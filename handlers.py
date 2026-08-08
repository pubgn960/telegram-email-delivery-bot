"""
Telegram Update Handlers for Telegram Email Image Delivery Bot.
Implements Two-Group Reply-Based Workflow, Privacy Protection (Exact Customer Message Copy without metadata),
Telegram Reaction handling (👍 order received, ❤️ delivery completed), and Admin Commands.
Includes structured logging tags ([CLIENT], [LOADER], [DELIVERY], [REACTION]).
"""

import io
import os
import sys
import html
import shutil
import logging
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from config import Config
from email_parser import extract_email, extract_order_id, extract_package
from media_collector import media_collector, user_session_manager
from delivery import deliver_order_by_id, deliver_images_for_email
from database import (
    get_current_settings,
    update_source_group,
    update_delivery_group,
    remove_source_group,
    remove_delivery_group,
    reset_groups,
    create_order,
    set_order_loader_message_id,
    get_order_by_id,
    get_order_by_loader_msg_id,
    get_pending_orders,
    get_delivered_orders,
    get_all_orders_by_email,
    delete_orders_by_email,
    cancel_order,
    get_detailed_stats,
    export_orders_to_csv,
    get_db_file_path,
    dispose_engine,
    init_db
)
from utils import (
    check_admin_permission,
    is_admin,
    safe_set_message_reaction,
    get_uptime_str,
    get_memory_usage_mb,
    is_railway_environment,
    get_db_type_name
)

logger = logging.getLogger(__name__)


# ==========================================
# Two-Group Workflow Message Handlers
# ==========================================

async def source_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in Group 1 (Client Group).
    When a customer sends an order message containing an email:
    1. Registers new Order in DB with status 'Pending'.
    2. Copies original customer message to Group 2 (Loader Group) EXACTLY as received (No added metadata/formatting).
    3. Adds 👍 reaction to original customer order message.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    settings = await get_current_settings()
    configured_client_id = settings.source_group_id

    if not configured_client_id:
        logger.warning(f"[CLIENT] Client Group is not configured yet. Ignored message in chat {chat.id} ({chat.title}).")
        return

    # Must match configured Client Group
    if chat.id != configured_client_id:
        logger.debug(f"[CLIENT] Ignored message in chat {chat.id} ({chat.title}); configured Client Group ID is {configured_client_id}.")
        return

    text_content = message.text or message.caption or ""
    if not text_content:
        logger.debug(f"[CLIENT] Message {message.message_id} in Client Group has no text/caption content.")
        return

    email = extract_email(text_content)
    if not email:
        logger.debug(f"[CLIENT] Message {message.message_id} in Client Group does not contain a valid email address.")
        return

    logger.info(f"[CLIENT] New order detected for email '{email}' in Client Group {chat.id} (Msg ID: {message.message_id})")

    package_desc = extract_package(text_content)

    # 1. Create Pending Order in DB
    order = await create_order(
        email=email,
        client_chat_id=chat.id,
        original_message_id=message.message_id,
        package=package_desc
    )

    # 2. Copy Original Customer Message to Loader Group EXACTLY as received (Zero added metadata or headers)
    loader_group_id = settings.delivery_group_id
    if loader_group_id:
        try:
            try:
                forwarded_msg = await context.bot.copy_message(
                    chat_id=loader_group_id,
                    from_chat_id=chat.id,
                    message_id=message.message_id
                )
            except Exception as e_copy:
                logger.debug(f"copy_message failed: {e_copy}. Fallback to raw text send_message.")
                forwarded_msg = await context.bot.send_message(
                    chat_id=loader_group_id,
                    text=text_content
                )

            await set_order_loader_message_id(order.id, forwarded_msg.message_id)
            logger.info(f"[CLIENT] Order copied to Loader Group {loader_group_id} (Order #{order.id}, Loader Msg ID: {forwarded_msg.message_id})")
        except Exception as e:
            logger.error(f"[CLIENT] Failed to post Order #{order.id} to Loader Group {loader_group_id}: {e}")
    else:
        logger.warning(f"[CLIENT] Order #{order.id} registered, but Loader Group is not configured yet!")

    # 3. Add 👍 reaction to ORIGINAL customer order message
    reacted = await safe_set_message_reaction(
        bot=context.bot,
        chat_id=chat.id,
        message_id=message.message_id,
        emoji="👍",
        fallback_emoji=None,
        log_tag="[REACTION]"
    )
    if reacted:
        logger.info("[REACTION] 👍 Order received")
    else:
        logger.warning("Reaction not supported.")


