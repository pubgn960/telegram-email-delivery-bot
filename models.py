"""
SQLAlchemy 2 Async declarative models for Telegram Email Image Delivery Bot.
Defines schemas and indexes for Orders, Images, and Settings tables supporting two-group reply-based workflow.
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base model class."""
    pass


class Settings(Base):
    """
    Stores dynamic application settings and group configurations.
    Maintains a single record (id=1).
    source_group_id: Client Group ID (where customers send orders)
    delivery_group_id: Loader Group ID (where bot forwards orders & loaders reply)
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    source_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    source_group_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    delivery_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    delivery_group_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<Settings(id={self.id}, client_group={self.source_group_id}, loader_group={self.delivery_group_id})>"


class Order(Base):
    """
    Represents an Order record in the two-group reply-based workflow.
    Tracks client message, forwarded loader message, status, package details, and stored image file_ids.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    package: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    original_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    loader_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending", index=True)  # Pending, Delivered, Cancelled, Expired
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    media_group_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    # Relationship to images ordered by position
    images: Mapped[List["Image"]] = relationship(
        "Image",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="Image.position"
    )

    def __repr__(self) -> str:
        img_count = len(self.__dict__['images']) if 'images' in self.__dict__ else self.image_count
        return f"<Order(id={self.id}, email='{self.email}', status='{self.status}', images={img_count})>"


class Image(Base):
    """
    Represents an individual image stored within an order.
    Supports photos and photo documents. Stores telegram file_id only.
    """

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False, default="photo")  # 'photo' or 'document'
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Many-to-one relationship to Order
    order: Mapped["Order"] = relationship("Order", back_populates="images")

    def __repr__(self) -> str:
        return f"<Image(id={self.id}, order_id={self.order_id}, file_type='{self.file_type}', position={self.position})>"


# Compound index for email + creation timestamp queries
Index("idx_orders_email_created_desc", Order.email, Order.created_at.desc())
