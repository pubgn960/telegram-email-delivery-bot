"""
Configuration management for Telegram Email Image Delivery Bot.
Uses pydantic and python-dotenv for strict environment variable parsing and validation.
"""

import os
import logging
from typing import Set, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Validated Application Configuration."""

    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # Telegram Group Chat IDs (Integers, e.g. -1001234567890)
    SOURCE_GROUP_ID: int = int(os.getenv("SOURCE_GROUP_ID", "0"))
    DELIVERY_GROUP_ID: int = int(os.getenv("DELIVERY_GROUP_ID", "0"))

    # Admin User IDs
    RAW_ADMIN_IDS: str = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS: Set[int] = set()

    # Database URL (SQLite default, PostgreSQL for production)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_database.db")

    # Media Group Debounce Window (seconds)
    MEDIA_GROUP_TIMEOUT: float = float(os.getenv("MEDIA_GROUP_TIMEOUT", "2.0"))

    # User Email Session Expiry (seconds - default 5 minutes = 300s)
    USER_SESSION_TIMEOUT: float = float(os.getenv("USER_SESSION_TIMEOUT", "300.0"))

    # Retry configuration for Telegram API calls
    MAX_RETRY: int = int(os.getenv("MAX_RETRY", "3"))
    RETRY_DELAY: float = float(os.getenv("RETRY_DELAY", "2.0"))

    # Storage Cleanup Retention (days)
    CLEANUP_DAYS: int = int(os.getenv("CLEANUP_DAYS", "30"))

    # Post-delivery option: delete order from DB after successful delivery
    DELETE_AFTER_DELIVERY: bool = os.getenv("DELETE_AFTER_DELIVERY", "false").lower() in ("true", "1", "yes")

    @classmethod
    def load_and_validate(cls) -> None:
        """Parses and validates environment settings."""
        # Parse Admin IDs
        if cls.RAW_ADMIN_IDS:
            try:
                cleaned_str = cls.RAW_ADMIN_IDS.replace(",", " ").replace(";", " ")
                cls.ADMIN_IDS = {int(x.strip()) for x in cleaned_str.split() if x.strip().lstrip("-").isdigit()}
            except Exception as e:
                logger.error(f"Error parsing ADMIN_IDS: {e}")

        # Adapt DATABASE_URL for SQLAlchemy 2 Async drivers
        if cls.DATABASE_URL.startswith("postgres://"):
            cls.DATABASE_URL = cls.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
        elif cls.DATABASE_URL.startswith("postgresql://") and not cls.DATABASE_URL.startswith("postgresql+asyncpg://"):
            cls.DATABASE_URL = cls.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif cls.DATABASE_URL.startswith("sqlite://") and not cls.DATABASE_URL.startswith("sqlite+aiosqlite://"):
            cls.DATABASE_URL = cls.DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)

        if not cls.BOT_TOKEN:
            logger.warning("BOT_TOKEN is not defined in environment variables!")


Config.load_and_validate()
