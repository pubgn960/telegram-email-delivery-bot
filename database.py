"""
Database manager providing asynchronous SQLAlchemy 2.0 session management, CRUD operations,
Order tracking for two-group reply-based workflow, SHA256 fingerprint deduplication, CSV export,
backup/restore, and detailed statistics dashboard.

Supports both PostgreSQL (production via Railway) and SQLite (development).
"""

import os
import io
import csv
import shutil
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, delete, update, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from config import Config
from models import Base, Order, Image, Settings

logger = logging.getLogger(__name__)

# Extra connect_args for SQLite to prevent locking under concurrency
engine_args: Dict[str, Any] = {"echo": False, "future": True}
if Config.DATABASE_URL.startswith("sqlite"):
    engine_args["connect_args"] = {"timeout": 30}
elif Config.DATABASE_URL.startswith("postgresql+asyncpg://"):
    # PostgreSQL specific optimizations
    engine_args["pool_size"] = 10
    engine_args["max_overflow"] = 20
    engine_args["pool_pre_ping"] = True

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
    logger.info("[DB] Disposing database connection engine...")
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


async def verify_db_connection() -> bool:
    """
    Verifies database connectivity by executing a simple query.
    Returns True on success, False on failure.
    """
    try:
        async with engine.connect() as conn:
            if Config.DATABASE_URL.startswith("postgresql+asyncpg://"):
                await conn.execute(text("SELECT 1"))
                logger.info("[DB] PostgreSQL connected.")
            else:
                await conn.execute(text("SELECT 1"))
                logger.info("[DB] SQLite connected.")
        return True
    except Exception as e:
        logger.error(f"[DB] Connection verification failed: {e}")
        return False


async def init_db() -> None:
    """
    Initializes database schema and default Settings record.
    - Verifies connection before proceeding
    - Creates all tables if they don't exist
    - Never recreates or overwrites existing tables
    - Initializes default Settings record if missing
    """
    logger.info("[DB] Initializing database...")
    
    # Verify connection first
    if not await verify_db_connection():
        raise RuntimeError("[DB] Failed to establish database connection")
    
    logger.info("[DB] Creating tables if not exist...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[DB] Tables verified.")
    except Exception as e:
        logger.error(f"[DB] Error creating tables: {e}")
        raise

    # Initialize Settings record
    await get_or_create_settings()
    logger.info("[DB] Settings loaded successfully.")


# ==========================================
# Dynamic Settings Operations
# ==========================================

async def get_or_create_settings() -> Settings:
    """Retrieves or initializes the single Settings record (id=1)."""
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
            logger.info("[DB] Initialized default Settings record in database.")

        return settings


async def get_current_settings() -> Settings:
    """Retrieves current Settings record directly from database."""
    return await get_or_create_settings()


