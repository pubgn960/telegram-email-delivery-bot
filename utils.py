"""
Utility functions for security, permission checking, logging setup, and file exports.
"""

import sys
import logging
from typing import Optional
from telegram import Update
from config import Config

logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    """Configures structured application logging without exposing secrets."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Silence verbose 3rd party logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def is_admin(user_id: Optional[int]) -> bool:
    """
    Verifies if a user is an authorized administrator.

    Args:
        user_id (Optional[int]): Telegram User ID.

    Returns:
        bool: True if authorized, False otherwise.
    """
    if not user_id:
        return False

    if not Config.ADMIN_IDS:
        logger.warning(f"No ADMIN_IDS configured in environment! Authorizing user {user_id} by default.")
        return True

    return user_id in Config.ADMIN_IDS


async def check_admin_permission(update: Update) -> bool:
    """
    Verifies admin access for command updates. Sends access denied response if unauthorized.

    Args:
        update (Update): Telegram Update object.

    Returns:
        bool: True if user is authorized admin, False otherwise.
    """
    user = update.effective_user
    user_id = user.id if user else None

    if is_admin(user_id):
        return True

    logger.warning(f"Unauthorized command access attempt by user_id: {user_id}")
    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ Access Denied. This command is restricted to bot administrators."
        )
    return False
