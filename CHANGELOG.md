# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-08-08

### Added & Changed
- **Two-Group Architecture**: Restructured bot workflow into Group 1 (**Client Group**) for customer orders and Group 2 (**Loader Group**) for automated order forwarding and loader image replies.
- **Automated Order Forwarding**: Bot automatically posts customer orders into the Loader Group (`📦 NEW ORDER \n Order ID: #10025 \n Package: 10800 CP \n Email: ... \n Customer: @username`).
- **Strict Loader Reply Validation**: Loaders MUST reply directly to the bot's Order Message in the Loader Group. Rejects non-reply uploads with: `❌ Please reply to the original order message.`
- **Duplicate Delivery Prevention**: If a loader replies to an already delivered order, replies with: `⚠️ This order has already been delivered.`
- **Order Status Tracking**: Added explicit status states (`Pending`, `Delivered`, `Cancelled`, `Expired`).
- **Order Timeout Monitoring**: Background task automatically marks orders pending longer than 24 hours as `Expired` (⏰ Pending Too Long).
- **Loader Confirmation Message Editing**: Upon successful delivery to Client Group, edits/replies to the loader message in Loader Group with delivery details (`✅ DELIVERED \n Order ID: #10025 \n Images: 8 \n Delivered: ...`).
- **New Admin Management Commands**: Added `/pending`, `/delivered`, `/order <id>`, and `/cancel <id>`. Enhanced `/find` and `/stats` with rich metrics (Total, Pending, Delivered, Cancelled, Today's Orders, Today's Deliveries, Avg Delivery Time).

## [1.1.0] - 2026-08-08

### Added & Changed
- **Reply-Based Delivery Workflow**: Switched from searching email text in loader messages to explicit Reply-Based Order Mapping.
- **Order Registration**: Automatically registers customer orders and posts Order Headers into the Source/Loader Group.
- **Zero Group ID Environment Variables**: Complete self-configuration via `/source` and `/delivery` Telegram commands without Railway `.env` edits.

## [1.0.0] - 2026-08-08

### Added
- **Source Group Listener**: Automated collection of single photos and Telegram Media Groups (albums).
- **Email Parser**: Regex-based email detection.
- **Media Group Debouncer**: In-memory album buffering and ordering preservation.
- **Database Engine**: SQLAlchemy 2.0 Async layer supporting both SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`).
- **Delivery Engine**: Automated delivery trigger in Delivery Group with auto-splitting into max 10-item Telegram albums.
- **Railway Deployment**: Full configuration including `Procfile`, `railway.json`, and `runtime.txt`.
