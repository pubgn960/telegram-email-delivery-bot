"""
Telegram Update Handlers for Telegram Email Image Delivery Bot.
Implements Source Group monitoring, Delivery Group triggering, and complete Admin management suite.
"""

import io
import os
import shutil
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from email_parser import extract_email
from media_collector import media_collector, user_session_manager
from delivery import deliver_images_for_email
from database import (
    get_all_orders_by_email,
    delete_orders_by_email,
    get_stats,
    get_pending_orders,
    export_orders_to_csv,
    get_db_file_path,
    init_db
)
from utils import check_admin_permission

logger = logging.getLogger(__name__)


# ==========================================
# Group Message Handlers
# ==========================================

async def source_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in the Source Group.
    Tracks user sessions when an email is posted, and routes photo/document uploads to media_collector.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat:
        return

    if Config.SOURCE_GROUP_ID != 0 and chat.id != Config.SOURCE_GROUP_ID:
        return

    text_content = message.text or message.caption or ""
    if text_content and user:
        email = extract_email(text_content)
        if email:
            user_session_manager.update_session(user.id, email)

    # Route photos and photo documents to collector
    if message.photo or (message.document and (message.document.mime_type or "").startswith("image/")):
        await media_collector.add_media_message(message)


async def delivery_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in the Delivery Group.
    Triggers automated image delivery when an email address is posted.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    if Config.DELIVERY_GROUP_ID != 0 and chat.id != Config.DELIVERY_GROUP_ID:
        return

    text_content = message.text or message.caption or ""
    if not text_content:
        return

    email = extract_email(text_content)
    if email:
        logger.info(f"Email delivery trigger detected in Delivery Group for: {email}")
        await deliver_images_for_email(
            bot=context.bot,
            chat_id=chat.id,
            email=email,
            reply_to_message_id=message.message_id
        )


