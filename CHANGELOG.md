# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.14.0] - 2026-08-09

### Changed
- **Removed Non-Reply & Unmatched Reply Warning Messages in Loader Group**:
  - Removed chat error messages (`❌ Please reply to the original order message.`) when staff send non-reply messages or chat in the Loader Group.
  - Replaced with silent logging: `[LOADER] Ignored non-reply message.`
  - Removed chat error messages when a reply does not match any active order in DB.
  - Replaced with silent logging: `[LOADER] Ignored reply that does not match any active order.`
  - Valid order replies continue to collect images, process `wrong` status, deliver images to customer, update database, and set reactions.

## [1.13.0] - 2026-08-09

### Added & Changed
- **Ignore Super Admin & Delivery User Messages in Client Group**:
  - Super Admin (`1573531032`) and Delivery User (`1078400998`, `1858358195`) messages in Client Group are ignored completely without keyword detection, order creation, or database saves.
  - Logs: `[CLIENT] Ignored Super Admin message. User ID: 1573531032` and `[CLIENT] Ignored Delivery User message. User ID: <user_id>`.

## [1.12.0] - 2026-08-09

### Added & Changed
- **Role-Based User Management (`authorized_users`)**:
  - Implemented `AuthorizedUser` model and `authorized_users` database table.
  - Super Admin commands: `/user delivery add <user_id>`, `/user delivery remove <user_id>`, `/users`.

## [1.11.0] - 2026-08-09

### Added & Changed
- **Customer Edited Order Message Handling**: Direct reply: `This order will be placed again manually wait for team`.

## [1.10.0] - 2026-08-09

### Added & Changed
- **Duplicate Order Prompt & Confirmation**: Interactive inline keyboard prompt (`⚠️ Duplicate Order Detected`).

## [1.9.0] - 2026-08-08

### Added & Changed
- **Email as First Image Album Caption**: Email address set as caption of the **FIRST image** in delivered albums.

## [1.8.0] - 2026-08-08

### Added & Changed
- **Removed Delivery Summary Card**: Removed extra completion summary card.
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