async def update_source_group(chat_id: int, title: str) -> Settings:
    """
    Updates the Source Group (Client Group) configuration in database,
    ensuring exactly one Settings record exists, committing to DB, and reloading.
    """
    logger.info(f"[SOURCE] Saving Source Group...")
    async with AsyncSessionLocal() as session:
        stmt = select(Settings).where(Settings.id == 1)
        res = await session.execute(stmt)
        settings = res.scalar_one_or_none()

        if not settings:
            settings = Settings(
                id=1,
                source_group_id=chat_id,
                source_group_title=title,
                delivery_group_id=None,
                delivery_group_title=None,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(settings)
        else:
            settings.source_group_id = chat_id
            settings.source_group_title = title
            settings.updated_at = datetime.now(timezone.utc)

        await session.commit()
        logger.info("[SOURCE] Database commit successful.")

    # Reload directly from database to verify persistence
    reloaded_settings = await get_current_settings()
    logger.info(f"[SOURCE] Source Group saved: {reloaded_settings.source_group_id}")
    logger.info(f"[SOURCE] Reload successful.")
    return reloaded_settings


async def update_delivery_group(chat_id: int, title: str) -> Settings:
    """
    Updates the Delivery Group (Loader Group) configuration in database,
    ensuring exactly one Settings record exists, committing to DB, and reloading.
    """
    logger.info(f"[DELIVERY_GROUP] Saving Delivery Group...")
    async with AsyncSessionLocal() as session:
        stmt = select(Settings).where(Settings.id == 1)
        res = await session.execute(stmt)
        settings = res.scalar_one_or_none()

        if not settings:
            settings = Settings(
                id=1,
                source_group_id=None,
                source_group_title=None,
                delivery_group_id=chat_id,
                delivery_group_title=title,
                updated_at=datetime.now(timezone.utc)
            )
            session.add(settings)
        else:
            settings.delivery_group_id = chat_id
            settings.delivery_group_title = title
            settings.updated_at = datetime.now(timezone.utc)

        await session.commit()
        logger.info("[DELIVERY_GROUP] Database commit successful.")

    # Reload directly from database to verify persistence
    reloaded_settings = await get_current_settings()
    logger.info(f"[DELIVERY_GROUP] Delivery Group saved: {reloaded_settings.delivery_group_id}")
    logger.info(f"[DELIVERY_GROUP] Reload successful.")
    return reloaded_settings


async def remove_source_group() -> Settings:
    """Removes Client Group configuration from database."""
    async with AsyncSessionLocal() as session:
        stmt = select(Settings).where(Settings.id == 1)
        res = await session.execute(stmt)
        settings = res.scalar_one_or_none()

        if settings:
            settings.source_group_id = None
            settings.source_group_title = None
            settings.updated_at = datetime.now(timezone.utc)
            await session.commit()

    return await get_current_settings()


async def remove_delivery_group() -> Settings:
    """Removes Loader Group configuration from database."""
    async with AsyncSessionLocal() as session:
        stmt = select(Settings).where(Settings.id == 1)
        res = await session.execute(stmt)
        settings = res.scalar_one_or_none()

        if settings:
            settings.delivery_group_id = None
            settings.delivery_group_title = None
            settings.updated_at = datetime.now(timezone.utc)
            await session.commit()

    return await get_current_settings()


async def reset_groups() -> Settings:
    """Resets both Client and Loader Group configurations in database."""
    async with AsyncSessionLocal() as session:
        stmt = select(Settings).where(Settings.id == 1)
        res = await session.execute(stmt)
        settings = res.scalar_one_or_none()

        if settings:
            settings.source_group_id = None
            settings.source_group_title = None
            settings.delivery_group_id = None
            settings.delivery_group_title = None
            settings.updated_at = datetime.now(timezone.utc)
            await session.commit()

    return await get_current_settings()


# ==========================================
# Two-Group Order CRUD & Operations
# ==========================================

async def create_order(
    email: str,
    client_chat_id: Optional[int] = None,
    original_message_id: Optional[int] = None,
    package: str = ""
) -> Order:
    """
    Creates a new Order record in Pending status and returns generated Order object.
    """
    email_clean = email.lower().strip()
    async with AsyncSessionLocal() as session:
        new_order = Order(
            email=email_clean,
            package=package,
            client_chat_id=client_chat_id,
            original_message_id=original_message_id,
            loader_message_id=None,
            status="Pending",
            image_count=0,
            media_group_id=None,
            fingerprint=None,
            created_at=datetime.now(timezone.utc)
        )
        session.add(new_order)
        await session.commit()
        await session.refresh(new_order)

        logger.info(f"New Order | Order ID: #{new_order.id} | Email: {email_clean} | Status: Pending")
        return new_order


async def set_order_loader_message_id(order_id: int, loader_message_id: int) -> None:
    """Updates the forwarded loader message ID for an order."""
    async with AsyncSessionLocal() as session:
        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(loader_message_id=loader_message_id)
        )
        await session.execute(stmt)
        await session.commit()
        logger.info(f"Forwarded Order | Order ID: #{order_id} -> Loader Msg ID: {loader_message_id}")