# ==========================================
# Admin Management Commands
# ==========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    if not await check_admin_permission(update):
        return

    user = update.effective_user
    name = user.first_name if user else "Admin"

    welcome_msg = (
        f"🤖 **Telegram Email Image Delivery Bot v1.0.0**\n\n"
        f"Welcome {name}! You are authenticated as a bot administrator.\n\n"
        f"📥 **Source Group ID**: `{Config.SOURCE_GROUP_ID or 'Unconfigured'}`\n"
        f"📤 **Delivery Group ID**: `{Config.DELIVERY_GROUP_ID or 'Unconfigured'}`\n\n"
        f"Type `/help` to see all available management commands."
    )
    await update.effective_message.reply_text(welcome_msg, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command listing all admin tools."""
    if not await check_admin_permission(update):
        return

    help_msg = (
        "🛠 **Admin Commands & Tools**\n\n"
        "• `/start` - Check bot status\n"
        "• `/help` - Show command instructions\n"
        "• `/find <email>` - Search order history for email\n"
        "• `/resend <email>` - Deliver stored images for email\n"
        "• `/delete <email>` - Delete all database records for email\n"
        "• `/stats` - Display storage & database metrics dashboard\n"
        "• `/pending` - List all undelivered orders\n"
        "• `/export` - Export database records as CSV file\n"
        "• `/backup` - Download SQLite database backup\n"
        "• `/restore` - Restore SQLite database from attached `.db` file\n"
    )
    await update.effective_message.reply_text(help_msg, parse_mode="Markdown")


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /find command to search order history for an email."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: `/find email@example.com`", parse_mode="Markdown")
        return

    raw_input = " ".join(context.args)
    email = extract_email(raw_input)

    if not email:
        await update.effective_message.reply_text("❌ Invalid email format provided.")
        return

    orders = await get_all_orders_by_email(email)
    if not orders:
        await update.effective_message.reply_text(f"❌ No records found for email: `{email}`", parse_mode="Markdown")
        return

    total_imgs = sum(len(o.images) for o in orders)
    details = [f"🔍 **Found {len(orders)} order(s) for email**: `{email}`\nTotal Images: **{total_imgs}**\n"]

    for idx, order in enumerate(orders, 1):
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        delivered_str = order.delivered_at.strftime("%Y-%m-%d %H:%M:%S UTC") if order.delivered_at else "Pending"
        img_count = len(order.images)
        details.append(f"{idx}. Order `{order.id}` | Created: `{created_str}` | Status: `{delivered_str}` | Images: `{img_count}`")

    await update.effective_message.reply_text("\n".join(details), parse_mode="Markdown")


async def resend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /resend command to manually trigger image delivery."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: `/resend email@example.com`", parse_mode="Markdown")
        return

    raw_input = " ".join(context.args)
    email = extract_email(raw_input)

    if not email:
        await update.effective_message.reply_text("❌ Invalid email format provided.")
        return

    target_chat_id = update.effective_chat.id
    await update.effective_message.reply_text(f"⏳ Processing re-delivery for `{email}`...", parse_mode="Markdown")

    await deliver_images_for_email(
        bot=context.bot,
        chat_id=target_chat_id,
        email=email,
        reply_to_message_id=update.effective_message.message_id
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /delete command to purge records for an email."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: `/delete email@example.com`", parse_mode="Markdown")
        return

    raw_input = " ".join(context.args)
    email = extract_email(raw_input)

    if not email:
        await update.effective_message.reply_text("❌ Invalid email format provided.")
        return

    deleted_count = await delete_orders_by_email(email)
    if deleted_count > 0:
        await update.effective_message.reply_text(f"✅ Successfully deleted **{deleted_count}** record(s) for `{email}`.", parse_mode="Markdown")
    else:
        await update.effective_message.reply_text(f"❌ No records found for `{email}`.", parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /stats command displaying database statistics."""
    if not await check_admin_permission(update):
        return

    stats = await get_stats()
    msg = (
        "📊 **Bot System & Database Dashboard**\n\n"
        f"📦 **Total Orders**: `{stats['total_orders']}`\n"
        f"🖼 **Total Images**: `{stats['total_images']}`\n"
        f"✉️ **Unique Emails**: `{stats['unique_emails']}`\n"
        f"⏳ **Pending Deliveries**: `{stats['pending_orders']}`\n"
        f"📅 **Oldest Record Date**: `{stats['oldest_order_date']}`\n\n"
        f"⚙️ **Retention Limit**: `{Config.CLEANUP_DAYS} Days`"
    )
    await update.effective_message.reply_text(msg, parse_mode="Markdown")


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /pending command to list undelivered orders."""
    if not await check_admin_permission(update):
        return

    pending = await get_pending_orders()
    if not pending:
        await update.effective_message.reply_text("✅ All orders have been delivered! No pending uploads.")
        return

    details = [f"⏳ **Found {len(pending)} Undelivered Order(s)**:\n"]
    for idx, order in enumerate(pending[:15], 1):  # Cap at 15 for readable formatting
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        details.append(f"{idx}. Email: `{order.email}` | Images: `{len(order.images)}` | Created: `{created_str}`")

    if len(pending) > 15:
        details.append(f"\n... and {len(pending) - 15} more pending order(s).")

    await update.effective_message.reply_text("\n".join(details), parse_mode="Markdown")


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /export command generating and sending a CSV export of all database records."""
    if not await check_admin_permission(update):
        return

    await update.effective_message.reply_text("⏳ Generating database CSV export...")

    csv_data = await export_orders_to_csv()
    csv_bytes = csv_data.encode("utf-8")
    document_file = io.BytesIO(csv_bytes)
    document_file.name = "orders_export.csv"

    await update.effective_message.reply_document(
        document=document_file,
        caption="📄 **Orders Database Export (CSV)**",
        parse_mode="Markdown"
    )


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /backup command creating and sending a SQLite database file backup."""
    if not await check_admin_permission(update):
        return

    db_path = await get_db_file_path()
    if not db_path:
        await update.effective_message.reply_text("⚠️ Backup available only for local SQLite database installations.")
        return

    await update.effective_message.reply_text("⏳ Creating SQLite database backup...")
    try:
        with open(db_path, "rb") as f:
            db_bytes = f.read()

        db_file = io.BytesIO(db_bytes)
        db_file.name = "bot_database_backup.db"

        await update.effective_message.reply_document(
            document=db_file,
            caption="💾 **SQLite Database Backup**",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error creating database backup: {e}")
        await update.effective_message.reply_text(f"❌ Failed to create database backup: {e}")


async def restore_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /restore command to restore SQLite database from an attached .db file."""
    if not await check_admin_permission(update):
        return

    message = update.effective_message
    if not message.reply_to_message or not message.reply_to_message.document:
        await update.effective_message.reply_text(
            "⚠️ Usage: Reply to a message containing an attached `.db` backup file with `/restore`."
        )
        return

    doc = message.reply_to_message.document
    if not doc.file_name.endswith(".db"):
        await update.effective_message.reply_text("❌ Attached file must be a `.db` database backup file.")
        return

    db_path = await get_db_file_path()
    if not db_path:
        await update.effective_message.reply_text("⚠️ Restore is supported only for SQLite database installations.")
        return

    await update.effective_message.reply_text("⏳ Restoring database from backup file...")
    try:
        telegram_file = await context.bot.get_file(doc.file_id)
        backup_dest = f"{db_path}.bak"

        # Backup current file first
        if os.path.exists(db_path):
            shutil.copyfile(db_path, backup_dest)

        # Download replacement DB
        await telegram_file.download_to_drive(custom_path=db_path)
        await init_db()

        await update.effective_message.reply_text("✅ Database successfully restored from backup!")
    except Exception as e:
        logger.error(f"Error restoring database backup: {e}")
        await update.effective_message.reply_text(f"❌ Database restore failed: {e}")
