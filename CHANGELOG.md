# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.8.0] - 2026-08-08

### Added & Changed
- **Removed Delivery Summary Card**: Removed the extra completion summary card (`📧 Email ... 📦 Order ID ... ✅ Delivery Completed`) sent after image delivery. Customers receive only images/album and caption email override (if present).
- **Caption Email Override**: If the Loader's reply text/caption contains valid email addresses, `extract_last_email()` extracts the last valid email and sends **ONLY** that email address as a text message to the customer (replying to the original customer message). Non-email caption text (e.g. `AG Done`, `Completed`) is ignored. Database email remains unchanged.
- **Wrong Details Workflow**: When the Loader replies to an order with text or caption containing the word `wrong` (case-insensitive):
  - Sends `❌ Please check and correct your details, then send them again.` to the customer in the Client Group (replying to customer's order).
  - Reacts to the Loader's message with `❌` (fallback `⚠️`).
  - Keeps order status as `Pending` without delivering images or deleting records.

## [1.7.0] - 2026-08-08

### Refactored & Changed
- **Global In-Memory `BOT_SETTINGS` Cache**: Refactored group configuration system to eliminate per-message database queries. Incoming updates in `source_group_handler` and `delivery_group_handler` validate group IDs strictly in RAM using `BOT_SETTINGS["source_group_id"]` and `BOT_SETTINGS["delivery_group_id"]`.
- **Startup Settings Pre-loading**: Added `reload_bot_settings_cache()` in `post_init()`, loading settings from database once during bot startup. Added `[CACHE]` startup logs (`Source Group Loaded: ...`, `Delivery Group Loaded: ...`, or `No groups configured.`).

## [1.6.0] - 2026-08-08

### Added & Changed
- **Keyword-Based Order Detection**: Messages in Client Group are checked against a dedicated keyword list in `keywords.py`. Only messages containing at least one order keyword (`.com`, `.co`, `.net`, `.org`, `.pk`, `.io`, `.gg`, `gmail`, `gma`, `hotmail`, `hotmail.com`, `outlook`, `outlook.com`, `yahoo`, `icloud`, `proton`, `+`, `email`) are forwarded. All non-matching messages are ignored completely.

## [1.5.0] - 2026-08-08

### Added & Changed
- **Exact Message Copying**: Bot copies customer messages from Client Group to Loader Group **EXACTLY** as received (`copy_message`), with zero added metadata, prefixes, suffixes, headers, footers, or emojis.

## [1.4.0] - 2026-08-08

### Added & Changed
- **Updated Reaction Rules**: `👍` reaction placed on original customer message on order received (`[REACTION] 👍 Order received`), `❤️` reaction placed on loader reply message (`[REACTION] ❤️ Loader delivery`), `❤️` reaction placed on customer message upon delivery completion (`[REACTION] ❤️ Customer delivery completed`).

## [1.3.0] - 2026-08-08

### Added & Changed
- **Privacy Protection**: Completely removed customer Telegram names, usernames, first/last names, and User IDs from all bot messages.

## [1.2.0] - 2026-08-08

### Added & Changed
- **Two-Group Architecture**: Restructured bot workflow into Group 1 (**Client Group**) for customer orders and Group 2 (**Loader Group**) for automated order forwarding and loader image replies.

## [1.1.0] - 2026-08-08

### Added & Changed
- **Reply-Based Delivery Workflow**: Switched from searching email text in loader messages to explicit Reply-Based Order Mapping.
- **Zero Group ID Environment Variables**: Complete self-configuration via `/source` and `/delivery` Telegram commands without Railway `.env` edits.

## [1.0.0] - 2026-08-08

### Added
- **Source Group Listener**: Automated collection of single photos and Telegram Media Groups (albums).
- **Email Parser**: Regex-based email detection.
- **Media Group Debouncer**: In-memory album buffering and ordering preservation.
- **Database Engine**: SQLAlchemy 2.0 Async layer supporting both SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`).
- **Railway Deployment**: Full configuration including `Procfile`, `railway.json`, and `runtime.txt`.
