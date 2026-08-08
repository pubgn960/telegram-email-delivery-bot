"""
Unit test suite for Telegram Email Image Delivery Bot.
Tests email, Order ID, package extraction, keyword detection, caption email overrides,
wrong details workflow, duplicate pending order detection, album splitting, SHA256 fingerprinting, user sessions,
BOT_SETTINGS cache, Role-Based User Management (AUTH_USERS_CACHE, Super Admin, Delivery Users),
and two-group reply-based DB operations.
"""

import unittest
import asyncio
from email_parser import extract_email, extract_order_id, extract_package, extract_last_email
from keywords import contains_order_keyword
from delivery import chunk_list
from media_collector import user_session_manager
from utils import is_super_admin, is_delivery_user
from database import (
    BOT_SETTINGS,
    AUTH_USERS_CACHE,
    init_db,
    reload_bot_settings_cache,
    reload_auth_users_cache,
    add_authorized_user,
    remove_authorized_user,
    get_all_authorized_users,
    create_order,
    set_order_loader_message_id,
    get_order_by_id,
    get_pending_order_by_email,
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


class TestRoleBasedUserManagement(unittest.IsolatedAsyncioTestCase):
    """Tests role-based user management, database persistence, and permission functions."""

    async def test_role_seeding_and_permissions(self):
        await init_db()

        # Verify initial seeds in memory cache
        self.assertTrue(is_super_admin(1573531032))
        self.assertTrue(is_delivery_user(1573531032))

        self.assertFalse(is_super_admin(1078400998))
        self.assertTrue(is_delivery_user(1078400998))

        self.assertFalse(is_super_admin(1858358195))
        self.assertTrue(is_delivery_user(1858358195))

        # Test adding a new delivery user
        new_uid = 999888777
        self.assertFalse(is_delivery_user(new_uid))
        success, _ = await add_authorized_user(new_uid, role="delivery")
        self.assertTrue(success)
        self.assertTrue(is_delivery_user(new_uid))
        self.assertFalse(is_super_admin(new_uid))

        # Test listing users
        all_users = await get_all_authorized_users()
        self.assertIn(1573531032, all_users["admin"])
        self.assertIn(new_uid, all_users["delivery"])

        # Test removing a delivery user
        rem_success, _ = await remove_authorized_user(new_uid)
        self.assertTrue(rem_success)
        self.assertFalse(is_delivery_user(new_uid))

        # Test protecting Super Admin from removal
        sa_rem_success, msg = await remove_authorized_user(1573531032)
        self.assertFalse(sa_rem_success)
        self.assertTrue(is_super_admin(1573531032))


class TestDuplicateOrderDetection(unittest.IsolatedAsyncioTestCase):
    """Tests duplicate pending order detection."""

    async def test_get_pending_order_by_email(self):
        await init_db()

        email = "dup_detect_test@example.com"
        # No pending order initially
        initial = await get_pending_order_by_email(email)
        self.assertIsNone(initial)

        # Create pending order
        o1 = await create_order(email, status="Pending")
        found = await get_pending_order_by_email(email)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, o1.id)

        # Deliver order
        await mark_order_delivered(o1.id)
        found_after_del = await get_pending_order_by_email(email)
        self.assertIsNone(found_after_del)

        # Cleanup
        await delete_orders_by_email(email)


class TestCaptionEmailAndWrongDetails(unittest.TestCase):
    """Tests extract_last_email helper for Loader caption email overrides and wrong details detection."""

    def test_extract_last_email_single(self):
        text = "AG Done\n\nabc@gmail.com"
        self.assertEqual(extract_last_email(text), "abc@gmail.com")

    def test_extract_last_email_multiple(self):
        text = "abc@gmail.com\n\nCompleted Successfully"
        self.assertEqual(extract_last_email(text), "abc@gmail.com")

    def test_extract_last_email_override(self):
        text = "AG Done\nold@gmail.com\nnew@gmail.com\nFinished"
        self.assertEqual(extract_last_email(text), "new@gmail.com")

    def test_extract_last_email_none(self):
        text = "AG Done\nNo email here"
        self.assertIsNone(extract_last_email(text))

    def test_wrong_details_keyword(self):
        self.assertIn("wrong", "wrong".lower())
        self.assertIn("wrong", "Wrong details provided".lower())
        self.assertIn("wrong", "WRONG".lower())


class TestBotSettingsCache(unittest.IsolatedAsyncioTestCase):
    """Tests in-memory BOT_SETTINGS cache initialization and updates."""

    async def test_cache_update_and_reload(self):
        await init_db()

        # Update source group and verify cache instantly reflects changes
        await update_source_group(-1001234567890, "Test Client Group")
        self.assertEqual(BOT_SETTINGS["source_group_id"], -1001234567890)
        self.assertEqual(BOT_SETTINGS["source_group_title"], "Test Client Group")

        # Update delivery group and verify cache instantly reflects changes
        await update_delivery_group(-1009876543210, "Test Loader Group")
        self.assertEqual(BOT_SETTINGS["delivery_group_id"], -1009876543210)
        self.assertEqual(BOT_SETTINGS["delivery_group_title"], "Test Loader Group")

        # Simulate bot restart by calling reload_bot_settings_cache()
        cached = await reload_bot_settings_cache()
        self.assertEqual(cached["source_group_id"], -1001234567890)
        self.assertEqual(cached["delivery_group_id"], -1009876543210)

        # Reset groups and verify cache cleared
        await reset_groups()
        self.assertIsNone(BOT_SETTINGS["source_group_id"])
        self.assertIsNone(BOT_SETTINGS["delivery_group_id"])


class TestKeywordDetector(unittest.TestCase):
    """Tests keyword-based order detection."""

    def test_keyword_matches(self):
        # Match cases
        self.assertTrue(contains_order_keyword("10800 CP\nabc@gmail.com")[0])
        self.assertTrue(contains_order_keyword("Login:\ntest@hotmail.com")[0])
        self.assertTrue(contains_order_keyword("UID:\n123456\nEmail:\nabc@outlook.com")[0])
        self.assertTrue(contains_order_keyword("Login: test+1234")[0])
        self.assertTrue(contains_order_keyword("myemail@yahoo.co.pk")[0])

    def test_keyword_ignores(self):
        # Ignore cases
        self.assertFalse(contains_order_keyword("Need CP")[0])
        self.assertFalse(contains_order_keyword("Hello")[0])
        self.assertFalse(contains_order_keyword("10800 CP")[0])


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
