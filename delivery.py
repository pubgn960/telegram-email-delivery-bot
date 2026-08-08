"""
Delivery engine handling media group aggregation, auto-splitting (max 10 items),
photo/document dispatching, API retries, and delivery status tracking.
"""

import asyncio
import logging
from typing import List, Union, Optional
from telegram import Bot, InputMediaPhoto, InputMediaDocument
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

from config import Config
from database import (
    get_newest_order_by_email,
    get_all_orders_by_email,
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

    Args:
        bot (Bot): Telegram Bot instance.
        chat_id (int): Destination chat/group ID.
        media (List[MediaUnion]): Array of InputMediaPhoto or InputMediaDocument objects (max 10).
        reply_to_message_id (int, optional): Message ID to reply to.
        max_retries (int): Maximum retry attempts.
        delay (float): Delay between retries in seconds.

    Returns:
        bool: True if delivered successfully, False otherwise.
    """
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


async def deliver_images_for_email(
    bot: Bot,
    chat_id: int,
    email: str,
    reply_to_message_id: Optional[int] = None,
    send_all_history: bool = False
) -> bool:
    """
    Retrieves stored image records for an email address and delivers them as Telegram albums.

    Args:
        bot (Bot): Telegram Bot instance.
        chat_id (int): Destination chat ID.
        email (str): Normalized target email address.
        reply_to_message_id (int, optional): Message ID to reply to in Telegram.
        send_all_history (bool): If True, sends all orders for email; if False, sends newest order.

    Returns:
        bool: True if images were found and delivered, False otherwise.
    """
    email_clean = email.lower().strip()

    if send_all_history:
        orders: List[Order] = await get_all_orders_by_email(email_clean)
    else:
        newest = await get_newest_order_by_email(email_clean)
        orders = [newest] if newest else []

    if not orders:
        logger.info(f"Delivery requested for '{email_clean}' but no records were found.")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="❌ No images found for this email.",
                reply_to_message_id=reply_to_message_id
            )
        except Exception as e:
            logger.error(f"Failed to send 'no images' reply message: {e}")
        return False

    # Eagerly collect image objects preserving position order
    all_images: List[Image] = []
    for order in orders:
        all_images.extend(order.images)

    total_images = len(all_images)
    logger.info(f"Delivering {total_images} images for email: '{email_clean}' to chat: {chat_id}")

    # Send status header reply message
    header_text = (
        f"✅ Images found\n"
        f"Email: {email_clean}\n"
        f"Total Images: {total_images}"
    )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=header_text,
            reply_to_message_id=reply_to_message_id
        )
    except Exception as e:
        logger.error(f"Failed to send delivery header message: {e}")

    # Chunk images into batches of MAX_MEDIA_PER_ALBUM (10)
    image_batches = chunk_list(all_images, MAX_MEDIA_PER_ALBUM)

    delivered_count = 0
    for idx, batch in enumerate(image_batches):
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
            chat_id=chat_id,
            media=media_group
        )
        if sent:
            delivered_count += len(batch)

    # Mark orders as delivered in DB
    for order in orders:
        await mark_order_delivered(order.id)

    # Optional post-delivery cleanup
    if Config.DELETE_AFTER_DELIVERY:
        logger.info(f"DELETE_AFTER_DELIVERY enabled. Purging orders for email: '{email_clean}'")
        await delete_orders_by_email(email_clean)

    logger.info(f"Delivery completed for email '{email_clean}'. Sent {delivered_count}/{total_images} items.")
    return True
