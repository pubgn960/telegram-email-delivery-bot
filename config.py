"""
Configuration management for Telegram Email Image Delivery Bot.
Handles environment variable loading, parsing, validation, and database URL adaptation.
"""

import os
import logging
from typing import Set
from dotenv import load_dotenv

# Load environment variables from .env file if available
load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Bot Configuration loaded from environment variables."""

    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # Group IDs
    SOURCE_GROUP_ID: int = int(os.getenv("SOURCE_GROUP_ID", "0"))
    DELIVERY_GROUP_ID: int = int(os.getenv("DELIVERY_GROUP_ID", "0"))

    # Admin Telegram User IDs
    RAW_ADMIN_IDS: str = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS: Set[int] = set()

    # Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot_database.db")

    # Media Group Collection Settings
    # Timeout in seconds to wait for all photos in an album to arrive
    MEDIA_GROUP_TIMEOUT: float = float(os.getenv("MEDIA_GROUP_TIMEOUT", "2.0"))

    # Storage & Cleanup settings
    MAX_STORAGE_DAYS: int = int(os.getenv("MAX_STORAGE_DAYS", "30"))

    @classmethod
    def load_and_validate(cls) -> None:
        """Parse complex env variables and validate critical settings."""
        # Parse Admin IDs
        if cls.RAW_ADMIN_IDS:
            try:
                # Supports comma-separated values: "12345,67890" or space separated
                cleaned_str = cls.RAW_ADMIN_IDS.replace(",", " ").replace(";", " ")
                cls.ADMIN_IDS = {int(x.strip()) for x in cleaned_str.split() if x.strip().isdigit()}
            except Exception as e:
                logger.error(f"Error parsing ADMIN_IDS: {e}")

        # Adapt DATABASE_URL for SQLAlchemy Async if standard postgresql/sqlite strings are provided
        if cls.DATABASE_URL.startswith("postgres://"):
            cls.DATABASE_URL = cls.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
        elif cls.DATABASE_URL.startswith("postgresql://") and not cls.DATABASE_URL.startswith("postgresql+asyncpg://"):
            cls.DATABASE_URL = cls.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif cls.DATABASE_URL.startswith("sqlite://") and not cls.DATABASE_URL.startswith("sqlite+aiosqlite://"):
            cls.DATABASE_URL = cls.DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://", 1)

        if not cls.BOT_TOKEN:
            logger.warning("BOT_TOKEN is not set in environment variables!")


# Initialize configuration validation on import
Config.load_and_validate()
