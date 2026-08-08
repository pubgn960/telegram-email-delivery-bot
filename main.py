"""
Main entry point for Telegram Email Image Delivery Bot.
Initializes database, configures handlers, sets Telegram '/' UI command menu,
populates global in-memory BOT_SETTINGS cache on startup, starts background tasks, and runs bot polling.
"""

import sys
import asyncio
import logging
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)

from config import Config
from database import init_db, cleanup_old_records, check_order_timeouts, reload_bot_settings_cache
from utils import setup_logging
from handlers import (
    source_group_handler,
    delivery_group_handler,
    start_command,
    help_command,
    find_command,
    order_info_command,
    cancel_command,
    resend_command,
    delete_command,
    stats_command,
    pending_command,
    delivered_command,
    export_command,
    backup_command,
    restore_command,
    setup_command,
    source_command,
    delivery_command,
    groups_command,
    status_command,
    removesource_command,
    removedelivery_command,
    resetgroups_command
)

# Initialize application logging
setup_logging()
logger = logging.getLogger("main")


async def periodic_maintenance_task() -> None:
    """Background task running every hour for order timeouts and 24h database retention cleanup."""
    while True:
        try:
            await asyncio.sleep(3600)  # Check every hour
            # Check order timeouts (pending longer than 24 hours)
            expired = await check_order_timeouts(timeout_hours=24)
            if expired > 0:
                logger.info(f"Periodic check marked {expired} pending order(s) as Expired (⏰ Pending Too Long).")

            # Retention cleanup if configured
            if Config.CLEANUP_DAYS > 0:
                await cleanup_old_records(Config.CLEANUP_DAYS)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic maintenance task: {e}")


async def post_init(application: Application) -> None:
    """Post-initialization callback run inside the active application event loop."""
    logger.info("Initializing database schema...")
    await init_db()

    # Load Settings from DB once on startup and populate in-memory BOT_SETTINGS cache
    await reload_bot_settings_cache()

    # Register Bot Commands list so Telegram displays them in the interactive '/' popup menu
    commands = [
        BotCommand("source", "Mark current group as Client Group"),
        BotCommand("delivery", "Mark current group as Loader Group"),
        BotCommand("groups", "Show group configuration status"),
        BotCommand("status", "View bot status & diagnostics"),
        BotCommand("setup", "View setup guide"),
        BotCommand("pending", "List pending orders"),
        BotCommand("delivered", "List latest delivered orders"),
        BotCommand("find", "Find order by ID or email"),
        BotCommand("order", "Display detailed order information"),
        BotCommand("cancel", "Cancel a pending order"),
        BotCommand("resend", "Re-deliver order images"),
        BotCommand("stats", "View bot statistics dashboard"),
        BotCommand("help", "List all admin commands"),
        BotCommand("export", "Export CSV data report"),
        BotCommand("backup", "Download SQLite database backup"),
        BotCommand("restore", "Restore SQLite database from backup")
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("Successfully registered bot commands for Telegram '/' menu UI.")
    except Exception as e:
        logger.warning(f"Failed to register '/' menu bot commands: {e}")

    # Initial order timeout check on startup
    expired = await check_order_timeouts(timeout_hours=24)
    if expired > 0:
        logger.info(f"Startup check marked {expired} pending order(s) as Expired.")

    if Config.CLEANUP_DAYS > 0:
        cleaned = await cleanup_old_records(Config.CLEANUP_DAYS)
        if cleaned > 0:
            logger.info(f"Startup retention check purged {cleaned} expired records.")

    # Schedule background maintenance task in active event loop
    asyncio.create_task(periodic_maintenance_task())

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

    # Register Setup & Group Configuration Commands
    application.add_handler(CommandHandler("setup", setup_command))
    application.add_handler(CommandHandler("source", source_command))
    application.add_handler(CommandHandler("delivery", delivery_command))
    application.add_handler(CommandHandler("groups", groups_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("removesource", removesource_command))
    application.add_handler(CommandHandler("removedelivery", removedelivery_command))
    application.add_handler(CommandHandler("resetgroups", resetgroups_command))

    # Register Core & New Admin Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("delivered", delivered_command))
    application.add_handler(CommandHandler("find", find_command))
    application.add_handler(CommandHandler("order", order_info_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("resend", resend_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("restore", restore_command))

    # Register Client Group Handler (Group 1 - Customer Orders)
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION | filters.PHOTO) & (~filters.COMMAND),
            source_group_handler
        ),
        group=1
    )

    # Register Loader Group Handler (Group 2 - Loader Photos / Photo Documents replied to orders)
    application.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.Document.ALL) & (~filters.COMMAND),
            delivery_group_handler
        ),
        group=2
    )

    logger.info("Bot running in polling mode. Press Ctrl+C to stop.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
