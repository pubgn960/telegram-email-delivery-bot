"""
Database manager providing asynchronous SQLAlchemy 2.0 session management, CRUD operations,
SHA256 fingerprint deduplication, CSV export, backup/restore, and dynamic Settings management.
"""

import os
import io
import csv
import shutil
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from config import Config
from models import Base, Order, Image, Settings

logger = logging.getLogger(__name__)

# Extra connect_args for SQLite to prevent locking under concurrency
engine_args: Dict[str, Any] = {"echo": False, "future": True}
if Config.DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"timeout": 30}

# SQLAlchemy Async Engine initialization
engine = create_async_engine(Config.DATABASE_URL, **engine_args)

# Async Session Maker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def dispose_engine() -> None:
    """Disposes active database engine connection pool."""
    logger.info("Disposing database connection engine...")
    await engine.dispose()


def compute_fingerprint(email: str, file_ids: List[str]) -> str:
    """
    Computes a unique SHA256 fingerprint for an upload.
    Formula: SHA256(email + image_count + sorted_file_ids)
    """
    email_clean = email.lower().strip()
    count_str = str(len(file_ids))
    sorted_ids = "".join(sorted(file_ids))
    raw_payload = f"{email_clean}:{count_str}:{sorted_ids}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


async def init_db() -> None:
    """Initializes the database schema and ensures single Settings record exists."""
    logger.info("Initializing database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized successfully.")

    # Initialize single Settings record if missing
    await get_or_create_settings()


# ==========================================
# Dynamic Settings Operations
# ==========================================

