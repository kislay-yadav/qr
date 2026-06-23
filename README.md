# ⚡ UPI QR Ultra Bot — Complete Setup Guide

---

## 📦 Prerequisites

```bash
pkg update && pkg upgrade -y
pkg install python python-pip git -y
pip install --upgrade pip
```

---

## 🔧 Installation (Termux / Linux)

```bash
# 1. Create project folder
mkdir upi_qr_bot && cd upi_qr_bot

# 2. Copy bot.py and requirements.txt here

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export BOT_TOKEN="your_telegram_bot_token"
export OWNER_ID="your_telegram_user_id"

# 5. Run
python bot.py
```

---

## 🌐 Deploy on Render (Free Cloud)

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install fonts for QR card text
RUN apt-get update && apt-get install -y fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

COPY . .
CMD ["python", "bot.py"]
```

### render.yaml
```yaml
services:
  - type: worker
    name: upi-qr-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python bot.py
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: OWNER_ID
        sync: false
```

---

## 🔑 Getting Your Credentials

### BOT_TOKEN
1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Follow prompts → copy the token

### OWNER_ID
1. Open Telegram → search **@userinfobot**
2. Send `/start` → copy your ID

---

## 📋 All Commands Reference

### 👤 User Commands
| Command | Description |
|---------|-------------|
| `/start` | Launch bot & main menu |
| `/menu` | Open main menu |
| `/help` | Full command guide |
| `/setupi` | Save your UPI ID & name |
| `/qr [amount]` | Generate QR with saved UPI |
| `/newqr` | Generate QR with custom UPI |
| `/style` | Browse & change QR style |
| `/setlogo` | Upload center logo image |
| `/removelogo` | Remove your logo |
| `/myinfo` | View your saved profile |
| `/stats` | Your QR generation stats |
| `/removeupi` | Delete saved UPI ID |

### 🛡️ Admin Commands
| Command | Description |
|---------|-------------|
| `/listadmins` | List all admins |
| `/ban <id>` | Ban a user |
| `/unban <id>` | Unban a user |
| `/bannedlist` | View all banned users |
| `/globalstats` | Bot-wide statistics |
| `/userinfo <id>` | View any user's details |

### 👑 Owner Commands
| Command | Description |
|---------|-------------|
| `/addadmin <id>` | Promote user to admin |
| `/rmadmin <id>` | Demote admin |
| `/broadcast` | Send message to all users |
| `/exportdb` | Download full database JSON |

---

## 🎨 QR Styles Available

| Key | Name | Theme |
|-----|------|-------|
| `cosmic` | 🌌 Cosmic Dark | Dark blue + cyan + violet gradient |
| `neon` | 💚 Neon Matrix | Black + electric green |
| `gold` | 🥇 Royal Gold | Dark + gold-to-orange gradient |
| `sakura` | 🌸 Sakura Pink | White + deep pink circles |
| `ocean` | 🌊 Deep Ocean | Navy + sky blue radial |
| `fire` | 🔥 Inferno Red | Black + red-to-gold gradient |
| `mint` | 🌿 Fresh Mint | Soft white + green circles |
| `purple` | 💜 Royal Purple | Deep dark + violet glow |

---

## 🗃️ Database Structure (database.json)

```json
{
  "users": {
    "123456789": {
      "upi": "yourname@upi",
      "name": "Your Name",
      "qr_count": 12,
      "style": "cosmic",
      "logo": null,
      "joined": "2025-06-22T09:00:00",
      "last_active": "2025-06-22T10:30:00"
    }
  },
  "admins": [987654321],
  "banned": [],
  "stats": {
    "total_qr": 45,
    "total_users": 10
  }
}
```

---

## 🧩 Supported UPI ID Formats

- `name@upi`
- `name@paytm`
- `name@okicici`
- `9876543210@paytm`
- `name@ybl` (PhonePe)
- `name@ibl` (ICICI)
- `name@axl` (Axis)
- `name@okhdfcbank`

---

## 💡 Tips

- QR images are generated at **700×900 px, 300 DPI** — print quality
- The center circle/logo has **error correction level H** so 30% of the QR can be covered
- All data is stored locally in `database.json` — back it up regularly
- On Render, mount a **persistent disk** at `/app` to preserve the database between deploys

---

## 🛡️ Security Notes

- Never share your `BOT_TOKEN` publicly
- Only the `OWNER_ID` can add/remove admins and use owner commands
- Banned users are blocked at the entry of every handler
- The `/exportdb` command is owner-only and sends the raw JSON file

---

*⚡ UPI QR Ultra Bot — Built for Termux & Cloud Deployment*
