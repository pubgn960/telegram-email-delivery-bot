"""
Unit test suite for Telegram Email Image Delivery Bot.
Tests email extraction, album splitting (8, 18, 35, 100+ items), SHA256 fingerprinting,
user session fallback, and database CRUD & CSV export operations.
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
    export_orders_to_csv
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

    def test_chunking_hundred_plus_images(self):
        images = [f"file_id_{i}" for i in range(105)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 11)
        self.assertEqual(len(chunks[-1]), 5)


class TestUserSessionManager(unittest.TestCase):
    """Tests 5-minute user session tracking."""

    def test_session_creation_and_retrieval(self):
        user_id = 999123
        email = "session_user@example.com"

        user_session_manager.update_session(user_id, email)
        retrieved = user_session_manager.get_session_email(user_id)
        self.assertEqual(retrieved, email)


class TestFingerprintAndDatabase(unittest.IsolatedAsyncioTestCase):
    """Async tests for database CRUD, SHA256 fingerprinting, and CSV export."""

    async def test_fingerprint_generation(self):
        email = "test.user@example.com"
        files_a = ["file_a", "file_b"]
        files_b = ["file_b", "file_a"]

        fp_a = compute_fingerprint(email, files_a)
        fp_b = compute_fingerprint(email, files_b)
        self.assertEqual(fp_a, fp_b)  # Order agnostic fingerprinting

    async def test_database_lifecycle(self):
        await init_db()

        test_email = "db_test@example.com"
        file_items = [("file_1", "photo"), ("file_2", "photo"), ("doc_1", "document")]

        # 1. Save new order
        order, is_dup = await save_order(test_email, file_items, media_group_id="mg_test_99")
        self.assertFalse(is_dup)
        self.assertIsNotNone(order)
        self.assertEqual(order.email, test_email)

        # 2. Check fingerprint duplicate detection
        dup_order, is_dup_flag = await save_order(test_email, file_items, media_group_id="mg_test_diff")
        self.assertTrue(is_dup_flag)

        # 3. Query pending orders
        pending = await get_pending_orders()
        self.assertTrue(any(o.id == order.id for o in pending))

        # 4. Mark delivered
        await mark_order_delivered(order.id)
        newest = await get_newest_order_by_email(test_email)
        self.assertIsNotNone(newest.delivered_at)

        # 5. Export CSV
        csv_text = await export_orders_to_csv()
        self.assertIn("db_test@example.com", csv_text)

        # 6. Delete order
        count = await delete_orders_by_email(test_email)
        self.assertGreaterEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
