"""
Telegram Update Handlers for Telegram Email Image Delivery Bot.
Includes group message handlers and admin command implementations.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import Config
from email_parser import extract_email
from media_collector import media_collector
from delivery import deliver_images_for_email
from database import (
    get_all_orders_by_email,
    delete_orders_by_email,
    get_stats,
    cleanup_old_records
)
from utils import check_admin_permission

logger = logging.getLogger(__name__)


# ==========================================
# Group Message Handlers
# ==========================================

async def source_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages sent to the Source Group.
    Collects photos/albums and detects email addresses in captions or text.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    # If SOURCE_GROUP_ID is configured, verify chat ID matches
    if Config.SOURCE_GROUP_ID != 0 and chat.id != Config.SOURCE_GROUP_ID:
        return

    # Check if message contains photo(s)
    if message.photo:
        await media_collector.add_photo_message(message)


async def delivery_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages sent to the Delivery Group.
    When a message contains an email address, retrieves and delivers stored images.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    # If DELIVERY_GROUP_ID is configured, verify chat ID matches
    if Config.DELIVERY_GROUP_ID != 0 and chat.id != Config.DELIVERY_GROUP_ID:
        return

    # Check text or caption for email address
    text_content = message.text or message.caption or ""
    if not text_content:
        return

    email = extract_email(text_content)
    if email:
        logger.info(f"Email delivery trigger received in Delivery Group for: {email}")
        await deliver_images_for_email(
            bot=context.bot,
            chat_id=chat.id,
            email=email,
            reply_to_message_id=message.message_id
        )


# ==========================================
# Admin Command Handlers
# ==========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    if not await check_admin_permission(update):
        return

    user = update.effective_user
    user_name = user.first_name if user else "Admin"

    welcome_text = (
        f"🤖 **Telegram Email Image Delivery Bot**\n\n"
        f"Hello {user_name}! You are authenticated as a bot administrator.\n\n"
        f"📥 **Source Group ID**: `{Config.SOURCE_GROUP_ID or 'Not Configured'}`\n"
        f"📤 **Delivery Group ID**: `{Config.DELIVERY_GROUP_ID or 'Not Configured'}`\n\n"
        f"Type `/help` to see available management commands."
    )
    await update.effective_message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command."""
    if not await check_admin_permission(update):
        return

    help_text = (
        "🛠 **Admin Commands & Usage**\n\n"
        "• `/start` - Check bot status and configuration\n"
        "• `/help` - Show this assistance menu\n"
        "• `/find <email>` - Search stored images and albums for an email\n"
        "• `/resend <email>` - Force re-delivery of images for an email\n"
        "• `/delete <email>` - Delete all stored records for an email\n"
        "• `/stats` - View database statistics & storage dashboard\n\n"
        "💡 *Note: Automatic image delivery triggers whenever someone posts an email in the Delivery Group.*"
    )
    await update.effective_message.reply_text(help_text, parse_mode="Markdown")


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /find command to search stored albums by email."""
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

    total_images = sum(len(order.images) for order in orders)
    details = [f"🔍 **Found {len(orders)} order(s) for email**: `{email}`\nTotal Images: **{total_images}**\n"]

    for idx, order in enumerate(orders, 1):
        date_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        img_count = len(order.images)
        mg_id = order.media_group_id or "Single Photo"
        details.append(f"{idx}. Order ID `{order.id}` | Date: `{date_str}` | Images: `{img_count}` | Album ID: `{mg_id}`")

    response_msg = "\n".join(details)
    await update.effective_message.reply_text(response_msg, parse_mode="Markdown")


async def resend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /resend command to trigger delivery manually."""
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
    await update.effective_message.reply_text(f"⏳ Processing manual re-delivery for `{email}`...", parse_mode="Markdown")

    await deliver_images_for_email(
        bot=context.bot,
        chat_id=target_chat_id,
        email=email,
        reply_to_message_id=update.effective_message.message_id
    )


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /delete command to purge records by email."""
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
        await update.effective_message.reply_text(
            f"✅ Successfully deleted **{deleted_count}** record(s) for `{email}`.",
            parse_mode="Markdown"
        )
    else:
        await update.effective_message.reply_text(f"❌ No records found to delete for `{email}`.", parse_mode="Markdown")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /stats command to display statistics dashboard."""
    if not await check_admin_permission(update):
        return

    stats = await get_stats()

    stats_text = (
        "📊 **Bot Database Statistics**\n\n"
        f"📦 **Total Orders**: `{stats['total_orders']}`\n"
        f"🖼 **Total Images Stored**: `{stats['total_images']}`\n"
        f"✉️ **Unique Emails**: `{stats['unique_emails']}`\n"
        f"📅 **Oldest Record Date**: `{stats['oldest_order_date']}`\n\n"
        f"⚙️ **Retention Limit**: `{Config.MAX_STORAGE_DAYS} Days`"
    )
    await update.effective_message.reply_text(stats_text, parse_mode="Markdown")
