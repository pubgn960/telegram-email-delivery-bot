"""
Telegram Update Handlers for Telegram Email Image Delivery Bot.
Implements the Reply-Based Delivery Workflow, Order Registration, Loader Validation,
and self-configuring Admin Commands (/source, /delivery, /groups, /status, /stats, etc.).
"""

import io
import os
import sys
import html
import shutil
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config import Config
from email_parser import extract_email, extract_order_id
from media_collector import media_collector, user_session_manager
from delivery import deliver_order_by_id, deliver_images_for_email
from database import (
    get_current_settings,
    update_source_group,
    update_delivery_group,
    remove_source_group,
    remove_delivery_group,
    reset_groups,
    create_pending_order,
    get_order_by_id,
    get_all_orders_by_email,
    delete_orders_by_email,
    get_stats,
    get_pending_orders,
    export_orders_to_csv,
    get_db_file_path,
    dispose_engine,
    init_db
)
from utils import (
    check_admin_permission,
    is_admin,
    get_uptime_str,
    get_memory_usage_mb,
    is_railway_environment,
    get_db_type_name
)

logger = logging.getLogger(__name__)


# ==========================================
# Reply-Based Source Group Handler
# ==========================================

async def source_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in the Source Group (Loader Group).
    Enforces Reply-Based Order Mapping:
    1. If message contains email & is NOT replying to an order: Creates a new Order and posts Order Header into group.
    2. If message contains images: MUST be a reply to an Order Notification message. Otherwise, rejects.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat:
        return

    # Read current Source Group configuration dynamically from DB
    settings = await get_current_settings()
    configured_source_id = settings.source_group_id

    # If no Source Group configured yet, ignore message
    if not configured_source_id:
        return

    # Enforce chat ID match against configured Source Group
    if chat.id != configured_source_id:
        return

    text_content = message.text or message.caption or ""
    is_media = bool(message.photo or (message.document and (message.document.mime_type or "").startswith("image/")))

    # -------------------------------------------------------------
    # CASE 1: Customer Order Registration (Message contains email)
    # -------------------------------------------------------------
    email_in_msg = extract_email(text_content) if text_content else None
    
    # If text contains an email and is NOT a media reply uploading to an existing order
    if email_in_msg and not is_media and not message.reply_to_message:
        # Create new order record in DB
        new_order = await create_pending_order(email_in_msg)
        email_escaped = html.escape(email_in_msg)

        order_notice_text = (
            f"📦 <b>New Order</b>\n\n"
            f"<b>Email:</b>\n{email_escaped}\n\n"
            f"<b>Order ID:</b>\n{new_order.id}"
        )

        logger.info(f"Order Forwarded | Order ID: {new_order.id} | Email: {email_in_msg}")
        await message.reply_text(order_notice_text, parse_mode="HTML")

        if user:
            user_session_manager.update_session(user.id, email_in_msg)
        return

    # -------------------------------------------------------------
    # CASE 2: Loader Image Upload (Must be a reply to an order)
    # -------------------------------------------------------------
    if is_media:
        reply_to = message.reply_to_message

        # Rule: When bot receives images, it MUST verify the message is a reply.
        if not reply_to:
            logger.info("Invalid Reply | Loader sent images without replying to an order message.")
            await message.reply_text(
                "❌ Please reply to the original order message before sending images.",
                reply_to_message_id=message.message_id
            )
            return

        # Extract Order ID and Email from the replied-to message
        reply_text = reply_to.text or reply_to.caption or ""
        order_id = extract_order_id(reply_text)
        email_from_reply = extract_email(reply_text)

        if not order_id:
            logger.info("Invalid Reply | Reply target does not contain a valid Order ID.")
            await message.reply_text(
                "❌ Invalid order message.",
                reply_to_message_id=message.message_id
            )
            return

        # Verify order exists in DB
        existing_order = await get_order_by_id(order_id)
        if not existing_order:
            logger.info(f"Invalid Reply | Order ID {order_id} not found in database.")
            await message.reply_text(
                "❌ Invalid order message.",
                reply_to_message_id=message.message_id
            )
            return

        target_email = email_from_reply or existing_order.email
        if not target_email:
            logger.info(f"Invalid Reply | Unable to determine customer email for Order ID {order_id}.")
            await message.reply_text(
                "❌ Unable to determine customer email.",
                reply_to_message_id=message.message_id
            )
            return

        logger.info(f"Loader Reply Received | Order ID: {order_id} | Email: {target_email}")
        
        # Buffer and process media via collector
        await media_collector.add_reply_media_message(
            message=message,
            order_id=order_id,
            email=target_email,
            bot=context.bot
        )