async def get_order_by_id(order_id: int) -> Optional[Order]:
    """Retrieves an Order by Order ID with images eagerly loaded."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.id == order_id)
        )
        res = await session.execute(stmt)
        return res.unique().scalar_one_or_none()


async def get_order_by_loader_msg_id(loader_msg_id: int) -> Optional[Order]:
    """Retrieves an Order matching loader_message_id with images eagerly loaded."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.loader_message_id == loader_msg_id)
        )
        res = await session.execute(stmt)
        return res.unique().scalar_one_or_none()


async def add_images_to_order(
    order_id: int,
    file_items: List[Tuple[str, str]],
    media_group_id: Optional[str] = None
) -> Tuple[Optional[Order], bool]:
    """
    Adds images to an Order by Order ID using SHA256 fingerprint duplicate protection.

    Returns:
        Tuple[Optional[Order], bool]: (Order object, is_duplicate)
    """
    if not file_items:
        return None, False

    async with AsyncSessionLocal() as session:
        stmt = select(Order).options(joinedload(Order.images)).where(Order.id == order_id)
        res = await session.execute(stmt)
        order = res.unique().scalar_one_or_none()

        if not order:
            logger.warning(f"Attempted to add images to non-existent Order ID: #{order_id}")
            return None, False

        file_ids = [item[0] for item in file_items]
        fingerprint = compute_fingerprint(order.email, file_ids)

        # Check duplicate fingerprint
        fp_stmt = select(Order).where(Order.fingerprint == fingerprint)
        fp_res = await session.execute(fp_stmt)
        if fp_res.scalar_one_or_none():
            logger.info(f"Duplicate Delivery | Fingerprint duplicate for Order ID: #{order_id}")
            return order, True

        # Check duplicate media group ID if present
        if media_group_id and order.media_group_id == media_group_id:
            logger.info(f"Duplicate Delivery | Media group duplicate for Order ID: #{order_id}")
            return order, True

        order.fingerprint = fingerprint
        if media_group_id:
            order.media_group_id = media_group_id

        start_pos = len(order.images)
        for idx, (file_id, file_type) in enumerate(file_items):
            img = Image(
                order_id=order.id,
                telegram_file_id=file_id,
                file_type=file_type,
                position=start_pos + idx
            )
            session.add(img)

        order.image_count = start_pos + len(file_items)
        await session.commit()

        res = await session.execute(
            select(Order).options(joinedload(Order.images)).where(Order.id == order_id)
        )
        updated_order = res.unique().scalar_one()

        logger.info(f"Album Completed | Order ID: #{updated_order.id} | Added: {len(file_items)} | Total: {updated_order.image_count}")
        return updated_order, False


async def mark_order_delivered(order_id: int) -> Optional[Order]:
    """Updates order status to 'Delivered' and sets delivered_at timestamp."""
    async with AsyncSessionLocal() as session:
        now_utc = datetime.now(timezone.utc)
        stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(
                status="Delivered",
                delivered_at=now_utc
            )
        )
        await session.execute(stmt)
        await session.commit()

        res = await session.execute(
            select(Order).options(joinedload(Order.images)).where(Order.id == order_id)
        )
        order = res.unique().scalar_one_or_none()
        logger.info(f"Delivery Completed | Order ID: #{order_id} marked as Delivered.")
        return order


async def cancel_order(order_id: int) -> Tuple[Optional[Order], bool]:
    """Cancels a pending order."""
    async with AsyncSessionLocal() as session:
        stmt = select(Order).options(joinedload(Order.images)).where(Order.id == order_id)
        res = await session.execute(stmt)
        order = res.unique().scalar_one_or_none()

        if not order:
            return None, False

        if order.status == "Cancelled":
            return order, True

        upd_stmt = (
            update(Order)
            .where(Order.id == order_id)
            .values(status="Cancelled")
        )
        await session.execute(upd_stmt)
        await session.commit()

        order.status = "Cancelled"
        logger.info(f"Cancelled Order | Order ID: #{order_id} marked as Cancelled.")
        return order, True


