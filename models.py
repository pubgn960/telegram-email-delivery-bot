"""
SQLAlchemy ORM models for Telegram Email Image Delivery Bot.
Defines schema for Orders and Images tables.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""
    pass


class Order(Base):
    """
    Represents an order (a collection of images associated with an email address).
    Can originate from a Telegram Media Group (Album) or a single photo.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    media_group_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # One-to-many relationship with Image records
    images: Mapped[List["Image"]] = relationship(
        "Image",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="Image.position"
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, email='{self.email}', media_group_id='{self.media_group_id}', images_count={len(self.images)})>"


class Image(Base):
    """
    Represents an individual image stored within an order.
    Stores only the Telegram file_id (never downloads the physical file).
    """

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Many-to-one relationship back to Order
    order: Mapped["Order"] = relationship("Order", back_populates="images")

    def __repr__(self) -> str:
        return f"<Image(id={self.id}, order_id={self.order_id}, position={self.position})>"


# Index on email and created_at for fast querying of newest records
Index("idx_orders_email_created", Order.email, Order.created_at.desc())
