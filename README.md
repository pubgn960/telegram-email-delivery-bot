# Telegram Email Image Delivery Bot (v1.2.0) 🚀

[![Python CI](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml/badge.svg)](https://github.com/pubgn960/telegram-email-delivery-bot/actions/workflows/python.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Railway Deploy](https://railway.app/button.svg)](https://railway.app/)

A self-configuring, production-ready Telegram bot built with **Python 3.12** and **python-telegram-bot v22+**. Operates on a production **Two-Group Reply-Based Workflow** linking customer orders from the **Client Group** directly to loader image submissions in the **Loader Group**.

---

## 🏗 Two-Group Architecture & Workflow

```text
+-----------------------+              +-----------------------+
|    1. CLIENT GROUP    |              |    2. LOADER GROUP    |
| (Customers post info) |              | (Loaders reply media) |
+-----------+-----------+              +-----------+-----------+
            |                                      |
     Customer sends order                    Bot forwards order
 (Email: abc@gmail.com)                      (Order ID: #10025)
            |                                      |
            v                                      v
+-----------+-----------+              +-----------+-----------+
| Bot Registers Order   |------------->| Loader Replies to Order   |
| (Status: Pending)     |              | (Photos / Albums / Docs)  |
+-----------------------+              +-----------+-----------+
            ^                                      |
            |                                      v
   Bot delivers albums                 Bot validates reply &
   to Client Group                     buffers image file_ids
            |                                      |
            +--------------------------------------+
                               |
                  Updates Status to 'Delivered'
                  Edits Loader Msg in Loader Group
```

---

## 🔄 Step-by-Step Business Workflow

### Step 1: Customer Order (Client Group)
A customer posts an order message in **Group 1 (Client Group)** containing text and email:
```text
10800 CP
Email: abc@gmail.com
```
The bot creates a database record with `Order ID: #10025`, status `Pending`, and automatically posts/forwards the formatted order message into **Group 2 (Loader Group)**:
```text
📦 NEW ORDER
Order ID: #10025
Package: 10800 CP
Email: abc@gmail.com
Customer: @john_doe
Time: 2026-08-08 17:30
```

### Step 2: Loader Reply (Loader Group)
The loader **MUST reply directly** to the bot's Order Message in the Loader Group with photos, photo-documents, or albums.

- The loader **never types the email manually**.
- The loader **never searches by email**.
- If the loader sends images without replying, the bot rejects the upload:
  ```text
  ❌ Please reply to the original order message.
  ```

### Step 3: Automated Delivery & Confirmations
Upon album completion, the bot automatically dispatches the image albums (split into max 10-item Telegram albums) to the **Client Group**:
```text
📧 Email: abc@gmail.com
📦 Order ID: #10025
✅ Delivery Completed
```
The bot updates the order status to `Delivered` and sends a confirmation back to the Loader Group:
```text
✅ DELIVERED
Order ID: #10025
Images: 8
Delivered: 2026-08-08 17:45
```

---

## 🛡 Duplicate & Timeout Safeguards

- **Duplicate Delivery Prevention**: If a loader replies to an already delivered order, the bot replies: `⚠️ This order has already been delivered.`
- **Fingerprint Protection**: Rejects duplicate media group uploads via SHA256 fingerprints.
- **Order Timeout Check**: Pending orders older than 24 hours are automatically marked `Expired` (⏰ Pending Too Long).

---

## ⚙️ Environment Variables (Zero Group IDs Required)

Only **3 environment variables** are required:

| Variable | Description | Example |
| :--- | :--- | :--- |
| `BOT_TOKEN` | Bot API Token from Telegram `@BotFather` | `1234567890:ABCdefGHIjkl...` |
| `ADMIN_IDS` | Comma-separated list of Admin Telegram User IDs | `123456789,987654321` |
| `DATABASE_URL` | Async SQLAlchemy Connection String | `sqlite+aiosqlite:///bot_database.db` |

---

## 🛠 Admin Management Commands

- `/source` - Configure current group as **Client Group**.
- `/delivery` - Configure current group as **Loader Group**.
- `/groups` - Display group configuration status.
- `/status` - View bot status, DB engine, uptime, and RAM memory usage.
- `/pending` - List all pending orders waiting for loader reply.
- `/delivered` - List latest delivered orders.
- `/find <order_id_or_email>` - Search order details by Order ID (e.g. `10025`) or customer email.
- `/order <order_id>` - Display detailed order information.
- `/cancel <order_id>` - Cancel a pending order.
- `/resend <order_id>` - Re-deliver an order to the Client Group.
- `/stats` - View rich dashboard metrics (Total, Pending, Delivered, Cancelled, Today's Orders, Today's Deliveries, Avg Delivery Time).
- `/export` - Download CSV report export.
- `/backup` - Download SQLite database backup file.
- `/restore` - Restore SQLite database from attached `.db` file.
- `/resetgroups` - Clear group configurations in DB.

---

## 🚂 Railway Deployment Guide

1. Push your repository to GitHub.
2. Create a **New Project** on [Railway](https://railway.app/) → **Deploy from GitHub repo**.
3. Click **+ New** → **Database** → **PostgreSQL** (Railway auto-populates `DATABASE_URL`).
4. Set Environment Variables: `BOT_TOKEN`, `ADMIN_IDS`.
5. Railway automatically builds and launches the worker via `python main.py`.
6. Send `/source` in your Client Group and `/delivery` in your Loader Group!
