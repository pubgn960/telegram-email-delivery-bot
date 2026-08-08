"""
Delivery module handling image aggregation, splitting into valid Telegram media groups (max 10),
and sending with automatic retry logic.
"""

import asyncio
import logging
from typing import List, Optional
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError, RetryAfter, TimedOut, NetworkError

from database import get_newest_order_by_email, get_all_orders_by_email
from models import Order

logger = logging.getLogger(__name__)

MAX_MEDIA_PER_ALBUM = 10


def chunk_list(lst: List[str], chunk_size: int = MAX_MEDIA_PER_ALBUM) -> List[List[str]]:
    """Splits a list into sublists of max chunk_size elements."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


async def send_media_group_with_retry(
    bot: Bot,
    chat_id: int,
    media: List[InputMediaPhoto],
    reply_to_message_id: Optional[int] = None,
    max_retries: int = 3
) -> bool:
    """
    Sends a media group with automatic retry logic for Telegram rate limits (RetryAfter) and timeouts.

    Args:
        bot (Bot): Telegram bot instance.
        chat_id (int): Destination group/chat ID.
        media (List[InputMediaPhoto]): Array of InputMediaPhoto objects (max 10).
        reply_to_message_id (int, optional): Message ID to reply to.
        max_retries (int): Maximum retry attempts.

    Returns:
        bool: True if sent successfully, False otherwise.
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
            logger.warning(f"Telegram Rate Limit hit. Sleeping for {e.retry_after} seconds (Attempt {attempt}/{max_retries})...")
            await asyncio.sleep(e.retry_after + 1)
        except (TimedOut, NetworkError) as e:
            logger.warning(f"Network error while sending media group: {e}. Retrying in 2s (Attempt {attempt}/{max_retries})...")
            await asyncio.sleep(2)
        except TelegramError as e:
            logger.error(f"Telegram error delivering media group: {e}")
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
    Finds stored image records for an email address and delivers them as albums.

    Args:
        bot (Bot): Telegram Bot instance.
        chat_id (int): Destination chat ID.
        email (str): Normalized target email address.
        reply_to_message_id (int, optional): Message ID to reply to in Telegram.
        send_all_history (bool): If True, sends all orders for email; if False, sends newest order.

    Returns:
        bool: True if images were found and sent, False if no images found.
    """
    email_clean = email.lower().strip()

    if send_all_history:
        orders: List[Order] = await get_all_orders_by_email(email_clean)
    else:
        newest_order = await get_newest_order_by_email(email_clean)
        orders = [newest_order] if newest_order else []

    if not orders:
        logger.info(f"Delivery requested for '{email_clean}' but no images found.")
        reply_text = f"❌ No images found for this email."
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=reply_text,
                reply_to_message_id=reply_to_message_id
            )
        except Exception as e:
            logger.error(f"Failed to send 'no images' reply: {e}")
        return False

    # Extract all telegram_file_ids in order
    all_file_ids: List[str] = []
    for order in orders:
        # Images are ordered by position
        for img in order.images:
            all_file_ids.append(img.telegram_file_id)

    total_images = len(all_file_ids)
    logger.info(f"Delivering {total_images} images for email: {email_clean} to chat: {chat_id}")

    # Send status reply message
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
    batches = chunk_list(all_file_ids, MAX_MEDIA_PER_ALBUM)

    success_count = 0
    for idx, batch in enumerate(batches):
        media_group = [InputMediaPhoto(media=file_id) for file_id in batch]
        # Small delay between albums to prevent flooding
        if idx > 0:
            await asyncio.sleep(1.0)

        sent = await send_media_group_with_retry(
            bot=bot,
            chat_id=chat_id,
            media=media_group
        )
        if sent:
            success_count += len(batch)

    logger.info(f"Delivery completed for email '{email_clean}'. Sent {success_count}/{total_images} images.")
    return True