async def delivery_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in the Delivery Group.
    If an email is posted in the Delivery Group, attempts to deliver newest pending order.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    settings = await get_current_settings()
    configured_delivery_id = settings.delivery_group_id

    if not configured_delivery_id or chat.id != configured_delivery_id:
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
# Self-Configuring Commands & Validation
# ==========================================

async def verify_admin_and_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Validates Admin user permission, group chat type, and Bot Admin status."""
    chat = update.effective_chat
    user = update.effective_user

    if not is_admin(user.id if user else None):
        if update.effective_message:
            await update.effective_message.reply_text("⛔ Access Denied. Restricted to authorized bot administrators.")
        return False

    if not chat or chat.type not in ("group", "supergroup"):
        if update.effective_message:
            await update.effective_message.reply_text("⚠️ This command must be executed inside a Telegram Group or Supergroup.")
        return False

    try:
        bot_member = await chat.get_member(context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            if update.effective_message:
                await update.effective_message.reply_text("❌ Please promote the bot to an Administrator in this group first.")
            return False
    except Exception as e:
        logger.warning(f"Error checking bot admin permissions: {e}")
        if update.effective_message:
            await update.effective_message.reply_text("❌ Failed to verify bot admin permissions in this chat.")
        return False

    return True


async def source_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /source command run inside the Source Group.
    Saves Chat ID and Name to DB as Source Group.
    """
    if not await verify_admin_and_group(update, context):
        return

    chat = update.effective_chat
    group_name = chat.title or "Orders Group"

    settings = await update_source_group(chat.id, group_name)
    title_escaped = html.escape(settings.source_group_title or group_name)

    reply_msg = (
        f"✅ <b>Source Group Saved</b>\n\n"
        f"<b>Group:</b>\n{title_escaped}\n\n"
        f"<b>ID:</b>\n<code>{settings.source_group_id}</code>"
    )
    await update.effective_message.reply_text(reply_msg, parse_mode="HTML")


