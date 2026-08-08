"""
Unit test suite for Telegram Email Image Delivery Bot.
Tests email extraction, Order ID parsing, album splitting, SHA256 fingerprinting,
user sessions, and Reply-Based Delivery Workflow DB operations.
"""

import unittest
import asyncio
from email_parser import extract_email, extract_order_id
from delivery import chunk_list
from media_collector import user_session_manager
from database import (
    init_db,
    create_pending_order,
    get_order_by_id,
    add_images_to_order,
    get_newest_order_by_email,
    mark_order_delivered,
    get_pending_orders,
    delete_orders_by_email,
    get_stats,
    compute_fingerprint,
    export_orders_to_csv,
    get_or_create_settings,
    update_source_group,
    update_delivery_group,
    remove_source_group,
    remove_delivery_group,
    reset_groups
)


class TestEmailAndOrderIdParser(unittest.TestCase):
    """Tests email and Order ID regex extraction."""

    def test_extract_basic_email(self):
        text = "Order confirmation for john@gmail.com please deliver."
        self.assertEqual(extract_email(text), "john@gmail.com")

    def test_case_insensitivity_and_trimming(self):
        text = "Customer Email:   JOHN.DOE@EXAMPLE.CO.UK  "
        self.assertEqual(extract_email(text), "john.doe@example.co.uk")

    def test_extract_order_id_formats(self):
        self.assertEqual(extract_order_id("Order ID: 12345"), 12345)
        self.assertEqual(extract_order_id("Order #998877"), 998877)
        self.assertEqual(extract_order_id("📦 New Order\nEmail: test@example.com\nOrder ID: 5544"), 5544)

    def test_no_order_id_returns_none(self):
        self.assertIsNone(extract_order_id("Here are the images for customer."))


class TestDeliverySplitting(unittest.TestCase):
    """Tests album splitting logic (8, 18, 35, 100+ images)."""

    def test_chunking_eight_images(self):
        images = [f"file_id_{i}" for i in range(8)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 8)

    def test_chunking_eighteen_images(self):
        images = [f"file_id_{i}" for i in range(18)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 2)
        self.assertEqual([len(c) for c in chunks], [10, 8])

    def test_chunking_thirty_five_images(self):
        images = [f"file_id_{i}" for i in range(35)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 4)
        self.assertEqual([len(c) for c in chunks], [10, 10, 10, 5])


class TestUserSessionManager(unittest.TestCase):
    """Tests 5-minute user session tracking."""

    def test_session_creation_and_retrieval(self):
        user_id = 999123
        email = "session_user@example.com"

        user_session_manager.update_session(user_id, email)
        retrieved = user_session_manager.get_session_email(user_id)
        self.assertEqual(retrieved, email)


class TestReplyBasedDatabaseWorkflow(unittest.IsolatedAsyncioTestCase):
    """Async tests for Reply-Based Order Creation, Image Aggregation, and Settings CRUD."""

    async def test_reply_based_order_flow(self):
        await init_db()

        # 1. Customer Order Creation
        email = "reply_flow@example.com"
        order = await create_pending_order(email)
        self.assertIsNotNone(order.id)
        self.assertEqual(order.email, email)

        # 2. Loader replies with photos for Order ID
        file_items = [("photo_1", "photo"), ("photo_2", "photo")]
        updated_order, is_dup = await add_images_to_order(
            order_id=order.id,
            file_items=file_items,
            media_group_id="album_1001"
        )
        self.assertFalse(is_dup)
        self.assertEqual(len(updated_order.images), 2)

        # 3. Loader replies with duplicate album -> should ignore duplicate
        dup_order, is_dup_2 = await add_images_to_order(
            order_id=order.id,
            file_items=file_items,
            media_group_id="album_1001"
        )
        self.assertTrue(is_dup_2)

        # 4. Mark order as delivered
        await mark_order_delivered(order.id)
        fetched = await get_order_by_id(order.id)
        self.assertIsNotNone(fetched.delivered_at)

        # Cleanup
        await delete_orders_by_email(email)


if __name__ == "__main__":
    unittest.main()
