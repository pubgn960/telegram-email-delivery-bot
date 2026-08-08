"""
Unit tests for Telegram Email Image Delivery Bot.
Uses standard library unittest and asyncio for execution.
"""

import unittest
import asyncio
from email_parser import extract_email
from delivery import chunk_list
from database import init_db, save_order, get_newest_order_by_email, delete_orders_by_email, get_stats


class TestEmailParser(unittest.TestCase):
    """Tests for regex email extraction and normalization."""

    def test_extract_basic_email(self):
        text = "Order confirmation for john@gmail.com please deliver."
        self.assertEqual(extract_email(text), "john@gmail.com")

    def test_case_insensitivity_and_trimming(self):
        text = "Customer Email:   JOHN.DOE@EXAMPLE.CO.UK  "
        self.assertEqual(extract_email(text), "john.doe@example.co.uk")

    def test_no_email_returns_none(self):
        text = "Here are the product pictures for the invoice."
        self.assertIsNone(extract_email(text))

    def test_multiline_caption_extraction(self):
        text = "Order #12345\nItems: 5\nContact: user_name@domain.org\nThank you!"
        self.assertEqual(extract_email(text), "user_name@domain.org")


class TestDeliverySplitting(unittest.TestCase):
    """Tests media group album splitting logic (max 10 items per album)."""

    def test_chunking_six_images(self):
        images = [f"file_id_{i}" for i in range(6)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 6)

    def test_chunking_eighteen_images(self):
        images = [f"file_id_{i}" for i in range(18)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 10)
        self.assertEqual(len(chunks[1]), 8)

    def test_chunking_thirty_five_images(self):
        images = [f"file_id_{i}" for i in range(35)]
        chunks = chunk_list(images, chunk_size=10)
        self.assertEqual(len(chunks), 4)
        self.assertEqual([len(c) for c in chunks], [10, 10, 10, 5])


class TestDatabaseOperations(unittest.IsolatedAsyncioTestCase):
    """Async tests for database operations."""

    async def test_database_crud(self):
        await init_db()

        test_email = "test.user@example.com"
        file_ids = ["file_id_1", "file_id_2", "file_id_3"]
        media_group_id = "test_mg_1001"

        # 1. Save new order
        order, is_dup = await save_order(test_email, file_ids, media_group_id)
        self.assertFalse(is_dup)
        self.assertIsNotNone(order)
        self.assertEqual(order.email, test_email)
        self.assertEqual(len(order.images), 3)

        # 2. Save duplicate order
        dup_order, is_dup_2 = await save_order(test_email, file_ids, media_group_id)
        self.assertTrue(is_dup_2)

        # 3. Retrieve newest order
        retrieved = await get_newest_order_by_email(test_email)
        self.assertIsNotNone(retrieved)
        self.assertEqual(len(retrieved.images), 3)
        self.assertEqual([img.telegram_file_id for img in retrieved.images], file_ids)

        # 4. Check Stats
        stats = await get_stats()
        self.assertGreaterEqual(stats["total_orders"], 1)
        self.assertGreaterEqual(stats["total_images"], 3)

        # 5. Delete order
        deleted_count = await delete_orders_by_email(test_email)
        self.assertEqual(deleted_count, 1)


if __name__ == "__main__":
    unittest.main()
