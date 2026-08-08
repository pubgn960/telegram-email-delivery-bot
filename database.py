"""
Database manager providing asynchronous SQLAlchemy session management and queries.
Supports both SQLite and PostgreSQL natively via DATABASE_URL config.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from config import Config
from models import Base, Order, Image

logger = logging.getLogger(__name__)

# Create SQLAlchemy Async Engine
engine = create_async_engine(
    Config.DATABASE_URL,
    echo=False,
    future=True
)

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db() -> None:
    """Initializes the database by creating all declared tables if they do not exist."""
    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully.")


async def save_order(email: str, file_ids: List[str], media_group_id: Optional[str] = None) -> Tuple[Optional[Order], bool]:
    """
    Saves a new Order along with its associated image file IDs.
    Handles duplicate media groups gracefully.

    Args:
        email (str): The normalized recipient email.
        file_ids (List[str]): List of Telegram photo file_ids in order.
        media_group_id (str, optional): Telegram media_group_id if part of an album.

    Returns:
        Tuple[Optional[Order], bool]: (Saved Order object or None, is_duplicate boolean)
    """
    if not file_ids:
        logger.warning("Attempted to save order with no images. Aborting.")
        return None, False

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Check duplicate media group if media_group_id is present
            if media_group_id:
                stmt = select(Order).where(Order.media_group_id == media_group_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(f"Duplicate Media Group '{media_group_id}' skipped.")
                    return existing, True

            # Create new order
            new_order = Order(
                email=email.lower().strip(),
                media_group_id=media_group_id,
                created_at=datetime.now(timezone.utc)
            )
            session.add(new_order)
            await session.flush()  # Obtain order.id

            # Create Image entries maintaining position order
            for idx, file_id in enumerate(file_ids):
                img = Image(
                    order_id=new_order.id,
                    telegram_file_id=file_id,
                    position=idx
                )
                session.add(img)

        # Reload with images eagerly loaded
        stmt = select(Order).options(joinedload(Order.images)).where(Order.id == new_order.id)
        res = await session.execute(stmt)
        saved_order = res.unique().scalar_one()

        logger.info(f"New album saved for email: {email} | Images: {len(file_ids)} | Order ID: {saved_order.id}")
        return saved_order, False


async def get_newest_order_by_email(email: str) -> Optional[Order]:
    """
    Retrieves the newest Order matching the specified email address, with images eagerly loaded.

    Args:
        email (str): Target email address.

    Returns:
        Optional[Order]: Matching Order or None if not found.
    """
    email_clean = email.lower().strip()
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.email == email_clean)
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.unique().scalar_one_or_none()


async def get_all_orders_by_email(email: str) -> List[Order]:
    """
    Retrieves all Orders matching the specified email address.

    Args:
        email (str): Target email address.

    Returns:
        List[Order]: List of Order records.
    """
    email_clean = email.lower().strip()
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.email == email_clean)
            .order_by(Order.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.unique().scalars().all())


async def delete_orders_by_email(email: str) -> int:
    """
    Deletes all records associated with a specific email address.

    Args:
        email (str): Target email address.

    Returns:
        int: Number of deleted order records.
    """
    email_clean = email.lower().strip()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Get orders to delete
            stmt = select(Order.id).where(Order.email == email_clean)
            res = await session.execute(stmt)
            order_ids = list(res.scalars().all())

            if not order_ids:
                return 0

            # Delete orders (Cascades to images)
            del_stmt = delete(Order).where(Order.id.in_(order_ids))
            result = await session.execute(del_stmt)
            count = result.rowcount
            logger.info(f"Deleted {count} order(s) for email: {email_clean}")
            return count


async def get_stats() -> Dict[str, Any]:
    """
    Computes system statistics for the /stats command dashboard.

    Returns:
        Dict[str, Any]: Dictionary of stats including orders, images, unique emails.
    """
    async with AsyncSessionLocal() as session:
        total_orders_res = await session.execute(select(func.count(Order.id)))
        total_orders = total_orders_res.scalar() or 0

        total_images_res = await session.execute(select(func.count(Image.id)))
        total_images = total_images_res.scalar() or 0

        unique_emails_res = await session.execute(select(func.count(func.distinct(Order.email))))
        unique_emails = unique_emails_res.scalar() or 0

        oldest_res = await session.execute(select(func.min(Order.created_at)))
        oldest_date = oldest_res.scalar()

        return {
            "total_orders": total_orders,
            "total_images": total_images,
            "unique_emails": unique_emails,
            "oldest_order_date": oldest_date.strftime("%Y-%m-%d %H:%M:%S UTC") if oldest_date else "N/A"
        }


async def cleanup_old_records(days: int) -> int:
    """
    Deletes records older than the specified number of days.

    Args:
        days (int): Retention period threshold in days.

    Returns:
        int: Number of deleted records.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = delete(Order).where(Order.created_at < cutoff)
            result = await session.execute(stmt)
            count = result.rowcount
            if count > 0:
                logger.info(f"Automatic cleanup: Deleted {count} order(s) older than {days} days.")
            return count
