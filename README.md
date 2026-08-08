# Telegram Email Image Delivery Bot (v1.0.0) 🚀

[![Python CI](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml/badge.svg)](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Railway Deploy](https://railway.app/button.svg)](https://railway.app/)

A self-configuring, production-ready Telegram bot built with **Python 3.12** and **python-telegram-bot v22+**. Automatically aggregates image albums from a **Source Group** linked by email address and delivers them to a **Delivery Group** upon request. **100% configurable directly from Telegram (Zero Group ID environment variables required)**.

---

## ✨ Key Features

- **Zero Group ID Configuration**: No need to copy or paste chat IDs into Railway or `.env`. Setup is done via `/source` and `/delivery` directly in Telegram.
- **Automated Album Collection**: Monitors the **Source Group** for single photos, captions, and Telegram Media Groups (albums).
- **Smart Debouncing & Ordering**: Buffers media group updates in-memory to ensure complete album collection while preserving original image order.
- **Regex Email Parser**: Automatically extracts emails from text or captions (`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`) with whitespace trimming and lowercasing.
- **Automatic Album Splitting**: Splitting logic guarantees Telegram's 10-media limit per album (e.g. 18 photos → 2 albums: 10 & 8).
- **Duplicate Suppression**: Rejects duplicate media group uploads based on unique `media_group_id` and SHA256 fingerprints.
- **Database Flexibility**: SQLAlchemy 2.0 Async supporting **SQLite** out-of-the-box for local testing and **PostgreSQL** for production on Railway.
- **Admin Security Whitelist**: Restricts administrative commands strictly to authorized user IDs (`ADMIN_IDS`).
- **Automatic Retries & Rate Limit Handling**: Built-in exponential backoff for Telegram `RetryAfter` rate limits and network glitches.

---

## ⚡ Self-Configuring Setup Workflow

Setting up the bot takes only 6 simple steps without touching environment variables:

1. Add your bot to the **Source Group** as an Administrator.
2. Send `/source` inside the Source Group.
3. Add your bot to the **Delivery Group** as an Administrator.
4. Send `/delivery` inside the Delivery Group.
5. Post photos with email captions in the Source Group.
6. Post the recipient email address in the Delivery Group to trigger instant album delivery!

---

## ⚙️ Required Environment Variables

Only **3 environment variables** are required:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Bot API Token from Telegram `@BotFather` | `1234567890:ABCdefGHIjkl...` |
| `ADMIN_IDS` | Comma-separated list of Admin Telegram User IDs | `123456789,987654321` |
| `DATABASE_URL` | Async SQLAlchemy Connection String | `sqlite+aiosqlite:///bot_database.db` |

---

## 🛠 Admin Management Commands

All management commands are secured and restricted to user IDs defined in `ADMIN_IDS`:

- `/source` - Mark current group as Source Group.
- `/delivery` - Mark current group as Delivery Group.
- `/groups` - Show current group setup status.
- `/status` - Display bot system status, database connection, uptime, and RAM usage.
- `/resetgroups` - Reset all group configurations.
- `/setup` - View interactive setup instructions.
- `/find <email>` - Search stored image counts and order history for an email.
- `/resend <email>` - Force re-delivery of stored images for an email.
- `/delete <email>` - Purge all records for an email from the database.
- `/stats` - View database dashboard metrics.
- `/pending` - List all undelivered orders.
- `/export` - Download CSV export report.
- `/backup` - Download SQLite database backup file.
- `/restore` - Restore SQLite database from attached `.db` backup file.

---

## 🚂 Deploying on Railway

1. Push your repository to GitHub.
2. Create a **New Project** on [Railway](https://railway.app/) → **Deploy from GitHub repo**.
3. Click **+ New** → **Database** → **PostgreSQL** (Railway auto-populates `DATABASE_URL`).
4. Set Environment Variables: `BOT_TOKEN`, `ADMIN_IDS`.
5. Railway automatically builds and launches the worker via `python main.py`.
6. Configure your groups in Telegram using `/source` and `/delivery`!
