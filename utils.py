"""
Utility functions for security, permission checking, reaction handling, system metrics, logging setup, and formatting.
"""

import os
import sys
import time
import logging
from typing import Optional
from telegram import Update, Bot, ReactionTypeEmoji
from config import Config

logger = logging.getLogger(__name__)

# Start timestamp for calculating bot uptime
BOT_START_TIME = time.time()


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


async def safe_set_message_reaction(
    bot: Bot,
    chat_id: Optional[int],
    message_id: Optional[int],
    emoji: str = "👍",
    fallback_emoji: Optional[str] = None,
    log_tag: str = "[REACTION]"
) -> bool:
    """
    Safely sets a Telegram reaction emoji on a message.
    Gracefully handles cases where reactions are disabled in chat or unsupported by API.
    Never stops the workflow. Logs 'Reaction not supported' on failure.
    """
    if not chat_id or not message_id:
        return False

    # Primary emoji attempt
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
        return True
    except Exception as e:
        logger.debug(f"Reaction '{emoji}' via ReactionTypeEmoji failed: {e}. Trying raw string list...")

    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[emoji]
        )
        return True
    except Exception as e:
        logger.warning(f"Reaction not supported: {e}")

    # Fallback emoji attempt if specified
    if fallback_emoji:
        try:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[ReactionTypeEmoji(emoji=fallback_emoji)]
            )
            return True
        except Exception:
            pass

        try:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[fallback_emoji]
            )
            return True
        except Exception as e2:
            logger.warning(f"Reaction not supported: {e2}")

    return False


def get_uptime_str() -> str:
    """Calculates and formats bot uptime into readable string (e.g. 2d 5h 12m 30s)."""
    elapsed = int(time.time() - BOT_START_TIME)
    days, remainder = divmod(elapsed, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")

    return " ".join(parts)


def get_memory_usage_mb() -> str:
    """Returns process RAM memory usage in MB."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_bytes = process.memory_info().rss
        return f"{mem_bytes / (1024 * 1024):.2f} MB"
    except ImportError:
        pass

    try:
        import resource
        mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        if sys.platform == "darwin":
            return f"{mem_kb / (1024 * 1024):.2f} MB"
        return f"{mem_kb / 1024:.2f} MB"
    except Exception:
        return "N/A"


def is_railway_environment() -> bool:
    """Checks if running inside Railway cloud hosting environment."""
    railway_vars = ["RAILWAY_STATIC_URL", "RAILWAY_SERVICE_NAME", "RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID"]
    return any(os.getenv(var) for var in railway_vars)


def get_db_type_name() -> str:
    """Returns human-readable name of the database engine in use."""
    if "postgres" in Config.DATABASE_URL.lower():
        return "PostgreSQL"
    elif "sqlite" in Config.DATABASE_URL.lower():
        return "SQLite"
    return "Unknown DB"
