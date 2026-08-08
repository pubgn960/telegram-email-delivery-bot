"""
Media Group Collector module for debouncing and buffering Telegram photo albums.
Telegram sends albums as separate Update messages sharing a media_group_id.
This collector buffers these items, waits until the album is complete, extracts the email,
and saves the result to the database.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from telegram import Message, PhotoSize

from config import Config
from email_parser import extract_email
from database import save_order

logger = logging.getLogger(__name__)


class MediaGroupCollector:
    """
    In-memory collector and debouncer for Telegram media groups (albums) and single photos.
    """

    def __init__(self, timeout: float = Config.MEDIA_GROUP_TIMEOUT):
        self.timeout = timeout
        # Structure: media_group_id -> { "items": [(msg_id, file_id, caption)], "task": asyncio.Task }
        self._buffers: Dict[str, Dict[str, Any]] = {}
        # Set of recently processed media_group_ids for memory caching duplicate checks
        self._processed_cache: set = set()

    async def add_photo_message(self, message: Message) -> None:
        """
        Processes an incoming message containing a photo.
        Supports both Media Group (album) messages and single photo messages.

        Args:
            message (Message): Telegram message object containing photo(s).
        """
        if not message.photo:
            return

        # Select highest resolution photo
        highest_res_photo: PhotoSize = message.photo[-1]
        file_id = highest_res_photo.file_id
        caption = message.caption or message.text or ""
        msg_id = message.message_id
        media_group_id = message.media_group_id

        # Case 1: Single Photo (No media group ID)
        if not media_group_id:
            email = extract_email(caption)
            if email:
                logger.info(f"Single photo email detected: {email}")
                _, is_dup = await save_order(email=email, file_ids=[file_id], media_group_id=None)
                if is_dup:
                    logger.info(f"Duplicate single photo skipped for email: {email}")
            else:
                logger.debug("Single photo received without valid email. Ignored.")
            return

        # Case 2: Media Group (Album)
        # Duplicate check against in-memory cache
        if media_group_id in self._processed_cache:
            logger.info(f"Duplicate Media Group '{media_group_id}' received and skipped via cache.")
            return

        # If existing buffer present, cancel pending processing task
        if media_group_id in self._buffers:
            buf = self._buffers[media_group_id]
            if buf.get("task") and not buf["task"].done():
                buf["task"].cancel()
            buf["items"].append((msg_id, file_id, caption))
        else:
            self._buffers[media_group_id] = {
                "items": [(msg_id, file_id, caption)],
                "task": None
            }

        # Schedule debounced process task
        task = asyncio.create_task(self._schedule_flush(media_group_id))
        self._buffers[media_group_id]["task"] = task

    async def _schedule_flush(self, media_group_id: str) -> None:
        """Waits for timeout period before flushing accumulated album images to database."""
        try:
            await asyncio.sleep(self.timeout)
            await self._flush_media_group(media_group_id)
        except asyncio.CancelledError:
            # Expected when new items are appended to the album
            pass

    async def _flush_media_group(self, media_group_id: str) -> None:
        """Flushes buffered media group images, parses email, and saves to database."""
        buf = self._buffers.pop(media_group_id, None)
        if not buf:
            return

        items: List[Tuple[int, str, str]] = buf["items"]
        if not items:
            return

        # Preserve image order by sorting items by message_id
        items.sort(key=lambda x: x[0])

        # Extract file_ids and combine all captions to find email
        file_ids = [item[1] for item in items]
        combined_text = " ".join([item[2] for item in items if item[2]])

        email = extract_email(combined_text)

        if email:
            logger.info(f"Media group '{media_group_id}' completed with {len(file_ids)} images. Email detected: {email}")
            _, is_dup = await save_order(email=email, file_ids=file_ids, media_group_id=media_group_id)
            if is_dup:
                logger.info(f"Duplicate Media Group '{media_group_id}' skipped.")
            # Add to processed cache (keep cache bounded)
            self._processed_cache.add(media_group_id)
            if len(self._processed_cache) > 1000:
                self._processed_cache.pop()
        else:
            logger.warning(f"Media group '{media_group_id}' had {len(file_ids)} images but no valid email address was found in captions.")


# Singleton instance of MediaGroupCollector
media_collector = MediaGroupCollector()