async def get_or_create_settings() -> Settings:
    """
    Retrieves or initializes the single Settings record (id=1).
    Avoids nested session.begin() calls to prevent transaction conflicts.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Settings).where(Settings.id == 1)
        res = await session.execute(stmt)
        settings = res.scalar_one_or_none()

        if not settings:
            settings = Settings(
                id=1,
                source_group_id=None,
                source_group_title=None,
                delivery_group_id=None,
                delivery_group_title=None,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            logger.info("Initialized default Settings record in database.")

        return settings


async def get_current_settings() -> Settings:
    """Retrieves current Settings record from database."""
    return await get_or_create_settings()


async def update_source_group(chat_id: int, title: str) -> Settings:
    """Updates the Source Group configuration in database."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Settings)
            .where(Settings.id == 1)
            .values(
                source_group_id=chat_id,
                source_group_title=title,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()

        res = await session.execute(select(Settings).where(Settings.id == 1))
        settings = res.scalar_one()
        logger.info(f"Source Group updated in DB: ID={chat_id}, Title='{title}'")
        return settings


async def update_delivery_group(chat_id: int, title: str) -> Settings:
    """Updates the Delivery Group configuration in database."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Settings)
            .where(Settings.id == 1)
            .values(
                delivery_group_id=chat_id,
                delivery_group_title=title,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()

        res = await session.execute(select(Settings).where(Settings.id == 1))
        settings = res.scalar_one()
        logger.info(f"Delivery Group updated in DB: ID={chat_id}, Title='{title}'")
        return settings


async def remove_source_group() -> Settings:
    """Removes Source Group configuration from database."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Settings)
            .where(Settings.id == 1)
            .values(
                source_group_id=None,
                source_group_title=None,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()

        res = await session.execute(select(Settings).where(Settings.id == 1))
        settings = res.scalar_one()
        logger.info("Source Group configuration removed from DB.")
        return settings


async def remove_delivery_group() -> Settings:
    """Removes Delivery Group configuration from database."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Settings)
            .where(Settings.id == 1)
            .values(
                delivery_group_id=None,
                delivery_group_title=None,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()

        res = await session.execute(select(Settings).where(Settings.id == 1))
        settings = res.scalar_one()
        logger.info("Delivery Group configuration removed from DB.")
        return settings


async def reset_groups() -> Settings:
    """Resets both Source and Delivery Group configurations in database."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Settings)
            .where(Settings.id == 1)
            .values(
                source_group_id=None,
                source_group_title=None,
                delivery_group_id=None,
                delivery_group_title=None,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await session.execute(stmt)
        await session.commit()

        res = await session.execute(select(Settings).where(Settings.id == 1))
        settings = res.scalar_one()
        logger.info("All Group settings reset in DB.")
        return settings


# ==========================================
# Order & Image Operations
# ==========================================

async def save_order(
    email: str,
    file_items: List[Tuple[str, str]],
    media_group_id: Optional[str] = None
) -> Tuple[Optional[Order], bool]:
    """Saves a new Order and images using SHA256 fingerprint duplicate suppression."""
    if not file_items:
        return None, False

    email_clean = email.lower().strip()
    file_ids = [item[0] for item in file_items]
    fingerprint = compute_fingerprint(email_clean, file_ids)

    async with AsyncSessionLocal() as session:
        # Check 1: Fingerprint duplicate check
        fp_stmt = select(Order).where(Order.fingerprint == fingerprint)
        fp_res = await session.execute(fp_stmt)
        if fp_res.scalar_one_or_none():
            logger.info(f"Duplicate upload detected via SHA256 fingerprint ({fingerprint[:10]}...). Skipped.")
            return None, True

        # Check 2: Media group ID duplicate check
        if media_group_id:
            mg_stmt = select(Order).where(Order.media_group_id == media_group_id)
            mg_res = await session.execute(mg_stmt)
            if mg_res.scalar_one_or_none():
                logger.info(f"Duplicate upload detected via media_group_id ({media_group_id}). Skipped.")
                return None, True

        # Create new order
        new_order = Order(
            email=email_clean,
            media_group_id=media_group_id,
            fingerprint=fingerprint,
            created_at=datetime.now(timezone.utc)
        )
        session.add(new_order)
        await session.flush()

        # Add Image records
        for idx, (file_id, file_type) in enumerate(file_items):
            img = Image(
                order_id=new_order.id,
                telegram_file_id=file_id,
                file_type=file_type,
                position=idx
            )
            session.add(img)

        await session.commit()

        # Reload with images eagerly loaded
        res = await session.execute(
            select(Order).options(joinedload(Order.images)).where(Order.id == new_order.id)
        )
        saved_order = res.unique().scalar_one()

        logger.info(f"New Order saved | ID: {saved_order.id} | Email: {email_clean} | Images: {len(file_items)}")
        return saved_order, False


async def get_newest_order_by_email(email: str) -> Optional[Order]:
    """Retrieves newest Order for email with images loaded."""
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
    """Retrieves all Orders for email."""
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


async def mark_order_delivered(order_id: int) -> None:
    """Updates delivered_at timestamp for an order."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(delivered_at=datetime.now(timezone.utc))
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Order {order_id} marked as delivered.")


async def get_pending_orders() -> List[Order]:
    """Retrieves all orders that have not yet been delivered (delivered_at IS NULL)."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.delivered_at.is_(None))
            .order_by(Order.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.unique().scalars().all())


async def delete_orders_by_email(email: str) -> int:
    """Deletes all orders matching email."""
    email_clean = email.lower().strip()
    async with AsyncSessionLocal() as session:
        stmt = select(Order.id).where(Order.email == email_clean)
        res = await session.execute(stmt)
        ids = list(res.scalars().all())

        if not ids:
            return 0

        del_stmt = delete(Order).where(Order.id.in_(ids))
        result = await session.execute(del_stmt)
        await session.commit()
        count = result.rowcount
        logger.info(f"Deleted {count} order(s) for email: {email_clean}")
        return count


async def get_stats() -> Dict[str, Any]:
    """Computes bot statistics dashboard."""
    async with AsyncSessionLocal() as session:
        total_orders = (await session.execute(select(func.count(Order.id)))).scalar() or 0
        total_images = (await session.execute(select(func.count(Image.id)))).scalar() or 0
        unique_emails = (await session.execute(select(func.count(func.distinct(Order.email))))).scalar() or 0
        pending_orders = (await session.execute(select(func.count(Order.id)).where(Order.delivered_at.is_(None)))).scalar() or 0
        oldest_date = (await session.execute(select(func.min(Order.created_at)))).scalar()

        return {
            "total_orders": total_orders,
            "total_images": total_images,
            "unique_emails": unique_emails,
            "pending_orders": pending_orders,
            "oldest_order_date": oldest_date.strftime("%Y-%m-%d %H:%M:%S UTC") if oldest_date else "N/A"
        }


async def cleanup_old_records(days: int) -> int:
    """Deletes orders older than days threshold."""
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        stmt = delete(Order).where(Order.created_at < cutoff)
        res = await session.execute(stmt)
        await session.commit()
        count = res.rowcount
        if count > 0:
            logger.info(f"Storage Retention: Purged {count} order(s) older than {days} days.")
        return count


async def export_orders_to_csv() -> str:
    """Generates CSV formatted string containing all orders export data using standard csv module."""
    async with AsyncSessionLocal() as session:
        stmt = select(Order).options(joinedload(Order.images)).order_by(Order.created_at.desc())
        res = await session.execute(stmt)
        orders = res.unique().scalars().all()

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["Email", "Images", "Created", "Delivered"])

        for o in orders:
            created_str = o.created_at.strftime("%Y-%m-%d %H:%M:%S")
            delivered_str = o.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if o.delivered_at else "Pending"
            writer.writerow([o.email, len(o.images), created_str, delivered_str])

        return output.getvalue()


async def get_db_file_path() -> Optional[str]:
    """Helper to get SQLite database file path if using SQLite."""
    if Config.DATABASE_URL.startswith("sqlite"):
        path = Config.DATABASE_URL.split("///")[-1]
        if os.path.exists(path):
            return path
    return None
