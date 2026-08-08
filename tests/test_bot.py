"""
Unit test suite for Telegram Email Image Delivery Bot.
Tests email extraction, album splitting, SHA256 fingerprinting, user sessions,
and dynamic DB-backed Settings / Group configuration CRUD.
"""

import unittest
import asyncio
from email_parser import extract_email
from delivery import chunk_list
from media_collector import user_session_manager
from database import (
    init_db,
    save_order,
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


class TestEmailParser(unittest.TestCase):
    """Tests email extraction and normalization."""

    def test_extract_basic_email(self):
        text = "Order confirmation for john@gmail.com please deliver."
        self.assertEqual(extract_email(text), "john@gmail.com")

    def test_case_insensitivity_and_trimming(self):
        text = "Customer Email:   JOHN.DOE@EXAMPLE.CO.UK  "
        self.assertEqual(extract_email(text), "john.doe@example.co.uk")

    def test_no_email_returns_none(self):
        text = "Here are the product pictures for the invoice."
        self.assertIsNone(extract_email(text))

    def test_multiline_caption(self):
        text = "Order #12345\nContact: user_name@domain.org\nThank you!"
        self.assertEqual(extract_email(text), "user_name@domain.org")


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


class TestSettingsAndDatabase(unittest.IsolatedAsyncioTestCase):
    """Async tests for database Settings CRUD and Order operations."""

    async def test_settings_lifecycle(self):
        await init_db()

        # 1. Get or create initial settings
        settings = await get_or_create_settings()
        self.assertEqual(settings.id, 1)

        # 2. Update Source Group
        updated_src = await update_source_group(-1001234567890, "Orders Source Group")
        self.assertEqual(updated_src.source_group_id, -1001234567890)
        self.assertEqual(updated_src.source_group_title, "Orders Source Group")

        # 3. Update Delivery Group
        updated_del = await update_delivery_group(-1009876543210, "Delivery Target Group")
        self.assertEqual(updated_del.delivery_group_id, -1009876543210)
        self.assertEqual(updated_del.delivery_group_title, "Delivery Target Group")

        # 4. Remove Source Group
        rem_src = await remove_source_group()
        self.assertIsNone(rem_src.source_group_id)

        # 5. Remove Delivery Group
        rem_del = await remove_delivery_group()
        self.assertIsNone(rem_del.delivery_group_id)

        # 6. Reset all groups
        reset_res = await reset_groups()
        self.assertIsNone(reset_res.source_group_id)
        self.assertIsNone(reset_res.delivery_group_id)

    async def test_database_order_lifecycle(self):
        await init_db()

        test_email = "db_test@example.com"
        file_items = [("file_1", "photo"), ("file_2", "photo"), ("doc_1", "document")]

        order, is_dup = await save_order(test_email, file_items, media_group_id="mg_test_99")
        self.assertFalse(is_dup)
        self.assertIsNotNone(order)

        pending = await get_pending_orders()
        self.assertTrue(any(o.id == order.id for o in pending))

        await mark_order_delivered(order.id)
        newest = await get_newest_order_by_email(test_email)
        self.assertIsNotNone(newest.delivered_at)

        csv_text = await export_orders_to_csv()
        self.assertIn("db_test@example.com", csv_text)

        count = await delete_orders_by_email(test_email)
        self.assertGreaterEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
