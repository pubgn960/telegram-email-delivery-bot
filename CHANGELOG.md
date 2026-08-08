# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.13.0] - 2026-08-09

### Added & Changed
- **Ignore Super Admin & Delivery User Messages in Client Group**:
  - Updated `source_group_handler` and `edited_message_handler` to filter out messages sent by Super Admins (`is_super_admin(user_id)`) and Delivery Users (`is_delivery_user(user_id)`).
  - Super Admin messages in Client Group are ignored completely without keyword detection, order creation, forwarding, duplicate checking, or database modification.
    - Logged: `[CLIENT] Ignored Super Admin message. User ID: 1573531032`
  - Delivery User messages in Client Group are ignored completely.
    - Logged: `[CLIENT] Ignored Delivery User message. User ID: <user_id>`
  - Only messages from normal customers (not Super Admin and not Delivery User) are processed by the order detection workflow.

## [1.12.0] - 2026-08-09

### Added & Changed
- **Role-Based User Management (`authorized_users`)**:
  - Implemented `AuthorizedUser` model and `authorized_users` database table storing user IDs, roles (`'admin'` or `'delivery'`), and timestamps.
  - Super Admin (`1573531032`) has full access to all bot commands, configuration, database management, statistics, and user management.
  - Seeded default Delivery Users (`1078400998`, `1858358195`).
- **New Super Admin Commands**:
  - `/user delivery add <telegram_user_id>`: Adds a delivery user.
  - `/user delivery remove <telegram_user_id>`: Removes a delivery user.
  - `/users`: Displays list of Super Admins and Delivery Users.

## [1.11.0] - 2026-08-09

### Added & Changed
- **Customer Edited Order Message Handling**: Added `edited_message_handler` to monitor message edits in the Client Group (`filters.UpdateType.EDITED_MESSAGE`). When a customer edits an existing order message, the bot replies directly: `This order will be placed again manually wait for team`.

## [1.10.0] - 2026-08-09

### Added & Changed
- **Duplicate Order Prompt & Confirmation**: Interactive inline keyboard prompt (`⚠️ Duplicate Order Detected`) when a customer submits duplicate pending orders.

## [1.9.0] - 2026-08-08

### Added & Changed
- **Email as First Image Album Caption**: Email address set as caption of the **FIRST image** in delivered albums. No separate text message afterward.

## [1.8.0] - 2026-08-08

### Added & Changed
- **Removed Delivery Summary Card**: Removed extra completion summary card.
- **Caption Email Override**: Support for extracting email overrides from Loader reply captions.
- **Wrong Details Workflow**: Support for Loader text reply `wrong` to notify customer.

## [1.7.0] - 2026-08-08

### Refactored & Changed
- **Global In-Memory `BOT_SETTINGS` Cache**: Zero-database-query message filtering in RAM.

## [1.6.0] - 2026-08-08

### Added & Changed
- **Keyword-Based Order Detection**: Configurable keyword list in `keywords.py`.

## [1.5.0] - 2026-08-08

### Added & Changed
- **Exact Message Copying**: `copy_message` without added metadata.

## [1.4.0] - 2026-08-08

### Added & Changed
- **Updated Reaction Rules**: `👍` on order received, `❤️` on loader reply, `❤️` on customer delivery.

## [1.3.0] - 2026-08-08

### Added & Changed
- **Privacy Protection**: Removed customer names/usernames.

## [1.2.0] - 2026-08-08

### Added & Changed
- **Two-Group Architecture**: Group 1 (Client Group) and Group 2 (Loader Group).

## [1.1.0] - 2026-08-08

### Added & Changed
- **Reply-Based Delivery Workflow**: Explicit Reply-Based Order Mapping.

## [1.0.0] - 2026-08-08

### Added
- **Initial Bot Release**: SQLAlchemy 2.0 Async layer, Railway deployment configuration.
