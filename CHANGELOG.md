# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.18.0] - 2026-08-09

### Fixed & Changed
- **Telegram BotCommand Menu Registration Fix**:
  - Replaced uppercase commands in `BotCommand` registration (`"A"` and `"B"`) with lowercase commands (`"a"` and `"b"`) to comply with Telegram API rules.
  - Retained full backward compatibility for command handlers accepting both lowercase and uppercase aliases: `CommandHandler(["a", "A"], category_a_command)` and `CommandHandler(["b", "B"], category_b_command)`.
  - Added pre-registration validation (`validate_bot_command`) verifying command names match `^[a-z0-9_]{1,32}$` and descriptions match `1 <= len <= 256`.
  - Improved command registration exception logging with `logger.exception("[COMMANDS] Failed to register bot commands.")` for full stack trace visibility.
  - Cleaned up Telegram `/` popup menu to display only 19 primary commands while keeping maintenance commands functional via direct typing.

## [1.17.0] - 2026-08-09

### Added & Changed
- **Multi-Loader Approval System (Category B v2)**:
  - Implemented `Loader` declarative model and `loaders` database table.
  - Category B interactive button workflow (`[✅ Accept]`, `[❌ Reject]`, `Select Loader` dynamic menu, `[❌ Cancel]`).
  - Added `/loaderadd`, `/loaderlist`, and `/loaderremove` admin commands.

## [1.16.0] - 2026-08-09

### Changed
- **Fixed Payment Review Group Constant (`-1004441603990`)**:
  - Configured fixed default Payment Review Group Chat ID `PAYMENT_REVIEW_GROUP_ID = -1004441603990` in `config.py`.

## [1.15.0] - 2026-08-09

### Added & Changed
- **Group Category Routing System (v1.2)**:
  - Added `ClientGroup` model and `client_groups` database table.

## [1.14.0] - 2026-08-09

### Changed
- **Removed Non-Reply & Unmatched Reply Warning Messages in Loader Group**:
  - Replaced error cards with silent logging: `[LOADER] Ignored non-reply message.` and `[LOADER] Ignored reply that does not match any active order.`

## [1.13.0] - 2026-08-09

### Added & Changed
- **Ignore Super Admin & Delivery User Messages in Client Group**:
  - Messages from Super Admins and Delivery Users in Client Group are ignored completely without order processing.

## [1.12.0] - 2026-08-09

### Added & Changed
- **Role-Based User Management (`authorized_users`)**:
  - Implemented `AuthorizedUser` model and user management commands (`/user`, `/users`).

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