async def delivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /delivery command run inside the Delivery Group.
    Saves Chat ID and Name to DB as Delivery Group.
    """
    if not await verify_admin_and_group(update, context):
        return

    chat = update.effective_chat
    group_name = chat.title or "Delivery Group"

    settings = await update_delivery_group(chat.id, group_name)
    title_escaped = html.escape(settings.delivery_group_title or group_name)

    reply_msg = (
        f"✅ <b>Delivery Group Saved</b>\n\n"
        f"<b>Group:</b>\n{title_escaped}\n\n"
        f"<b>ID:</b>\n<code>{settings.delivery_group_id}</code>"
    )
    await update.effective_message.reply_text(reply_msg, parse_mode="HTML")


async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /groups command displaying active group settings."""
    if not await check_admin_permission(update):
        return

    settings = await get_current_settings()

    src_title = html.escape(settings.source_group_title or "Unconfigured")
    del_title = html.escape(settings.delivery_group_title or "Unconfigured")

    msg = (
        f"📥 <b>Source Group</b>\n\n{src_title}\n\n"
        f"📤 <b>Delivery Group</b>\n\n{del_title}\n\n"
        f"<b>Status</b>\n\nReady"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


async def resetgroups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /resetgroups command."""
    if not await check_admin_permission(update):
        return

    await reset_groups()
    await update.effective_message.reply_text("✅ All group settings have been reset.", parse_mode="HTML")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /status command displaying system diagnostics."""
    if not await check_admin_permission(update):
        return

    settings = await get_current_settings()
    stats = await get_stats()

    src_str = html.escape(settings.source_group_title or "Unconfigured")
    if settings.source_group_id:
        src_str += f" ({settings.source_group_id})"

    del_str = html.escape(settings.delivery_group_title or "Unconfigured")
    if settings.delivery_group_id:
        del_str += f" ({settings.delivery_group_id})"

    msg = (
        "🤖 <b>Bot Status</b>\n\n"
        f"<b>Status:</b> Online\n"
        f"<b>Database:</b> Connected ({get_db_type_name()})\n"
        f"<b>Source Group:</b> {src_str}\n"
        f"<b>Delivery Group:</b> {del_str}\n"
        f"<b>Orders Stored:</b> {stats['total_orders']}\n"
        f"<b>Images Stored:</b> {stats['total_images']}\n"
        f"<b>Version:</b> v1.0.0\n"
        f"<b>Uptime:</b> {get_uptime_str()}"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setup command showing step-by-step guidance."""
    if not await check_admin_permission(update):
        return

    settings = await get_current_settings()
    src_ok = bool(settings.source_group_id)
    del_ok = bool(settings.delivery_group_id)

    lines = [
        "🤖 <b>Self-Configuring Setup Wizard</b>\n",
        f"{'✅' if src_ok else '❌'} <b>Source Group:</b> {html.escape(settings.source_group_title or 'Unconfigured')}",
        f"{'✅' if del_ok else '❌'} <b>Delivery Group:</b> {html.escape(settings.delivery_group_title or 'Unconfigured')}\n",
        "<b>Setup Instructions:</b>",
        "1. Add bot to Source Group → Promote to Admin → Send <code>/source</code>",
        "2. Add bot to Delivery Group → Promote to Admin → Send <code>/delivery</code>"
    ]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def removesource_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /removesource command."""
    if not await check_admin_permission(update):
        return

    await remove_source_group()
    await update.effective_message.reply_text("✅ Source Group Removed Successfully.", parse_mode="HTML")


async def removedelivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /removedelivery command."""
    if not await check_admin_permission(update):
        return

    await remove_delivery_group()
    await update.effective_message.reply_text("✅ Delivery Group Removed Successfully.", parse_mode="HTML")


# ==========================================
# Additional Admin Commands
# ==========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    if not await check_admin_permission(update):
        return

    user = update.effective_user
    name = html.escape(user.first_name if user else "Admin")
    settings = await get_current_settings()

    welcome_msg = (
        f"🤖 <b>Telegram Email Image Delivery Bot v1.0.0</b>\n\n"
        f"Welcome {name}! You are authenticated as a bot administrator.\n\n"
        f"📥 <b>Source Group</b>: {html.escape(settings.source_group_title or 'Unconfigured')}\n"
        f"📤 <b>Delivery Group</b>: {html.escape(settings.delivery_group_title or 'Unconfigured')}\n\n"
        f"Type <code>/help</code> or <code>/setup</code> for guidance."
    )
    await update.effective_message.reply_text(welcome_msg, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command listing all commands."""
    if not await check_admin_permission(update):
        return

    help_msg = (
        "🛠 <b>Admin Commands & Management Suite</b>\n\n"
        "<b>Group Configuration:</b>\n"
        "• <code>/source</code> - Mark current group as Source Group\n"
        "• <code>/delivery</code> - Mark current group as Delivery Group\n"
        "• <code>/groups</code> - Show group status\n"
        "• <code>/resetgroups</code> - Reset all group settings\n"
        "• <code>/status</code> - Display bot system status\n"
        "• <code>/setup</code> - View setup guide\n"
        "• <code>/removesource</code> - Remove Source Group\n"
        "• <code>/removedelivery</code> - Remove Delivery Group\n\n"
        "<b>Order & Data Management:</b>\n"
        "• <code>/find &lt;email&gt;</code> - Search order history for email\n"
        "• <code>/resend &lt;email&gt;</code> - Deliver stored images for email\n"
        "• <code>/delete &lt;email&gt;</code> - Delete records for email\n"
        "• <code>/stats</code> - Database metrics dashboard\n"
        "• <code>/pending</code> - List undelivered orders\n"
        "• <code>/export</code> - Export CSV report\n"
        "• <code>/backup</code> - Download SQLite DB backup\n"
        "• <code>/restore</code> - Restore SQLite DB from backup file\n"
    )
    await update.effective_message.reply_text(help_msg, parse_mode="HTML")


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /find command to search order history for an email."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: <code>/find email@example.com</code>", parse_mode="HTML")
        return

    raw_input = " ".join(context.args)
    email = extract_email(raw_input)

    if not email:
        await update.effective_message.reply_text("❌ Invalid email format provided.")
        return

    orders = await get_all_orders_by_email(email)
    if not orders:
        await update.effective_message.reply_text(f"❌ No records found for email: <code>{html.escape(email)}</code>", parse_mode="HTML")
        return

    total_imgs = sum(len(o.images) for o in orders)
    email_escaped = html.escape(email)
    details = [f"🔍 <b>Found {len(orders)} order(s) for email</b>: <code>{email_escaped}</code>\nTotal Images: <b>{total_imgs}</b>\n"]

    for idx, order in enumerate(orders, 1):
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        delivered_str = order.delivered_at.strftime("%Y-%m-%d %H:%M:%S UTC") if order.delivered_at else "Pending"
        img_count = len(order.images)
        details.append(f"{idx}. Order <code>{order.id}</code> | Created: <code>{created_str}</code> | Status: <code>{delivered_str}</code> | Images: <code>{img_count}</code>")

    await update.effective_message.reply_text("\n".join(details), parse_mode="HTML")


async def resend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /resend command to manually trigger image delivery."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: <code>/resend email@example.com</code>", parse_mode="HTML")
        return

    raw_input = " ".join(context.args)
    email = extract_email(raw_input)

    if not email:
        await update.effective_message.reply_text("❌ Invalid email format provided.")
        return

    target_chat_id = update.effective_chat.id
    await update.effective_message.reply_text(f"⏳ Processing re-delivery for <code>{html.escape(email)}</code>...", parse_mode="HTML")

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
        await update.effective_message.reply_text("⚠️ Usage: <code>/delete email@example.com</code>", parse_mode="HTML")
        return

    raw_input = " ".join(context.args)
    email = extract_email(raw_input)

    if not email:
        await update.effective_message.reply_text("❌ Invalid email format provided.")
        return

    deleted_count = await delete_orders_by_email(email)
    email_escaped = html.escape(email)
    if deleted_count > 0:
        await update.effective_message.reply_text(f"✅ Successfully deleted <b>{deleted_count}</b> record(s) for <code>{email_escaped}</code>.", parse_mode="HTML")
    else:
        await update.effective_message.reply_text(f"❌ No records found for <code>{email_escaped}</code>.", parse_mode="HTML")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /stats command displaying database statistics."""
    if not await check_admin_permission(update):
        return

    stats = await get_stats()
    msg = (
        "📊 <b>Bot System & Database Dashboard</b>\n\n"
        f"📦 <b>Total Orders</b>: <code>{stats['total_orders']}</code>\n"
        f"🖼 <b>Total Images</b>: <code>{stats['total_images']}</code>\n"
        f"✉️ <b>Unique Emails</b>: <code>{stats['unique_emails']}</code>\n"
        f"⏳ <b>Pending Deliveries</b>: <code>{stats['pending_orders']}</code>\n"
        f"📅 <b>Oldest Record Date</b>: <code>{stats['oldest_order_date']}</code>\n\n"
        f"⚙️ <b>Retention Limit</b>: <code>{Config.CLEANUP_DAYS} Days</code>"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /pending command to list undelivered orders."""
    if not await check_admin_permission(update):
        return

    pending = await get_pending_orders()
    if not pending:
        await update.effective_message.reply_text("✅ All orders have been delivered! No pending uploads.")
        return

    details = [f"⏳ <b>Found {len(pending)} Undelivered Order(s)</b>:\n"]
    for idx, order in enumerate(pending[:15], 1):
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        email_escaped = html.escape(order.email)
        details.append(f"{idx}. Order ID: <code>{order.id}</code> | Email: <code>{email_escaped}</code> | Images: <code>{len(order.images)}</code> | Created: <code>{created_str}</code>")

    if len(pending) > 15:
        details.append(f"\n... and {len(pending) - 15} more pending order(s).")

    await update.effective_message.reply_text("\n".join(details), parse_mode="HTML")


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
        caption="📄 <b>Orders Database Export (CSV)</b>",
        parse_mode="HTML"
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
            caption="💾 <b>SQLite Database Backup</b>",
            parse_mode="HTML"
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
            "⚠️ Usage: Reply to a message containing an attached <code>.db</code> backup file with <code>/restore</code>.",
            parse_mode="HTML"
        )
        return

    doc = message.reply_to_message.document
    if not doc.file_name.endswith(".db"):
        await update.effective_message.reply_text("❌ Attached file must be a <code>.db</code> database backup file.", parse_mode="HTML")
        return

    db_path = await get_db_file_path()
    if not db_path:
        await update.effective_message.reply_text("⚠️ Restore is supported only for SQLite database installations.")
        return

    await update.effective_message.reply_text("⏳ Restoring database from backup file...")
    try:
        telegram_file = await context.bot.get_file(doc.file_id)
        backup_dest = f"{db_path}.bak"

        await dispose_engine()

        if os.path.exists(db_path):
            shutil.copyfile(db_path, backup_dest)

        await telegram_file.download_to_drive(custom_path=db_path)
        await init_db()

        await update.effective_message.reply_text("✅ Database successfully restored from backup!")
    except Exception as e:
        logger.error(f"Error restoring database backup: {e}")
        await update.effective_message.reply_text(f"❌ Database restore failed: {e}")
