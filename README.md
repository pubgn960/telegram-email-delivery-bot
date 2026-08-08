# Telegram Email Image Delivery Bot (v1.0.0) 🚀

[![Python CI](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml/badge.svg)](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Railway Deploy](https://railway.app/button.svg)](https://railway.app/)

A production-ready Telegram bot built with **Python 3.12** and **python-telegram-bot v22+** designed to automatically aggregate image albums from a **Source Group** linked by email address and deliver them to a **Delivery Group** upon request. Fully optimized for instant deployment on **Railway**.

---

## ✨ Key Features

- **Automated Album Collection**: Monitors the **Source Group** for single photos, captions, and Telegram Media Groups (albums).
- **Smart Debouncing & Ordering**: Buffers media group updates in-memory to ensure complete album collection while preserving original image order.
- **Regex Email Parser**: Automatically extracts emails from text or captions (`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`) with whitespace trimming and lowercasing.
- **Automatic Album Splitting**: Splitting logic guarantees Telegram's 10-media limit per album (e.g. 18 photos → 2 albums: 10 & 8).
- **Duplicate Suppression**: Rejects duplicate media group uploads based on unique `media_group_id`.
- **Database Flexibility**: SQLAlchemy 2.0 Async supporting **SQLite** out-of-the-box for local testing and **PostgreSQL** for production on Railway.
- **Admin Security Whitelist**: Restricts administrative commands strictly to authorized user IDs (`ADMIN_IDS`).
- **Automatic Retries & Rate Limit Handling**: Built-in exponential backoff for Telegram `RetryAfter` rate limits and network glitches.
- **Automatic Storage Retention Cleanup**: Scheduled background task automatically purges records older than `MAX_STORAGE_DAYS`.

---

## 📁 Folder Structure

```
telegram-email-delivery-bot/
├── .github/
│   ├── ISSUE_TEMPLATE/    # Bug report & feature request templates
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       └── python.yml     # GitHub Actions CI workflow
├── main.py                # Bot application setup, handler registration & loop
├── config.py              # Configuration loader & environment variable validator
├── database.py            # Async SQLAlchemy engine, session maker & queries
├── models.py              # Declarative ORM models (Order, Image) with indexes
├── email_parser.py        # Regex email extractor & sanitizer
├── media_collector.py     # Debounced media group / album collector
├── delivery.py            # Album sender with auto-splitting (max 10) & retry logic
├── handlers.py            # Source group, Delivery group & Admin command handlers
├── utils.py               # Permissions, logging setup & formatting helpers
├── requirements.txt       # Dependencies
├── Procfile               # Railway worker startup rule
├── runtime.txt            # Python 3.12 runtime specification
├── railway.json           # Railway deployment spec
├── .env.example           # Environment template file
├── CHANGELOG.md           # Semantic versioning history
├── CONTRIBUTING.md        # Contribution guidelines
├── LICENSE                # MIT License
├── tests/                 # Unit tests suite
│   └── test_bot.py
└── README.md              # Documentation
```

---

## 🤖 BotFather Setup Guide

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow the instructions to create your bot.
3. Copy the **HTTP API Token** (e.g., `1234567890:ABCdefGHIjkl...`).
4. Add your bot to both your **Source Group** and **Delivery Group**.
5. Promote the bot to an **Administrator** in both groups with permissions to read and post messages.

---

## ⚙️ Environment Variables

Create a `.env` file based on `.env.example`:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Bot API Token from Telegram `@BotFather` | `1234567890:ABCdefGHIjkl...` |
| `SOURCE_GROUP_ID` | Telegram Chat ID of the Source Group | `-1001234567890` |
| `DELIVERY_GROUP_ID` | Telegram Chat ID of the Delivery Group | `-1009876543210` |
| `ADMIN_IDS` | Comma-separated list of Admin Telegram User IDs | `123456789,987654321` |
| `DATABASE_URL` | Async SQLAlchemy Connection String | `sqlite+aiosqlite:///bot_database.db` |
| `MEDIA_GROUP_TIMEOUT` | Album debounce timeout in seconds (default `2.0`) | `2.0` |
| `MAX_STORAGE_DAYS` | Data retention limit in days (default `30`) | `30` |

---

## 💻 Local Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/pubgn960/telegram-email-delivery-bot.git
cd telegram-email-delivery-bot
```

### 2. Create Virtual Environment & Install Dependencies
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Run Unit Tests
```bash
python -m unittest discover -s tests
```

### 4. Launch Bot Locally
```bash
python main.py
```

---

## 🐙 GitHub Repository Setup

1. Initialize git and push to your GitHub account:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Telegram Email Image Delivery Bot v1.0.0"
   git branch -M main
   git remote add origin https://github.com/pubgn960/telegram-email-delivery-bot.git
   git push -u origin main
   ```

---

## 🚂 Railway Deployment Guide

1. **Connect Repository to Railway**:
   - Log into [Railway](https://railway.app/).
   - Click **New Project** → **Deploy from GitHub repo**.
   - Select `telegram-email-delivery-bot`.

2. **Add PostgreSQL Database**:
   - In your Railway canvas, click **+ New** → **Database** → **PostgreSQL**.
   - Railway will auto-generate and inject `DATABASE_URL`.

3. **Set Environment Variables**:
   In your Railway service **Variables** settings, configure:
   - `BOT_TOKEN`
   - `SOURCE_GROUP_ID`
   - `DELIVERY_GROUP_ID`
   - `ADMIN_IDS`

4. **Deploy**:
   Railway automatically detects `railway.json`, `Procfile`, and `runtime.txt`, building container images under Python 3.12.

---

## 🛠 Admin Commands

All management commands are secured and restricted to user IDs defined in `ADMIN_IDS`:

- `/start` - Check bot status and group configuration.
- `/help` - Display command help menu.
- `/find <email>` - Search stored image counts and order history for an email.
- `/resend <email>` - Force re-delivery of stored images for an email.
- `/delete <email>` - Purge all records for an email from the database.
- `/stats` - View database dashboard metrics (Total Orders, Total Images, Unique Emails).

---

## 📸 Screenshots

*(Placeholder: Add screenshots of Source Group submission, Delivery Group automated album response, and /stats dashboard)*

---

## 🗺 Future Roadmap

- [ ] Web Dashboard for visual order management.
- [ ] Export orders to ZIP/PDF archive.
- [ ] Multi-tenant group support.
- [ ] OCR text extraction fallback for image-embedded email addresses.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
