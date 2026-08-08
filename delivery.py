"""
Delivery engine handling media group aggregation, auto-splitting (max 10 items),
photo/document dispatching to Delivery Group, API retries, delivery status updates,
and Loader Success Replies.
"""

import html
import asyncio
import logging
from typing import List, Union, Optional, Any
from telegram import Bot, InputMediaPhoto, InputMediaDocument
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

from config import Config
from database import (
    get_order_by_id,
    get_newest_order_by_email,
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
    """
    Sends a media group to a Telegram chat with retry handling for rate limits and errors.
    """
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
    Delivers stored images for an Order ID to the configured Delivery Group.
    Sends completion header to Delivery Group and Success Reply back to the Loader in Source Group.

    Args:
        bot (Bot): Telegram Bot instance.
        order_id (int): Target Order ID.
        loader_chat_id (Optional[int]): Source Group chat ID where loader replied.
        loader_reply_msg_id (Optional[int]): Loader's upload message ID to reply to.
        target_delivery_chat_id (Optional[int]): Override destination chat ID (used by /resend).

    Returns:
        bool: True if images were delivered successfully, False otherwise.
    """
    order = await get_order_by_id(order_id)
    if not order or not order.images:
        logger.warning(f"Delivery attempted for Order ID {order_id} but no stored images were found.")
        if loader_chat_id and loader_reply_msg_id:
            try:
                await bot.send_message(
                    chat_id=loader_chat_id,
                    text="❌ Unable to deliver order: No stored images found for this Order ID.",
                    reply_to_message_id=loader_reply_msg_id
                )
            except Exception:
                pass
        return False

    # Determine target Delivery Group ID
    if not target_delivery_chat_id:
        settings = await get_current_settings()
        target_delivery_chat_id = settings.delivery_group_id

    if not target_delivery_chat_id:
        logger.error("Delivery failed: Delivery Group is not configured in database settings.")
        if loader_chat_id and loader_reply_msg_id:
            try:
                await bot.send_message(
                    chat_id=loader_chat_id,
                    text="❌ Delivery Group is not configured yet. Run <code>/delivery</code> in your Delivery Group.",
                    reply_to_message_id=loader_reply_msg_id,
                    parse_mode="HTML"
                )
            except Exception:
                pass
        return False

    all_images: List[Image] = list(order.images)
    total_images = len(all_images)
    email_escaped = html.escape(order.email)

    logger.info(f"Delivering Order ID: {order_id} ({total_images} images) to Delivery Group: {target_delivery_chat_id}")

    # 1. Dispatch images to Delivery Group in batches of max 10 items (grouped by file_type)
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
            chat_id=target_delivery_chat_id,
            media=media_group
        )
        if sent:
            delivered_count += len(batch)

    # 2. Send Delivery Completion Header in Delivery Group
    completion_text = (
        f"📧 <b>Email:</b>\n{email_escaped}\n\n"
        f"📦 <b>Order ID:</b>\n{order.id}\n\n"
        f"✅ <b>Delivery Completed</b>"
    )

    try:
        await bot.send_message(
            chat_id=target_delivery_chat_id,
            text=completion_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send delivery completion header to Delivery Group: {e}")

    # 3. Mark order as delivered in database
    await mark_order_delivered(order.id)
    logger.info(f"Delivery Completed | Order ID: {order.id} | Email: {order.email} | Sent: {delivered_count}/{total_images}")

    # 4. Send Success Reply back to Loader in Source Group
    if loader_chat_id and loader_reply_msg_id:
        loader_success_text = (
            f"✅ <b>Delivery Successful</b>\n\n"
            f"<b>Email:</b>\n{email_escaped}\n\n"
            f"<b>Images:</b>\n{total_images}\n\n"
            f"<b>Order ID:</b>\n{order.id}"
        )
        try:
            await bot.send_message(
                chat_id=loader_chat_id,
                text=loader_success_text,
                reply_to_message_id=loader_reply_msg_id,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send loader success reply in Source Group: {e}")

    # 5. Optional post-delivery cleanup
    if Config.DELETE_AFTER_DELIVERY:
        logger.info(f"DELETE_AFTER_DELIVERY enabled. Purging order {order.id} for email: '{order.email}'")
        await delete_orders_by_email(order.email)

    return True


async def deliver_images_for_email(
    bot: Bot,
    chat_id: int,
    email: str,
    reply_to_message_id: Optional[int] = None,
    send_all_history: bool = False
) -> bool:
    """
    Finds orders for email and delivers them to target chat (used by /resend command).
    """
    email_clean = email.lower().strip()

    if send_all_history:
        orders: List[Order] = await get_all_orders_by_email(email_clean)
    else:
        newest = await get_newest_order_by_email(email_clean)
        orders = [newest] if newest else []

    if not orders:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ No images found for this email.",
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