async def delivery_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Monitors messages in Group 2 (Loader Group).
    Validates that incoming images/documents are sent strictly as a reply to a valid bot Order Message.
    Identifies order by DB lookup and triggers album debouncing and automatic delivery.
    """
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    settings = await get_current_settings()
    configured_loader_id = settings.delivery_group_id

    if not configured_loader_id:
        logger.warning(f"[LOADER] Loader Group is not configured yet. Ignored message in chat {chat.id} ({chat.title}).")
        return

    # Must match configured Loader Group
    if chat.id != configured_loader_id:
        logger.debug(f"[LOADER] Ignored message in chat {chat.id} ({chat.title}); configured Loader Group ID is {configured_loader_id}.")
        return

    is_media = bool(message.photo or (message.document and (message.document.mime_type or "").startswith("image/")))
    if not is_media:
        return

    reply_to = message.reply_to_message

    # Rule 1: Message MUST be a reply
    if not reply_to:
        logger.warning(f"[LOADER] Reply failed: Loader message {message.message_id} in Loader Group is not a reply to an order.")
        try:
            await message.reply_text(
                "❌ Please reply to the original order message.",
                reply_to_message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"[LOADER] Failed to send non-reply rejection message: {e}")
        return

    logger.info(f"[LOADER] Reply detected (Loader Msg ID: {message.message_id}, Replied Msg ID: {reply_to.message_id})")

    # Rule 2: Identify order from database using replied message ID or text Order ID
    order = await get_order_by_loader_msg_id(reply_to.message_id)
    if not order:
        reply_text = reply_to.text or reply_to.caption or ""
        order_id_from_text = extract_order_id(reply_text)
        if order_id_from_text:
            order = await get_order_by_id(order_id_from_text)

    if not order:
        logger.warning(f"[LOADER] Reply failed: Could not match replied message {reply_to.message_id} to any Order in DB.")
        try:
            await message.reply_text(
                "❌ Please reply to the original order message.",
                reply_to_message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"[LOADER] Failed to send un-matched order rejection message: {e}")
        return

    # Rule 3: Check Order Status (Duplicate Protection & State Check)
    if order.status == "Delivered":
        logger.info(f"[LOADER] Duplicate reply detected: Order #{order.id} is already Delivered.")
        try:
            await message.reply_text(
                "⚠️ This order has already been delivered.",
                reply_to_message_id=message.message_id
            )
        except Exception:
            pass
        return

    if order.status == "Cancelled":
        logger.info(f"[LOADER] Reply failed: Order #{order.id} is Cancelled.")
        try:
            await message.reply_text(
                f"❌ Order #{order.id} has been cancelled.",
                reply_to_message_id=message.message_id
            )
        except Exception:
            pass
        return

    if order.status == "Expired":
        logger.info(f"[LOADER] Reply failed: Order #{order.id} is Expired.")
        try:
            await message.reply_text(
                f"⏰ Order #{order.id} has expired (Pending Too Long).",
                reply_to_message_id=message.message_id
            )
        except Exception:
            pass
        return

    logger.info(f"[LOADER] Processing media reply for Order #{order.id} (Email: '{order.email}')...")

    # Pass media to collector
    await media_collector.add_reply_media_message(
        message=message,
        order_id=order.id,
        email=order.email,
        bot=context.bot
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
    /source command run inside Group 1 (Client Group).
    Saves Chat ID and Name to DB as Client Group.
    """
    if not await verify_admin_and_group(update, context):
        return

    chat = update.effective_chat
    group_name = chat.title or "Client Group"

    settings = await update_source_group(chat.id, group_name)
    title_escaped = html.escape(settings.source_group_title or group_name)

    reply_msg = (
        f"✅ <b>Client Group Saved</b>\n\n"
        f"<b>Group:</b>\n{title_escaped}\n\n"
        f"<b>ID:</b>\n<code>{settings.source_group_id}</code>"
    )
    await update.effective_message.reply_text(reply_msg, parse_mode="HTML")


