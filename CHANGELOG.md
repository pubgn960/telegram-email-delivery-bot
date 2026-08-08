# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.0] - 2026-08-08

### Added & Changed
- **Updated Reaction Rules**:
  - `👍` reaction placed on the original customer message when order is received & forwarded (`[REACTION] 👍 Order received`).
  - `❤️` reaction placed on loader reply message upon image processing (`[REACTION] ❤️ Loader delivery`).
  - `❤️` reaction placed on original customer order message when delivery is completed in Client Group (`[REACTION] ❤️ Customer delivery completed`).
- **Reaction Failure Handling**: If reactions are not supported in a chat, logs `Reaction not supported.` and continues normal processing without stopping the workflow.

## [1.3.0] - 2026-08-08

### Added & Changed
- **Privacy Protection**: Completely removed customer Telegram names, usernames, first/last names, and User IDs from all bot messages.
- **Graceful Reaction Fallbacks**: Added `safe_set_message_reaction()` helper in `utils.py` that never crashes if reactions are disabled/unsupported in a chat.

## [1.2.0] - 2026-08-08

### Added & Changed
- **Two-Group Architecture**: Restructured bot workflow into Group 1 (**Client Group**) for customer orders and Group 2 (**Loader Group**) for automated order forwarding and loader image replies.
- **Automated Order Forwarding**: Bot automatically posts customer orders into the Loader Group.
- **Strict Loader Reply Validation**: Loaders MUST reply directly to the bot's Order Message in the Loader Group.

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