async def get_pending_orders() -> List[Order]:
    """Retrieves all orders in Pending status."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.status == "Pending")
            .order_by(Order.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.unique().scalars().all())


async def get_delivered_orders(limit: int = 15) -> List[Order]:
    """Retrieves latest delivered orders."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Order)
            .options(joinedload(Order.images))
            .where(Order.status == "Delivered")
            .order_by(Order.delivered_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.unique().scalars().all())


async def get_all_orders_by_email(email: str) -> List[Order]:
    """Retrieves all Orders matching an email."""
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


async def check_order_timeouts(timeout_hours: int = 24) -> int:
    """
    Checks for pending orders created longer than timeout_hours ago and marks them Expired.
    """
    if timeout_hours <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=timeout_hours)
    async with AsyncSessionLocal() as session:
        stmt = select(Order).where(Order.status == "Pending", Order.created_at < cutoff)
        res = await session.execute(stmt)
        expired_orders = list(res.scalars().all())

        if not expired_orders:
            return 0

        expired_ids = [o.id for o in expired_orders]
        upd_stmt = (
            update(Order)
            .where(Order.id.in_(expired_ids))
            .values(status="Expired")
        )
        await session.execute(upd_stmt)
        await session.commit()

        for o in expired_orders:
            logger.warning(f"Timeout | Order ID: #{o.id} created at {o.created_at} marked as Expired (⏰ Pending Too Long).")

        return len(expired_ids)


async def get_detailed_stats() -> Dict[str, Any]:
    """Computes comprehensive statistics for the bot dashboard."""
    async with AsyncSessionLocal() as session:
        total_orders = (await session.execute(select(func.count(Order.id)))).scalar() or 0
        pending_orders = (await session.execute(select(func.count(Order.id)).where(Order.status == "Pending"))).scalar() or 0
        delivered_orders = (await session.execute(select(func.count(Order.id)).where(Order.status == "Delivered"))).scalar() or 0
        cancelled_orders = (await session.execute(select(func.count(Order.id)).where(Order.status == "Cancelled"))).scalar() or 0

        # Today's metrics (UTC)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_orders = (await session.execute(select(func.count(Order.id)).where(Order.created_at >= today_start))).scalar() or 0
        today_deliveries = (await session.execute(select(func.count(Order.id)).where(Order.delivered_at >= today_start))).scalar() or 0

        # Calculate Average Delivery Time
        stmt = select(Order.created_at, Order.delivered_at).where(Order.status == "Delivered", Order.delivered_at.isnot(None))
        res = await session.execute(stmt)
        del_times = list(res.all())

        avg_delivery_str = "N/A"
        if del_times:
            durations = [(d_at - c_at).total_seconds() for c_at, d_at in del_times if d_at and c_at]
            if durations:
                avg_seconds = sum(durations) / len(durations)
                if avg_seconds < 60:
                    avg_delivery_str = f"{int(avg_seconds)}s"
                elif avg_seconds < 3600:
                    avg_delivery_str = f"{int(avg_seconds // 60)}m {int(avg_seconds % 60)}s"
                else:
                    avg_delivery_str = f"{round(avg_seconds / 3600, 1)}h"

        return {
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "delivered_orders": delivered_orders,
            "cancelled_orders": cancelled_orders,
            "today_orders": today_orders,
            "today_deliveries": today_deliveries,
            "avg_delivery_time": avg_delivery_str
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
        writer.writerow(["Order ID", "Email", "Package", "Status", "Images", "Created", "Delivered"])

        for o in orders:
            created_str = o.created_at.strftime("%Y-%m-%d %H:%M:%S")
            delivered_str = o.delivered_at.strftime("%Y-%m-%d %H:%M:%S") if o.delivered_at else "Pending"
            writer.writerow([o.id, o.email, o.package or "N/A", o.status, len(o.images), created_str, delivered_str])

        return output.getvalue()


async def get_db_file_path() -> Optional[str]:
    """Helper to get SQLite database file path if using SQLite."""
    if Config.DATABASE_URL.startswith("sqlite"):
        path = Config.DATABASE_URL.split("///")[-1]
        if os.path.exists(path):
            return path
    return None

