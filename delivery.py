"""
Delivery engine handling media group aggregation, auto-splitting (max 10 items),
dispatching image albums to the Client Group, Telegram API retries, database status updates,
and Loader confirmations.
"""

import html
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Union, Optional, Any
from telegram import Bot, InputMediaPhoto, InputMediaDocument
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

from config import Config
from database import (
    get_order_by_id,
    get_all_orders_by_email,
    get_current_settings,
    mark_order_delivered,
    delete_orders_by_email
)
from models import Order, Image

logger = logging.getLogger(__name__)

MAX_MEDIA_PER_ALBUM = 10
MediaUnion = Union[InputMediaPhoto, InputMediaDocument]


def chunk_list(lst: List[Any], chunk_size: int = MAX_MEDIA_PER_ALBUM) -> List[List[Any]]:
    """Splits a list into sublists of maximum length chunk_size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


async def send_media_group_with_retry(
    bot: Bot,
    chat_id: int,
    media: List[MediaUnion],
    reply_to_message_id: Optional[int] = None,
    max_retries: int = Config.MAX_RETRY,
    delay: float = Config.RETRY_DELAY
) -> bool:
    """Sends a media group to a Telegram chat with retry handling for rate limits and network glitches."""
    if not media:
        return True

    for attempt in range(1, max_retries + 1):
        try:
            await bot.send_media_group(
                chat_id=chat_id,
                media=media,
                reply_to_message_id=reply_to_message_id if attempt == 1 else None
            )
            return True
        except RetryAfter as e:
            wait_time = e.retry_after + 1
            logger.warning(f"Telegram Rate Limit (RetryAfter). Waiting {wait_time}s (Attempt {attempt}/{max_retries})...")
            await asyncio.sleep(wait_time)
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Network error during send_media_group: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except TelegramError as e:
            logger.error(f"Telegram API Error delivering album: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected error delivering media group: {e}")
            break

    return False


async def deliver_order_by_id(
    bot: Bot,
    order_id: int,
    loader_chat_id: Optional[int] = None,
    loader_reply_msg_id: Optional[int] = None,
    target_delivery_chat_id: Optional[int] = None
) -> bool:
    """
    Delivers stored image albums for an order to the Client Group and sends confirmation to the Loader Group.

    Args:
        bot (Bot): Telegram Bot instance.
        order_id (int): Target Order ID.
        loader_chat_id (Optional[int]): Loader Group Chat ID.
        loader_reply_msg_id (Optional[int]): Loader message ID to reply to / edit.
        target_delivery_chat_id (Optional[int]): Override Client Group Chat ID.

    Returns:
        bool: True if images were delivered successfully, False otherwise.
    """
    order = await get_order_by_id(order_id)
    settings = await get_current_settings()

    if not order or not order.images:
        logger.warning(f"Delivery attempted for Order ID #{order_id} but no stored images were found.")
        if loader_chat_id and loader_reply_msg_id:
            try:
                await bot.send_message(
                    chat_id=loader_chat_id,
                    text=f"❌ Unable to deliver order #{order_id}: No stored images found.",
                    reply_to_message_id=loader_reply_msg_id
                )
            except Exception:
                pass
        return False

    # Duplicate delivery prevention
    if order.status == "Delivered":
        logger.info(f"Duplicate Delivery | Order ID #{order_id} is already delivered. Ignored.")
        if loader_chat_id and loader_reply_msg_id:
            try:
                await bot.send_message(
                    chat_id=loader_chat_id,
                    text=f"⚠️ This order (#{order_id}) has already been delivered.",
                    reply_to_message_id=loader_reply_msg_id
                )
            except Exception:
                pass
        return False

    if order.status == "Cancelled":
        logger.info(f"Cancelled Order | Delivery attempted for cancelled Order ID #{order_id}. Ignored.")
        if loader_chat_id and loader_reply_msg_id:
            try:
                await bot.send_message(
                    chat_id=loader_chat_id,
                    text=f"❌ Order #{order_id} has been cancelled.",
                    reply_to_message_id=loader_reply_msg_id
                )
            except Exception:
                pass
        return False

    # Determine Client Group Chat ID
    client_chat_id = target_delivery_chat_id or order.client_chat_id or settings.source_group_id
    loader_group_id = loader_chat_id or settings.delivery_group_id

    if not client_chat_id:
        logger.error(f"Delivery failed: Client Group ID not found for Order ID #{order_id}.")
        if loader_group_id and loader_reply_msg_id:
            try:
                await bot.send_message(
                    chat_id=loader_group_id,
                    text="❌ Client Group is not configured yet. Send <code>/source</code> in your Client Group.",
                    reply_to_message_id=loader_reply_msg_id,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        return False

    all_images: List[Image] = list(order.images)
    total_images = len(all_images)
    email_escaped = html.escape(order.email)

    logger.info(f"Delivering Order ID: #{order_id} ({total_images} images) to Client Group: {client_chat_id}")

    # 1. Dispatch image albums to Client Group in batches of max 10 items (grouped by file_type)
    grouped_batches: List[List[Image]] = []
    current_batch: List[Image] = []

    for img in all_images:
        if not current_batch:
            current_batch.append(img)
        elif len(current_batch) >= MAX_MEDIA_PER_ALBUM or current_batch[0].file_type != img.file_type:
            grouped_batches.append(current_batch)
            current_batch = [img]
        else:
            current_batch.append(img)

    if current_batch:
        grouped_batches.append(current_batch)

    delivered_count = 0
    for idx, batch in enumerate(grouped_batches):
        media_group: List[MediaUnion] = []
        for img in batch:
            if img.file_type == "document":
                media_group.append(InputMediaDocument(media=img.telegram_file_id))
            else:
                media_group.append(InputMediaPhoto(media=img.telegram_file_id))

        if idx > 0:
            await asyncio.sleep(1.0)

        sent = await send_media_group_with_retry(
            bot=bot,
            chat_id=client_chat_id,
            media=media_group,
            reply_to_message_id=order.original_message_id if idx == 0 else None
        )
        if sent:
            delivered_count += len(batch)

    # 2. Send Delivery Completion Header in Client Group
    completion_text = (
        f"📧 <b>Email:</b>\n{email_escaped}\n\n"
        f"📦 <b>Order ID:</b>\n#{order.id}\n\n"
        f"✅ <b>Delivery Completed</b>"
    )

    try:
        await bot.send_message(
            chat_id=client_chat_id,
            text=completion_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send delivery completion header to Client Group: {e}")

    # 3. Mark order status as Delivered in DB
    updated_order = await mark_order_delivered(order.id)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 4. Edit or reply to Loader Order Message in Loader Group
    target_loader_msg_id = loader_reply_msg_id or order.loader_message_id
    if loader_group_id and target_loader_msg_id:
        loader_notice = (
            f"✅ <b>DELIVERED</b>\n\n"
            f"<b>Order ID:</b>\n#{order.id}\n\n"
            f"<b>Images:</b>\n{total_images}\n\n"
            f"<b>Delivered:</b>\n{now_str}"
        )
        try:
            await bot.send_message(
                chat_id=loader_group_id,
                text=loader_notice,
                reply_to_message_id=target_loader_msg_id,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send loader delivery confirmation: {e}")

    # 5. Optional post-delivery cleanup
    if Config.DELETE_AFTER_DELIVERY:
        logger.info(f"DELETE_AFTER_DELIVERY enabled. Purging order #{order.id} for email: '{order.email}'")
        await delete_orders_by_email(order.email)

    return True


async def deliver_images_for_email(
    bot: Bot,
    chat_id: int,
    email: str,
    reply_to_message_id: Optional[int] = None
) -> bool:
    """Finds pending orders for email and delivers them to target chat (used by /resend)."""
    email_clean = email.lower().strip()
    orders = await get_all_orders_by_email(email_clean)

    if not orders:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ No orders found for this email.",
                reply_to_message_id=reply_to_message_id
            )
        except Exception:
            pass
        return False

    success = False
    for order in orders:
        res = await deliver_order_by_id(
            bot=bot,
            order_id=order.id,
            target_delivery_chat_id=chat_id
        )
        if res:
            success = True

    return success
