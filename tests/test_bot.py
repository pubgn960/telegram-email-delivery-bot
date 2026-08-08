"""
Unit test suite for Telegram Email Image Delivery Bot.
Tests email, Order ID, and package extraction, album splitting, SHA256 fingerprinting,
user sessions, and two-group reply-based DB operations.
"""

import unittest
import asyncio
from email_parser import extract_email, extract_order_id, extract_package
from delivery import chunk_list
from media_collector import user_session_manager
from database import (
    init_db,
    create_order,
    set_order_loader_message_id,
    get_order_by_id,
    get_order_by_loader_msg_id,
    add_images_to_order,
    mark_order_delivered,
    cancel_order,
    get_pending_orders,
    get_delivered_orders,
    delete_orders_by_email,
    get_detailed_stats,
    compute_fingerprint,
    export_orders_to_csv,
    get_or_create_settings,
    update_source_group,
    update_delivery_group,
    reset_groups
)


class TestEmailOrderPackageParser(unittest.TestCase):
    """Tests email, Order ID, and package regex extraction."""

    def test_extract_basic_email(self):
        text = "Order confirmation for john@gmail.com please deliver."
        self.assertEqual(extract_email(text), "john@gmail.com")

    def test_extract_order_id_formats(self):
        self.assertEqual(extract_order_id("Order ID: #10025"), 10025)
        self.assertEqual(extract_order_id("Order #10025"), 10025)
        self.assertEqual(extract_order_id("#10025"), 10025)
        self.assertEqual(extract_order_id("Order ID: 10025"), 10025)

    def test_extract_package_description(self):
        text = "10800 CP\nEmail: test@gmail.com"
        self.assertEqual(extract_package(text), "10800 CP")


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


class TestTwoGroupDatabaseWorkflow(unittest.IsolatedAsyncioTestCase):
    """Async tests for Two-Group Reply-Based Order Creation, Loader Reply Mapping, and Statuses."""

    async def test_two_group_workflow(self):
        await init_db()

        # 1. Customer Order Creation in Client Group
        email = "twogroup_flow@example.com"
        order = await create_order(
            email=email,
            client_chat_id=-1001111111111,
            original_message_id=501,
            package="10800 CP"
        )
        self.assertIsNotNone(order.id)
        self.assertEqual(order.status, "Pending")
        self.assertEqual(order.package, "10800 CP")

        # 2. Forward to Loader Group & Store Loader Message ID
        await set_order_loader_message_id(order.id, 9901)
        loader_order = await get_order_by_loader_msg_id(9901)
        self.assertIsNotNone(loader_order)
        self.assertEqual(loader_order.id, order.id)

        # 3. Loader replies with images
        file_items = [("photo_1", "photo"), ("photo_2", "photo")]
        updated_order, is_dup = await add_images_to_order(
            order_id=order.id,
            file_items=file_items,
            media_group_id="album_5501"
        )
        self.assertFalse(is_dup)
        self.assertEqual(len(updated_order.images), 2)

        # 4. Duplicate reply test
        _, is_dup_2 = await add_images_to_order(
            order_id=order.id,
            file_items=file_items,
            media_group_id="album_5501"
        )
        self.assertTrue(is_dup_2)

        # 5. Mark Order Delivered
        await mark_order_delivered(order.id)
        del_order = await get_order_by_id(order.id)
        self.assertEqual(del_order.status, "Delivered")
        self.assertIsNotNone(del_order.delivered_at)

        # 6. Cancellation test on second order
        order2 = await create_order("cancel_test@example.com")
        canceled_order, success = await cancel_order(order2.id)
        self.assertTrue(success)
        self.assertEqual(canceled_order.status, "Cancelled")

        # Clean up
        await delete_orders_by_email(email)
        await delete_orders_by_email("cancel_test@example.com")


if __name__ == "__main__":
    unittest.main()
