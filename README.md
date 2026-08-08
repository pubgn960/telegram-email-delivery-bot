# Telegram Email Image Delivery Bot (v1.1.0) 🚀

[![Python CI](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml/badge.svg)](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Railway Deploy](https://railway.app/button.svg)](https://railway.app/)

A self-configuring, production-ready Telegram bot built with **Python 3.12** and **python-telegram-bot v22+**. Implements a strict **Reply-Based Delivery Workflow** linking loader image submissions directly to customer Order IDs. **100% configurable directly from Telegram (Zero Group ID environment variables required)**.

---

## ✨ Key Features & Workflow

- **Reply-Based Order Mapping**: Loaders **MUST** reply to the original Order Header message when submitting images. Rejects non-reply uploads with: `❌ Please reply to the original order message before sending images.`
- **Automated Order Registration**: Posts Order Headers (`📦 New Order \n Email: ... \n Order ID: ...`) into the Source Group when a customer submits an email.
- **Zero Group ID Configuration**: No need to copy or paste chat IDs into Railway or `.env`. Setup is done via `/source` and `/delivery` directly in Telegram.
- **Automated Album Collection**: Monitors the **Source Group** for single photos, captions, and Telegram Media Groups (albums).
- **Smart Debouncing & Ordering**: Buffers media group updates in-memory to ensure complete album collection while preserving original image order.
- **Automatic Album Splitting**: Splitting logic guarantees Telegram's 10-media limit per album (e.g. 18 photos → 2 albums: 10 & 8).
- **Duplicate Suppression**: Rejects duplicate media group uploads based on SHA256 fingerprints (`Duplicate Ignored`).
- **Loader Confirmation**: Sends instant success confirmation to the loader in the Source Group (`✅ Delivery Successful \n Email: ... \n Images: ... \n Order ID: ...`).
- **Database Flexibility**: SQLAlchemy 2.0 Async supporting **SQLite** out-of-the-box for local testing and **PostgreSQL** for production on Railway.
- **Admin Security Whitelist**: Restricts administrative commands strictly to authorized user IDs (`ADMIN_IDS`).

---

## 🔄 Reply-Based Delivery Workflow

### Step 1: Customer Order Registration
Customer posts message containing email (e.g. `Email: abc@gmail.com`).
The bot registers the order and posts an Order Header into the Source Group:
```text
📦 New Order

Email:
abc@gmail.com

Order ID:
12345
```

### Step 2: Loader Image Upload
The loader **MUST reply directly** to the `📦 New Order` message with photos or photo-documents.
If the loader sends images without replying, the bot rejects the upload:
```text
❌ Please reply to the original order message before sending images.
```

### Step 3: Automated Delivery & Confirmation
Once the loader's album finishes uploading, the bot automatically dispatches the images to the **Delivery Group** with a delivery completion header:
```text
📧 Email:
abc@gmail.com

📦 Order ID:
12345

✅ Delivery Completed
```
The bot then sends a Success Reply back to the loader in the Source Group:
```text
✅ Delivery Successful

Email:
abc@gmail.com

Images:
8

Order ID:
12345
```

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
