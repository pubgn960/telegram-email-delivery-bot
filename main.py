"""
Main entry point for Telegram Email Image Delivery Bot.
Initializes database, configures handlers, starts background tasks, and runs bot polling.
"""

import sys
import asyncio
import logging
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)

from config import Config
from database import init_db, cleanup_old_records
from utils import setup_logging
from handlers import (
    source_group_handler,
    delivery_group_handler,
    start_command,
    help_command,
    find_command,
    resend_command,
    delete_command,
    stats_command,
    pending_command,
    export_command,
    backup_command,
    restore_command
)

# Initialize application logging
setup_logging()
logger = logging.getLogger("main")


async def periodic_cleanup_task() -> None:
    """Background task running every 24 hours to automatically purge old records."""
    while True:
        try:
            await asyncio.sleep(86400)  # 24 hours
            if Config.CLEANUP_DAYS > 0:
                logger.info("Executing scheduled database retention cleanup...")
                await cleanup_old_records(Config.CLEANUP_DAYS)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup task: {e}")


async def post_init(application: Application) -> None:
    """Post-initialization callback run inside the active application event loop."""
    logger.info("Initializing database schema...")
    await init_db()

    if Config.CLEANUP_DAYS > 0:
        cleaned = await cleanup_old_records(Config.CLEANUP_DAYS)
        if cleaned > 0:
            logger.info(f"Startup retention check purged {cleaned} expired records.")

    # Schedule background cleanup task in active event loop
    asyncio.create_task(periodic_cleanup_task())

    logger.info("Bot initialization complete. Active and listening for updates...")


def main() -> None:
    """Configures and launches the Telegram Bot Application."""
    if not Config.BOT_TOKEN:
        logger.critical("BOT_TOKEN is missing! Please configure it in .env file or environment variables.")
        sys.exit(1)

    logger.info("Starting Telegram Email Image Delivery Bot v1.0.0...")

    # Build python-telegram-bot application
    application = (
        ApplicationBuilder()
        .token(Config.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Register Admin Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("find", find_command))
    application.add_handler(CommandHandler("resend", resend_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("restore", restore_command))

    # Register Source Group Handler (Photos, Photo Documents, Text/Caption for user sessions)
    application.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.Document.IMAGE | filters.TEXT | filters.CAPTION) & (~filters.COMMAND),
            source_group_handler
        ),
        group=1
    )

    # Register Delivery Group Handler (Text or Caption messages containing emails)
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & (~filters.COMMAND),
            delivery_group_handler
        ),
        group=2
    )

    logger.info("Bot running in polling mode. Press Ctrl+C to stop.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
