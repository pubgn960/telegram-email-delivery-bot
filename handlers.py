"""
Telegram Update Handlers for Telegram Email Image Delivery Bot.
Includes dynamic DB-backed group monitoring, setup wizard, group management, and admin commands.
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
from email_parser import extract_email
from media_collector import media_collector, user_session_manager
from delivery import deliver_images_for_email
from database import (
    get_current_settings,
    update_source_group,
    update_delivery_group,
    remove_source_group,
    remove_delivery_group,
    reset_groups,
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
    get_uptime_str,
    get_memory_usage_mb,
    is_railway_environment,
    get_db_type_name
)

logger = logging.getLogger(__name__)


# ==========================================
# Group Message Handlers (Dynamic DB Lookup)
# ==========================================

async def source_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in the Source Group.
    Dynamically checks the Source Group ID from database settings on every message.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat:
        return

    # Read current group configuration dynamically from database
    settings = await get_current_settings()
    configured_source_id = settings.source_group_id

    # If Source Group ID is set in DB, enforce chat ID match
    if configured_source_id and chat.id != configured_source_id:
        return
    # Fallback to Config env if DB is unconfigured but env is set
    elif not configured_source_id and Config.SOURCE_GROUP_ID != 0 and chat.id != Config.SOURCE_GROUP_ID:
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
    Dynamically checks the Delivery Group ID from database settings on every message.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    # Read current group configuration dynamically from database
    settings = await get_current_settings()
    configured_delivery_id = settings.delivery_group_id

    # If Delivery Group ID is set in DB, enforce chat ID match
    if configured_delivery_id and chat.id != configured_delivery_id:
        return
    # Fallback to Config env if DB is unconfigured but env is set
    elif not configured_delivery_id and Config.DELIVERY_GROUP_ID != 0 and chat.id != Config.DELIVERY_GROUP_ID:
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
# Dynamic Setup Wizard & Group Commands
# ==========================================

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /setup command. Displays dynamic environment, permissions, and setup status checklist.
    """
    if not await check_admin_permission(update):
        return

    chat = update.effective_chat
    bot_member = None
    if chat and chat.type in ("group", "supergroup"):
        try:
            bot_member = await chat.get_member(context.bot.id)
        except Exception:
            pass

    # Check permissions
    is_bot_admin = bot_member.status in ("administrator", "creator") if bot_member else True
    can_send = True

    # Database connection test
    db_ok = True
    try:
        settings = await get_current_settings()
    except Exception as e:
        logger.error(f"Database setup check failed: {e}")
        db_ok = False
        settings = None

    source_configured = bool(settings and settings.source_group_id)
    delivery_configured = bool(settings and settings.delivery_group_id)
    railway_detected = is_railway_environment()

    lines = ["🤖 <b>Setup Wizard</b>\n"]
    lines.append(f"{'✅' if is_bot_admin else '❌'} <b>Bot Administrator</b>")
    lines.append(f"{'✅' if can_send else '❌'} <b>Can Read & Send Messages</b>")
    lines.append(f"{'✅' if db_ok else '❌'} <b>Database Connected</b> ({get_db_type_name()})")
    lines.append(f"{'✅' if railway_detected else 'ℹ️'} <b>Railway Environment</b> ({'Detected' if railway_detected else 'Local/Self-hosted'})")
    lines.append(f"{'✅' if source_configured else '❌'} <b>Source Group Configured</b>")
    lines.append(f"{'✅' if delivery_configured else '❌'} <b>Delivery Group Configured</b>")

    if not source_configured or not delivery_configured:
        lines.append("\n<b>Configuration Required:</b>")
        if not source_configured:
            lines.append("Run:\n<code>/source</code>\ninside your Source Group.\n")
        if not delivery_configured:
            lines.append("Run:\n<code>/delivery</code>\ninside your Delivery Group.")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def source_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /source command run inside the Source Group.
    Saves current group ID and title to database.
    """
    if not await check_admin_permission(update):
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("⚠️ Run <code>/source</code> inside your Source Group.", parse_mode="HTML")
        return

    # Verify bot admin status
    try:
        member = await chat.get_member(context.bot.id)
        if member.status not in ("administrator", "creator"):
            await update.effective_message.reply_text("❌ Bot must be an Administrator in this group to set it as Source Group.")
            return
    except Exception as e:
        logger.warning(f"Could not verify bot member status: {e}")

    # Save to database immediately
    settings = await update_source_group(chat.id, chat.title or "Source Group")
    group_title = html.escape(settings.source_group_title or chat.title or "Source Group")

    reply_msg = (
        f"✅ <b>Source Group Configured</b>\n\n"
        f"<b>Group:</b>\n{group_title}\n\n"
        f"<b>Chat ID:</b>\n<code>{settings.source_group_id}</code>"
    )
    await update.effective_message.reply_text(reply_msg, parse_mode="HTML")


async def delivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles /delivery command run inside the Delivery Group.
    Saves current group ID and title to database.
    """
    if not await check_admin_permission(update):
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("⚠️ Run <code>/delivery</code> inside your Delivery Group.", parse_mode="HTML")
        return

    # Verify bot admin status
    try:
        member = await chat.get_member(context.bot.id)
        if member.status not in ("administrator", "creator"):
            await update.effective_message.reply_text("❌ Bot must be an Administrator in this group to set it as Delivery Group.")
            return
    except Exception as e:
        logger.warning(f"Could not verify bot member status: {e}")

    # Save to database immediately
    settings = await update_delivery_group(chat.id, chat.title or "Delivery Group")
    group_title = html.escape(settings.delivery_group_title or chat.title or "Delivery Group")

    reply_msg = (
        f"✅ <b>Delivery Group Configured</b>\n\n"
        f"<b>Group:</b>\n{group_title}\n\n"
        f"<b>Chat ID:</b>\n<code>{settings.delivery_group_id}</code>"
    )
    await update.effective_message.reply_text(reply_msg, parse_mode="HTML")


