# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-08-08

### Added & Changed
- **Privacy Protection**: Completely removed customer Telegram names, usernames, first/last names, and User IDs from all bot messages. Loader Group order messages format: `📦 NEW ORDER \n Order ID: #1 \n Package: ... \n Email: ... \n Time: ...`.
- **Telegram Reaction 📥 (Order Received)**: When an order is registered and forwarded to Loader Group, automatically places an `📥` (or `✅` fallback) reaction on the original customer message in Client Group.
- **Telegram Reaction ❤️ (Delivery Completed)**: When loader delivery is processed, automatically places a `❤️` reaction on the original customer order message in Client Group and the loader's delivery message in Loader Group.
- **Graceful Reaction Fallbacks**: Added `safe_set_message_reaction()` helper in `utils.py` that never crashes if reactions are disabled/unsupported in a chat. Logs `Reaction not supported` on failure.
- **Clean Delivery Formatting**: Streamlined delivery header in Client Group (`📧 Email \n abc@gmail.com \n 📦 Order ID \n #1 \n ✅ Delivery Completed`).

## [1.2.0] - 2026-08-08

### Added & Changed
- **Two-Group Architecture**: Restructured bot workflow into Group 1 (**Client Group**) for customer orders and Group 2 (**Loader Group**) for automated order forwarding and loader image replies.
- **Automated Order Forwarding**: Bot automatically posts customer orders into the Loader Group.
- **Strict Loader Reply Validation**: Loaders MUST reply directly to the bot's Order Message in the Loader Group.
- **Duplicate Delivery Prevention**: If a loader replies to an already delivered order, replies with: `⚠️ This order has already been delivered.`
- **Order Status Tracking**: Added explicit status states (`Pending`, `Delivered`, `Cancelled`, `Expired`).
- **Order Timeout Monitoring**: Background task automatically marks orders pending longer than 24 hours as `Expired` (⏰ Pending Too Long).
- **New Admin Management Commands**: Added `/pending`, `/delivered`, `/order <id>`, and `/cancel <id>`.

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