async def delivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /delivery command run inside Group 2 (Loader Group).
    Saves Chat ID and Name to DB as Loader Group.
    """
    if not await verify_admin_and_group(update, context):
        return

    chat = update.effective_chat
    group_name = chat.title or "Loader Group"

    settings = await update_delivery_group(chat.id, group_name)
    title_escaped = html.escape(settings.delivery_group_title or group_name)

    reply_msg = (
        f"✅ <b>Loader Group Saved</b>\n\n"
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
        f"📥 <b>Client Group</b>\n\n{src_title}\n\n"
        f"📤 <b>Loader Group</b>\n\n{del_title}\n\n"
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
    stats = await get_detailed_stats()

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
        f"<b>Client Group:</b> {src_str}\n"
        f"<b>Loader Group:</b> {del_str}\n"
        f"<b>Total Orders:</b> {stats['total_orders']}\n"
        f"<b>Pending Orders:</b> {stats['pending_orders']}\n"
        f"<b>Delivered Orders:</b> {stats['delivered_orders']}\n"
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
        "🤖 <b>Two-Group Reply-Based Setup Wizard</b>\n",
        f"{'✅' if src_ok else '❌'} <b>Client Group:</b> {html.escape(settings.source_group_title or 'Unconfigured')}",
        f"{'✅' if del_ok else '❌'} <b>Loader Group:</b> {html.escape(settings.delivery_group_title or 'Unconfigured')}\n",
        "<b>Setup Instructions:</b>",
        "1. Add bot to Client Group → Promote to Admin → Send <code>/source</code>",
        "2. Add bot to Loader Group → Promote to Admin → Send <code>/delivery</code>"
    ]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


# ==========================================
# Order Management Commands
# ==========================================

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /pending command listing all pending orders."""
    if not await check_admin_permission(update):
        return

    pending = await get_pending_orders()
    if not pending:
        await update.effective_message.reply_text("✅ No pending orders! All orders delivered.")
        return

    details = [f"⏳ <b>Pending Orders ({len(pending)})</b>:\n"]
    for idx, order in enumerate(pending[:15], 1):
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M UTC")
        email_escaped = html.escape(order.email)
        pkg_escaped = html.escape(order.package or "Standard Package")
        details.append(f"{idx}. Order <code>#{order.id}</code> | Email: <code>{email_escaped}</code>\n    Package: <i>{pkg_escaped}</i> | Created: <code>{created_str}</code>")

    if len(pending) > 15:
        details.append(f"\n... and {len(pending) - 15} more pending order(s).")

    await update.effective_message.reply_text("\n".join(details), parse_mode="HTML")


