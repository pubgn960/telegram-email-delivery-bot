"""
Utility functions for logging, permissions, and string formatting.
"""

import logging
import sys
from typing import Optional
from telegram import Update
from config import Config

logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    """Configures structured logging for the application."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Reduce noisy library logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def is_admin(user_id: Optional[int]) -> bool:
    """
    Checks if a Telegram user ID is authorized as a bot administrator.

    Args:
        user_id (Optional[int]): Telegram user ID.

    Returns:
        bool: True if user is in Config.ADMIN_IDS (or ADMIN_IDS is empty for unrestricted dev mode).
    """
    if not user_id:
        return False

    # If no admin IDs are defined in env, log warning and allow for easy initial setup
    if not Config.ADMIN_IDS:
        logger.warning(f"No ADMIN_IDS defined in .env! Allowing access to user {user_id}.")
        return True

    return user_id in Config.ADMIN_IDS


async def check_admin_permission(update: Update) -> bool:
    """
    Helper function to check admin status from a Telegram Update and send permission denied message if unauthorized.

    Args:
        update (Update): Incoming Telegram update.

    Returns:
        bool: True if authorized, False otherwise.
    """
    user = update.effective_user
    user_id = user.id if user else None

    if is_admin(user_id):
        return True

    logger.warning(f"Unauthorized command access attempt by user: {user_id} ({user.username if user else 'Unknown'})")
    if update.effective_message:
        await update.effective_message.reply_text(
            "⛔ Access Denied. This command is restricted to bot administrators."
        )
    return False