async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /groups command displaying active group settings from database."""
    if not await check_admin_permission(update):
        return

    settings = await get_current_settings()

    src_name = html.escape(settings.source_group_title or "Unconfigured")
    src_id = f"<code>{settings.source_group_id}</code>" if settings.source_group_id else "<i>None</i>"

    del_name = html.escape(settings.delivery_group_title or "Unconfigured")
    del_id = f"<code>{settings.delivery_group_id}</code>" if settings.delivery_group_id else "<i>None</i>"

    msg = (
        "<b>Current Configuration</b>\n\n"
        f"📥 <b>Source Group</b>\n{src_name}\nChat ID: {src_id}\n\n"
        f"📤 <b>Delivery Group</b>\n{del_name}\nChat ID: {del_id}\n\n"
        f"<b>Database:</b> {get_db_type_name()}\n"
        f"<b>Status:</b> Ready"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /status command displaying detailed system diagnostic metrics."""
    if not await check_admin_permission(update):
        return

    settings = await get_current_settings()
    stats = await get_stats()

    src_str = html.escape(settings.source_group_title or "Unconfigured")
    if settings.source_group_id:
        src_str += f" (<code>{settings.source_group_id}</code>)"

    del_str = html.escape(settings.delivery_group_title or "Unconfigured")
    if settings.delivery_group_id:
        del_str += f" (<code>{settings.delivery_group_id}</code>)"

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    railway_str = "Active" if is_railway_environment() else "Local / Self-Hosted"

    msg = (
        "📊 <b>Bot System Status & Diagnostics</b>\n\n"
        f"🤖 <b>Bot Version:</b> v1.0.0\n"
        f"⏱ <b>Bot Uptime:</b> {get_uptime_str()}\n"
        f"🗄 <b>Database Status:</b> Connected ({get_db_type_name()})\n"
        f"📥 <b>Source Group:</b> {src_str}\n"
        f"📤 <b>Delivery Group:</b> {del_str}\n"
        f"📦 <b>Orders Stored:</b> <code>{stats['total_orders']}</code>\n"
        f"🖼 <b>Images Stored:</b> <code>{stats['total_images']}</code>\n"
        f"🐍 <b>Python Version:</b> {py_version}\n"
        f"🚂 <b>Railway Status:</b> {railway_str}\n"
        f"💾 <b>Memory Usage:</b> {get_memory_usage_mb()}"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


async def removesource_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /removesource command to clear Source Group setting."""
    if not await check_admin_permission(update):
        return

    await remove_source_group()
    await update.effective_message.reply_text("✅ Source Group Removed Successfully.", parse_mode="HTML")


async def removedelivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /removedelivery command to clear Delivery Group setting."""
    if not await check_admin_permission(update):
        return

    await remove_delivery_group()
    await update.effective_message.reply_text("✅ Delivery Group Removed Successfully.", parse_mode="HTML")


async def resetgroups_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /resetgroups command to clear both Source and Delivery Group settings."""
    if not await check_admin_permission(update):
        return

    await reset_groups()
    await update.effective_message.reply_text("✅ All group settings have been reset.", parse_mode="HTML")


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
        f"Type <code>/help</code> or <code>/setup</code> to manage configuration."
    )
    await update.effective_message.reply_text(welcome_msg, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /help command listing all commands."""
    if not await check_admin_permission(update):
        return

    help_msg = (
        "🛠 <b>Admin Commands & Management Suite</b>\n\n"
        "<b>Group Configuration:</b>\n"
        "• <code>/setup</code> - Interactive setup wizard\n"
        "• <code>/source</code> - Set current group as Source Group\n"
        "• <code>/delivery</code> - Set current group as Delivery Group\n"
        "• <code>/groups</code> - Display current group setup\n"
        "• <code>/status</code> - Detailed system diagnostics & uptime\n"
        "• <code>/removesource</code> - Remove Source Group\n"
        "• <code>/removedelivery</code> - Remove Delivery Group\n"
        "• <code>/resetgroups</code> - Reset all group configurations\n\n"
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
        details.append(f"{idx}. Email: <code>{email_escaped}</code> | Images: <code>{len(order.images)}</code> | Created: <code>{created_str}</code>")

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

        # Dispose active DB engine pool before file copy
        await dispose_engine()

        if os.path.exists(db_path):
            shutil.copyfile(db_path, backup_dest)

        await telegram_file.download_to_drive(custom_path=db_path)
        await init_db()

        await update.effective_message.reply_text("✅ Database successfully restored from backup!")
    except Exception as e:
        logger.error(f"Error restoring database backup: {e}")
        await update.effective_message.reply_text(f"❌ Database restore failed: {e}")