async def delivered_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /delivered command showing latest delivered orders."""
    if not await check_admin_permission(update):
        return

    delivered = await get_delivered_orders(limit=15)
    if not delivered:
        await update.effective_message.reply_text("ℹ️ No delivered orders found.")
        return

    details = [f"✅ <b>Latest Delivered Orders ({len(delivered)})</b>:\n"]
    for idx, order in enumerate(delivered, 1):
        delivered_str = order.delivered_at.strftime("%Y-%m-%d %H:%M UTC") if order.delivered_at else "N/A"
        email_escaped = html.escape(order.email)
        details.append(f"{idx}. Order <code>#{order.id}</code> | Email: <code>{email_escaped}</code> | Images: <code>{len(order.images)}</code> | Delivered: <code>{delivered_str}</code>")

    await update.effective_message.reply_text("\n".join(details), parse_mode="HTML")


async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /find <order_id_or_email> command."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: <code>/find 10025</code> or <code>/find email@example.com</code>", parse_mode="HTML")
        return

    raw_arg = context.args[0].strip()

    if raw_arg.lstrip("#").isdigit():
        order_id = int(raw_arg.lstrip("#"))
        order = await get_order_by_id(order_id)
        if not order:
            await update.effective_message.reply_text(f"❌ Order <code>#{order_id}</code> not found.", parse_mode="HTML")
            return
        orders = [order]
    else:
        email = extract_email(raw_arg)
        if not email:
            await update.effective_message.reply_text("❌ Invalid Order ID or email format.")
            return
        orders = await get_all_orders_by_email(email)

    if not orders:
        await update.effective_message.reply_text("❌ No matching orders found.")
        return

    details = [f"🔍 <b>Found {len(orders)} matching order(s)</b>:\n"]
    for idx, order in enumerate(orders, 1):
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M UTC")
        delivered_str = order.delivered_at.strftime("%Y-%m-%d %H:%M UTC") if order.delivered_at else "N/A"
        email_escaped = html.escape(order.email)
        status_icon = "✅" if order.status == "Delivered" else ("⏳" if order.status == "Pending" else "❌")
        details.append(
            f"{idx}. {status_icon} Order <code>#{order.id}</code> | Status: <b>{order.status}</b>\n"
            f"    Email: <code>{email_escaped}</code> | Images: <b>{len(order.images)}</b>\n"
            f"    Created: <code>{created_str}</code> | Delivered: <code>{delivered_str}</code>"
        )

    await update.effective_message.reply_text("\n".join(details), parse_mode="HTML")


async def order_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /order <order_id> command displaying complete order information."""
    if not await check_admin_permission(update):
        return

    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.effective_message.reply_text("⚠️ Usage: <code>/order 10025</code>", parse_mode="HTML")
        return

    order_id = int(context.args[0].lstrip("#"))
    order = await get_order_by_id(order_id)

    if not order:
        await update.effective_message.reply_text(f"❌ Order <code>#{order_id}</code> not found.", parse_mode="HTML")
        return

    created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    delivered_str = order.delivered_at.strftime("%Y-%m-%d %H:%M:%S UTC") if order.delivered_at else "Pending"
    email_escaped = html.escape(order.email)
    pkg_escaped = html.escape(order.package or "Standard Package")

    status_icon = "✅" if order.status == "Delivered" else ("⏳" if order.status == "Pending" else "❌")

    msg = (
        f"📦 <b>Order Detailed Information</b>\n\n"
        f"<b>Order ID:</b> #{order.id}\n"
        f"<b>Status:</b> {status_icon} {order.status}\n"
        f"<b>Email:</b> <code>{email_escaped}</code>\n"
        f"<b>Package:</b> <i>{pkg_escaped}</i>\n"
        f"<b>Stored Images:</b> {len(order.images)}\n"
        f"<b>Client Chat ID:</b> <code>{order.client_chat_id or 'N/A'}</code>\n"
        f"<b>Loader Msg ID:</b> <code>{order.loader_message_id or 'N/A'}</code>\n"
        f"<b>Created Time:</b> <code>{created_str}</code>\n"
        f"<b>Delivered Time:</b> <code>{delivered_str}</code>"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /cancel <order_id> command."""
    if not await check_admin_permission(update):
        return

    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.effective_message.reply_text("⚠️ Usage: <code>/cancel 10025</code>", parse_mode="HTML")
        return

    order_id = int(context.args[0].lstrip("#"))
    order, success = await cancel_order(order_id)

    if not success or not order:
        await update.effective_message.reply_text(f"❌ Order <code>#{order_id}</code> not found.", parse_mode="HTML")
        return

    await update.effective_message.reply_text(f"✅ Order <code>#{order_id}</code> has been cancelled successfully.", parse_mode="HTML")


async def resend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /resend <order_id_or_email> command."""
    if not await check_admin_permission(update):
        return

    if not context.args:
        await update.effective_message.reply_text("⚠️ Usage: <code>/resend 10025</code> or <code>/resend email@example.com</code>", parse_mode="HTML")
        return

    raw_arg = context.args[0].strip()

    if raw_arg.lstrip("#").isdigit():
        order_id = int(raw_arg.lstrip("#"))
        await update.effective_message.reply_text(f"⏳ Processing re-delivery for Order <code>#{order_id}</code>...", parse_mode="HTML")
        res = await deliver_order_by_id(
            bot=context.bot,
            order_id=order_id,
            target_delivery_chat_id=update.effective_chat.id
        )
        if res:
            await update.effective_message.reply_text(f"✅ Re-delivery of Order <code>#{order_id}</code> completed.", parse_mode="HTML")
        else:
            await update.effective_message.reply_text(f"❌ Re-delivery of Order <code>#{order_id}</code> failed.", parse_mode="HTML")
    else:
        email = extract_email(raw_arg)
        if not email:
            await update.effective_message.reply_text("❌ Invalid Order ID or email format.")
            return

        await update.effective_message.reply_text(f"⏳ Processing re-delivery for <code>{html.escape(email)}</code>...", parse_mode="HTML")
        await deliver_images_for_email(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            email=email,
            reply_to_message_id=update.effective_message.message_id
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /stats command displaying detailed dashboard statistics."""
    if not await check_admin_permission(update):
        return

    stats = await get_detailed_stats()

    msg = (
        "📊 <b>Bot Statistics Dashboard</b>\n\n"
        f"📦 <b>Total Orders:</b> <code>{stats['total_orders']}</code>\n"
        f"⏳ <b>Pending Orders:</b> <code>{stats['pending_orders']}</code>\n"
        f"✅ <b>Delivered Orders:</b> <code>{stats['delivered_orders']}</code>\n"
        f"❌ <b>Cancelled Orders:</b> <code>{stats['cancelled_orders']}</code>\n\n"
        f"📅 <b>Today's Orders:</b> <code>{stats['today_orders']}</code>\n"
        f"🚀 <b>Today's Deliveries:</b> <code>{stats['today_deliveries']}</code>\n"
        f"⚡ <b>Avg Delivery Time:</b> <code>{stats['avg_delivery_time']}</code>\n\n"
        f"⚙️ <b>Retention Limit:</b> <code>{Config.CLEANUP_DAYS} Days</code>"
    )
    await update.effective_message.reply_text(msg, parse_mode="HTML")


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


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /export command generating and sending a CSV export."""
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
        f"📥 <b>Client Group</b>: {html.escape(settings.source_group_title or 'Unconfigured')}\n"
        f"📤 <b>Loader Group</b>: {html.escape(settings.delivery_group_title or 'Unconfigured')}\n\n"
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
        "• <code>/source</code> - Mark current group as Client Group\n"
        "• <code>/delivery</code> - Mark current group as Loader Group\n"
        "• <code>/groups</code> - Show group status\n"
        "• <code>/resetgroups</code> - Reset all group settings\n"
        "• <code>/status</code> - Display bot status\n"
        "• <code>/setup</code> - View setup guide\n\n"
        "<b>Order & Data Management:</b>\n"
        "• <code>/pending</code> - List pending orders\n"
        "• <code>/delivered</code> - List latest delivered orders\n"
        "• <code>/find &lt;id_or_email&gt;</code> - Search orders\n"
        "• <code>/order &lt;id&gt;</code> - Complete order information\n"
        "• <code>/cancel &lt;id&gt;</code> - Cancel a pending order\n"
        "• <code>/resend &lt;id&gt;</code> - Re-deliver an order\n"
        "• <code>/delete &lt;email&gt;</code> - Delete records for email\n"
        "• <code>/stats</code> - Rich statistics dashboard\n"
        "• <code>/export</code> - Export CSV report\n"
        "• <code>/backup</code> - Backup SQLite database\n"
        "• <code>/restore</code> - Restore SQLite database\n"
    )
    await update.effective_message.reply_text(help_msg, parse_mode="HTML")


async def removesource_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /removesource command."""
    if not await check_admin_permission(update):
        return

    await remove_source_group()
    await update.effective_message.reply_text("✅ Client Group Removed Successfully.", parse_mode="HTML")


async def removedelivery_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /removedelivery command."""
    if not await check_admin_permission(update):
        return

    await remove_delivery_group()
    await update.effective_message.reply_text("✅ Loader Group Removed Successfully.", parse_mode="HTML")
