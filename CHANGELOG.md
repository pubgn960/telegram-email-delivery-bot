# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
