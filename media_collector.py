"""
Media Group Collector module supporting debouncing, user session fallback (5-min window),
photo documents, and SHA256 fingerprint duplicate suppression. Includes thread-safe locking and LRU cache.
"""

import time
import asyncio
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Any
from telegram import Message, PhotoSize, Document

from config import Config
from email_parser import extract_email
from database import save_order

logger = logging.getLogger(__name__)


class UserSessionManager:
    """
    Tracks recent email addresses submitted by users in the Source Group.
    Allows photo messages sent within 5 minutes (300s) to be automatically
    associated with the user's active session email.
    """

    def __init__(self, timeout: float = Config.USER_SESSION_TIMEOUT):
        self.timeout = timeout
        # Structure: user_id -> (email, timestamp)
        self._sessions: Dict[int, Tuple[str, float]] = {}

    def update_session(self, user_id: int, email: str) -> None:
        """Stores or updates the active email session for a Telegram user."""
        if user_id and email:
            self._cleanup_expired()
            self._sessions[user_id] = (email.lower().strip(), time.time())
            logger.debug(f"User {user_id} session updated with email: {email}")

    def get_session_email(self, user_id: int) -> Optional[str]:
        """Retrieves active session email if created within the timeout window."""
        if not user_id or user_id not in self._sessions:
            return None

        email, timestamp = self._sessions[user_id]
        if time.time() - timestamp <= self.timeout:
            logger.debug(f"Active session found for user {user_id}: {email}")
            return email
        else:
            self._sessions.pop(user_id, None)
            return None

    def _cleanup_expired(self) -> None:
        """Removes expired user sessions from memory."""
        now = time.time()
        expired = [uid for uid, (_, ts) in self._sessions.items() if now - ts > self.timeout]
        for uid in expired:
            self._sessions.pop(uid, None)


# Global session manager instance
user_session_manager = UserSessionManager()


class MediaGroupCollector:
    """
    In-memory debouncer and collector for Telegram photo albums and single photo/document messages.
    Uses asyncio.Lock for thread-safe concurrent update processing.
    """

    def __init__(self, timeout: float = Config.MEDIA_GROUP_TIMEOUT):
        self.timeout = timeout
        # Structure: media_group_id -> { "items": [(msg_id, file_id, file_type, caption, user_id)], "task": Task }
        self._buffers: Dict[str, Dict[str, Any]] = {}
        # LRU cache for processed media group IDs (max 1000 items)
        self._processed_cache: OrderedDict = OrderedDict()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def add_media_message(self, message: Message) -> None:
        """
        Processes an incoming photo or photo-document message safely.

        Args:
            message (Message): Telegram message object.
        """
        file_id: Optional[str] = None
        file_type: str = "photo"

        # 1. Extract Photo or Photo-Document file_id
        if message.photo:
            file_id = message.photo[-1].file_id
            file_type = "photo"
        elif message.document:
            mime = message.document.mime_type or ""
            if mime.startswith("image/"):
                file_id = message.document.file_id
                file_type = "document"

        if not file_id:
            return

        caption = message.caption or message.text or ""
        msg_id = message.message_id
        media_group_id = message.media_group_id
        user_id = message.from_user.id if message.from_user else 0

        # 2. Check for Email in caption or fallback to active User Session
        extracted_email = extract_email(caption)
        if extracted_email:
            user_session_manager.update_session(user_id, extracted_email)
            email = extracted_email
        else:
            email = user_session_manager.get_session_email(user_id)

        # Case A: Single Photo / Single Document (No media group)
        if not media_group_id:
            if email:
                logger.info(f"Processing single {file_type} upload for email: {email}")
                _, is_dup = await save_order(
                    email=email,
                    file_items=[(file_id, file_type)],
                    media_group_id=None
                )
                if is_dup:
                    logger.info(f"Duplicate single {file_type} upload skipped for email: {email}")
            else:
                logger.debug("Single photo received without explicit email or active user session. Ignored.")
            return

        # Case B: Media Group (Album) - Thread safe locking
        async with self._lock:
            if media_group_id in self._processed_cache:
                logger.info(f"Duplicate Media Group '{media_group_id}' skipped via LRU cache.")
                return

            if media_group_id in self._buffers:
                buf = self._buffers[media_group_id]
                if buf.get("task") and not buf["task"].done():
                    buf["task"].cancel()
                buf["items"].append((msg_id, file_id, file_type, caption, user_id))
                if email and not buf.get("email"):
                    buf["email"] = email
            else:
                self._buffers[media_group_id] = {
                    "items": [(msg_id, file_id, file_type, caption, user_id)],
                    "email": email,
                    "task": None
                }

            # Schedule debounced flush task
            task = asyncio.create_task(self._schedule_flush(media_group_id))
            self._buffers[media_group_id]["task"] = task

    async def _schedule_flush(self, media_group_id: str) -> None:
        """Waits for debounce timeout before flushing media group to database."""
        try:
            await asyncio.sleep(self.timeout)
            await self._flush_media_group(media_group_id)
        except asyncio.CancelledError:
            pass

    async def _flush_media_group(self, media_group_id: str) -> None:
        """Flushes buffered album safely under lock, resolves email, and saves to database."""
        async with self._lock:
            buf = self._buffers.pop(media_group_id, None)

        if not buf or not buf.get("items"):
            return

        items: List[Tuple[int, str, str, str, int]] = buf["items"]
        items.sort(key=lambda x: x[0])  # Sort by message_id to preserve original sequence

        # Combine captions and check session emails
        captions_combined = " ".join([it[3] for it in items if it[3]])
        email = extract_email(captions_combined) or buf.get("email")

        # Fallback check on user_id of first item in album
        if not email and items:
            first_user_id = items[0][4]
            email = user_session_manager.get_session_email(first_user_id)

        if email:
            file_items = [(it[1], it[2]) for it in items]
            logger.info(f"Flushing Media Group '{media_group_id}' with {len(file_items)} items for email: {email}")
            _, is_dup = await save_order(
                email=email,
                file_items=file_items,
                media_group_id=media_group_id
            )
            if is_dup:
                logger.info(f"Duplicate Media Group '{media_group_id}' skipped.")

            async with self._lock:
                self._processed_cache[media_group_id] = True
                if len(self._processed_cache) > 1000:
                    self._processed_cache.popitem(last=False)  # Evict oldest entry (LRU)
        else:
            logger.warning(f"Media Group '{media_group_id}' ({len(items)} items) could not be saved: No email detected.")


# Singleton collector instance
media_collector = MediaGroupCollector()
