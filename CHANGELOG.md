# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-08-08

### Added & Changed
- **Reply-Based Delivery Workflow**: Switched from searching email text in loader messages to explicit Reply-Based Order Mapping.
- **Order Registration**: Automatically registers customer orders and posts Order Headers (`📦 New Order \n Email: ... \n Order ID: ...`) into the Source/Loader Group.
- **Strict Loader Reply Validation**: Enforces that loaders MUST reply to the original Order Header message when sending images. Rejects non-reply media uploads with: `❌ Please reply to the original order message before sending images.`
- **Order ID Matching**: Extracts Order ID and customer email directly from replied-to messages.
- **Loader Success Reply**: Sends automatic confirmation to the loader in Source Group upon successful delivery: `✅ Delivery Successful \n Email: ... \n Images: ... \n Order ID: ...`.
- **Delivery Header**: Sends order summary in Delivery Group: `📧 Email: ... \n 📦 Order ID: ... \n ✅ Delivery Completed`.
- **Zero Group ID Environment Variables**: Complete self-configuration via `/source` and `/delivery` Telegram commands without Railway `.env` edits.

## [1.0.0] - 2026-08-08

### Added
- **Source Group Listener**: Automated collection of single photos and Telegram Media Groups (albums).
- **Email Parser**: Regex-based email detection (`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`) with whitespace trimming and case-insensitive lowercasing.
- **Media Group Debouncer**: In-memory album buffering and ordering preservation prior to database insertion.
- **Database Engine**: SQLAlchemy 2.0 Async layer supporting both SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`).
- **Delivery Engine**: Automated delivery trigger in Delivery Group with auto-splitting into max 10-item Telegram albums.
- **Admin Management Commands**: Security-whitelisted `/start`, `/help`, `/find`, `/resend`, `/delete`, and `/stats`.
- **Automatic Storage Retention**: Daily cleanup task purging records older than `MAX_STORAGE_DAYS`.
- **Railway Deployment**: Full configuration including `Procfile`, `railway.json`, and `runtime.txt`.
- **CI/CD Pipeline**: GitHub Actions workflow for automated testing and syntax compilation checks.
