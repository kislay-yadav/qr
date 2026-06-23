import os
import io
import json
import time
import hashlib
import logging
import asyncio
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    RoundedModuleDrawer, GappedSquareModuleDrawer,
    CircleModuleDrawer, SquareModuleDrawer, VerticalBarsDrawer
)
from qrcode.image.styles.colormasks import (
    RadialGradiantColorMask, SquareGradiantColorMask,
    HorizontalGradiantColorMask, SolidFillColorMask
)
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, BotCommand, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID    = int(os.getenv("OWNER_ID", "123456789"))   # Your Telegram user ID
DB_FILE     = "database.json"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONVERSATION STATES
# ─────────────────────────────────────────────
(
    WAITING_UPI, WAITING_NAME, WAITING_AMOUNT,
    WAITING_NUPI, WAITING_NUPI_AMOUNT,
    WAITING_BROADCAST, WAITING_BAN_ID,
    WAITING_LOGO, WAITING_CUSTOM_UPI_FULL,
) = range(9)

# ─────────────────────────────────────────────
#  QR STYLES  ─ 8 premium presets
# ─────────────────────────────────────────────
QR_STYLES = {
    "cosmic": {
        "name": "🌌 Cosmic Dark",
        "bg": (10, 10, 30),
        "fg": (100, 200, 255),
        "accent": (255, 100, 200),
        "border": (60, 60, 120),
        "drawer": RoundedModuleDrawer,
        "mask": RadialGradiantColorMask,
        "mask_args": {"back_color": (10,10,30), "center_color": (100,200,255), "edge_color": (180,80,255)},
    },
    "neon": {
        "name": "💚 Neon Matrix",
        "bg": (0, 10, 0),
        "fg": (0, 255, 100),
        "accent": (0, 200, 80),
        "border": (0, 80, 30),
        "drawer": SquareModuleDrawer,
        "mask": SolidFillColorMask,
        "mask_args": {"back_color": (0,10,0), "front_color": (0,255,100)},
    },
    "gold": {
        "name": "🥇 Royal Gold",
        "bg": (20, 15, 0),
        "fg": (255, 200, 30),
        "accent": (255, 160, 0),
        "border": (80, 60, 0),
        "drawer": RoundedModuleDrawer,
        "mask": HorizontalGradiantColorMask,
        "mask_args": {"back_color": (20,15,0), "left_color": (255,200,30), "right_color": (255,130,0)},
    },
    "sakura": {
        "name": "🌸 Sakura Pink",
        "bg": (255, 240, 248),
        "fg": (200, 50, 120),
        "accent": (255, 100, 180),
        "border": (240, 180, 220),
        "drawer": CircleModuleDrawer,
        "mask": SolidFillColorMask,
        "mask_args": {"back_color": (255,240,248), "front_color": (200,50,120)},
    },
    "ocean": {
        "name": "🌊 Deep Ocean",
        "bg": (5, 20, 50),
        "fg": (30, 160, 255),
        "accent": (0, 220, 200),
        "border": (10, 60, 120),
        "drawer": RoundedModuleDrawer,
        "mask": SquareGradiantColorMask,
        "mask_args": {"back_color": (5,20,50), "center_color": (30,160,255), "edge_color": (0,100,200)},
    },
    "fire": {
        "name": "🔥 Inferno Red",
        "bg": (20, 5, 0),
        "fg": (255, 80, 20),
        "accent": (255, 200, 0),
        "border": (80, 20, 0),
        "drawer": GappedSquareModuleDrawer,
        "mask": HorizontalGradiantColorMask,
        "mask_args": {"back_color": (20,5,0), "left_color": (255,80,20), "right_color": (255,200,0)},
    },
    "mint": {
        "name": "🌿 Fresh Mint",
        "bg": (240, 255, 248),
        "fg": (0, 150, 100),
        "accent": (0, 200, 150),
        "border": (180, 240, 210),
        "drawer": CircleModuleDrawer,
        "mask": SolidFillColorMask,
        "mask_args": {"back_color": (240,255,248), "front_color": (0,150,100)},
    },
    "purple": {
        "name": "💜 Royal Purple",
        "bg": (15, 5, 30),
        "fg": (180, 80, 255),
        "accent": (255, 150, 255),
        "border": (60, 20, 100),
        "drawer": RoundedModuleDrawer,
        "mask": RadialGradiantColorMask,
        "mask_args": {"back_color": (15,5,30), "center_color": (180,80,255), "edge_color": (100,20,200)},
    },
}

# ─────────────────────────────────────────────
#  DATABASE  (JSON flat-file)
# ─────────────────────────────────────────────
def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        return {"users": {}, "admins": [], "banned": [], "stats": {"total_qr": 0, "total_users": 0}}
    with open(DB_FILE) as f:
        return json.load(f)

def save_db(db: dict):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

def get_user(db: dict, uid: int) -> dict:
    key = str(uid)
    if key not in db["users"]:
        db["users"][key] = {
            "upi": None, "name": None, "qr_count": 0, "style": "cosmic",
            "logo": None, "joined": datetime.now().isoformat(), "last_active": None,
        }
        db["stats"]["total_users"] += 1
        save_db(db)
    return db["users"][key]

def touch_user(db: dict, uid: int):
    get_user(db, uid)
    db["users"][str(uid)]["last_active"] = datetime.now().isoformat()
    save_db(db)

# ─────────────────────────────────────────────
#  PERMISSION DECORATORS
# ─────────────────────────────────────────────
def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text(TEXTS["no_perm"])
            return
        return await func(update, ctx)
    return wrapper

def not_banned(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        db = load_db()
        if update.effective_user.id in db["banned"]:
            await update.message.reply_text("🚫 You are banned from using this bot.")
            return
        return await func(update, ctx)
    return wrapper

def admin_or_owner(func):
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        db = load_db()
        uid = update.effective_user.id
        if uid != OWNER_ID and uid not in db["admins"]:
            await update.message.reply_text(TEXTS["no_perm"])
            return
        return await func(update, ctx)
    return wrapper

# ─────────────────────────────────────────────
#  PREMIUM TEXT TEMPLATES
# ─────────────────────────────────────────────
TEXTS = {
    "no_perm": (
        "╔══════════════════════╗\n"
        "║  🔐  ACCESS DENIED   ║\n"
        "╚══════════════════════╝\n\n"
        "⛔ You don't have permission to use this command.\n"
        "Contact the bot owner if you believe this is a mistake."
    ),
    "welcome": (
        "╔══════════════════════════════╗\n"
        "║  ✨  UPI QR  ULTRA  PRO  ✨  ║\n"
        "╚══════════════════════════════╝\n\n"
        "👋 Welcome, **{name}**!\n\n"
        "🎯 *Generate premium-quality UPI QR codes*\n"
        "🎨 *8 stunning visual styles*\n"
        "⚡ *Instant, high-resolution output*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *Quick Start:*\n"
        "  » /setupi — Save your UPI ID\n"
        "  » /qr `<amount>` — Generate QR\n"
        "  » /style — Change QR style\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Type /help for all commands"
    ),
}

# ─────────────────────────────────────────────
#  QR IMAGE GENERATOR
# ─────────────────────────────────────────────
def build_upi_url(upi_id: str, name: str, amount: Optional[float] = None) -> str:
    url = f"upi://pay?pa={upi_id}&pn={requests.utils.quote(name)}&cu=INR"
    if amount:
        url += f"&am={amount}"
    return url

def generate_qr_image(
    upi_id: str,
    name: str,
    amount: Optional[float],
    style_key: str = "cosmic",
    logo_bytes: Optional[bytes] = None,
) -> bytes:
    style = QR_STYLES.get(style_key, QR_STYLES["cosmic"])
    upi_url = build_upi_url(upi_id, name, amount)

    # --- Build raw QR ---
    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12, border=2,
    )
    qr.add_data(upi_url)
    qr.make(fit=True)

    try:
        drawer_cls = style["drawer"]
        if style["mask"] in (SolidFillColorMask,):
            qr_img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=drawer_cls(),
                color_mask=style["mask"](**style["mask_args"]),
            )
        else:
            qr_img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=drawer_cls(),
                color_mask=style["mask"](**style["mask_args"]),
            )
    except Exception:
        qr_img = qr.make_image(fill_color=style["fg"], back_color=style["bg"])

    qr_pil = qr_img.convert("RGBA")
    qr_size = qr_pil.size[0]

    # --- Add center logo / circle ---
    logo_area = qr_size // 5
    if logo_bytes:
        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
            logo = logo.resize((logo_area, logo_area), Image.LANCZOS)
            mask = Image.new("L", (logo_area, logo_area), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, logo_area, logo_area), fill=255)
            logo.putalpha(mask)
            pos = ((qr_size - logo_area) // 2, (qr_size - logo_area) // 2)
            qr_pil.paste(logo, pos, logo)
        except Exception:
            pass
    else:
        # accent circle
        draw = ImageDraw.Draw(qr_pil)
        cx = qr_size // 2
        r  = logo_area // 2
        draw.ellipse((cx-r, cx-r, cx+r, cx+r), fill=style["accent"] + (220,))

    # --- Build card ---
    card_w, card_h = 700, 900
    card = Image.new("RGBA", (card_w, card_h), style["bg"])
    draw = ImageDraw.Draw(card)

    # Gradient overlay top
    for y in range(120):
        alpha = int(160 * (1 - y / 120))
        r2, g2, b2 = style["accent"]
        draw.line([(0, y), (card_w, y)], fill=(r2, g2, b2, alpha))

    # Border glow
    for i in range(6):
        r2, g2, b2 = style["border"]
        draw.rectangle(
            [i, i, card_w - i - 1, card_h - i - 1],
            outline=(r2, g2, b2, 60 + i * 10)
        )

    # Paste QR centered
    qr_target = 500
    qr_pil_r = qr_pil.resize((qr_target, qr_target), Image.LANCZOS)
    qr_x = (card_w - qr_target) // 2
    qr_y = 180
    card.paste(qr_pil_r, (qr_x, qr_y), qr_pil_r)

    # QR border box
    pad = 12
    draw.rectangle(
        [qr_x - pad, qr_y - pad, qr_x + qr_target + pad, qr_y + qr_target + pad],
        outline=style["accent"], width=3
    )

    # --- Typography ---
    try:
        font_title  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",    44)
        font_amount = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",    54)
        font_upi    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",         26)
        font_small  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", 22)
        font_tag    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",         20)
    except Exception:
        font_title = font_amount = font_upi = font_small = font_tag = ImageFont.load_default()

    ar, ag, ab = style["accent"]
    fr, fg2, fb = style["fg"]

    # Title
    title_text = "INITIALIZE PAYMENT"
    bbox = draw.textbbox((0, 0), title_text, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((card_w - tw) // 2, 30), title_text, font=font_title, fill=(fr, fg2, fb, 255))

    # Amount
    amt_text = f"₹ {amount:.2f} INR" if amount else "ANY AMOUNT"
    bbox = draw.textbbox((0, 0), amt_text, font=font_amount)
    aw = bbox[2] - bbox[0]
    draw.text(((card_w - aw) // 2, 100), amt_text, font=font_amount, fill=(ar, ag, ab, 255))

    # Underline
    draw.line([(card_w // 2 - 150, 160), (card_w // 2 + 150, 160)], fill=(ar, ag, ab, 180), width=2)

    # Bottom info
    info_y = qr_y + qr_target + pad + 30
    paying_text = f"PAYING TO: {upi_id}"
    bbox = draw.textbbox((0, 0), paying_text, font=font_upi)
    pw = bbox[2] - bbox[0]
    draw.text(((card_w - pw) // 2, info_y), paying_text, font=font_upi, fill=(fr, fg2, fb, 200))

    name_text = f"Account Name: {name}"
    bbox = draw.textbbox((0, 0), name_text, font=font_small)
    nw = bbox[2] - bbox[0]
    draw.text(((card_w - nw) // 2, info_y + 40), name_text, font=font_small, fill=(ar, ag, ab, 180))

    hint_text = "📱 Scan with any UPI app to proceed"
    bbox = draw.textbbox((0, 0), hint_text, font=font_small)
    hw = bbox[2] - bbox[0]
    draw.text(((card_w - hw) // 2, info_y + 80), hint_text, font=font_small, fill=(fr, fg2, fb, 150))

    # Style badge
    badge = f"Style: {style['name']}"
    draw.text((20, card_h - 50), badge, font=font_tag, fill=(ar, ag, ab, 120))

    # Watermark
    wm = "⚡ @UpiQrUltraBot"
    bbox = draw.textbbox((0, 0), wm, font=font_tag)
    ww = bbox[2] - bbox[0]
    draw.text(((card_w - ww) // 2, card_h - 50), wm, font=font_tag, fill=(ar, ag, ab, 150))

    # Timestamp
    ts = datetime.now().strftime("%d %b %Y  %H:%M")
    draw.text((card_w - 200, card_h - 50), ts, font=font_tag, fill=(fr, fg2, fb, 100))

    # Convert to RGB and save
    final = Image.new("RGB", (card_w, card_h), style["bg"])
    final.paste(card, mask=card.split()[3])

    buf = io.BytesIO()
    final.save(buf, format="PNG", dpi=(300, 300))
    buf.seek(0)
    return buf.read()

# ─────────────────────────────────────────────
#  INLINE KEYBOARDS
# ─────────────────────────────────────────────
def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Generate QR", callback_data="gen_qr"),
         InlineKeyboardButton("🎨 Change Style", callback_data="style_menu")],
        [InlineKeyboardButton("⚙️ My Settings",  callback_data="my_settings"),
         InlineKeyboardButton("📊 My Stats",     callback_data="my_stats")],
        [InlineKeyboardButton("🖼️ Set Logo",     callback_data="set_logo"),
         InlineKeyboardButton("❓ Help",          callback_data="help")],
        [InlineKeyboardButton("⭐ Rate & Share",  callback_data="rate")],
    ])

def style_menu_kb(current: str):
    rows = []
    items = list(QR_STYLES.items())
    for i in range(0, len(items), 2):
        row = []
        for key, val in items[i:i+2]:
            label = val["name"] + (" ✅" if key == current else "")
            row.append(InlineKeyboardButton(label, callback_data=f"setstyle_{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def settings_kb(user: dict):
    upi_set = "✅" if user["upi"] else "❌"
    logo_set = "✅" if user["logo"] else "❌"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 UPI ID {upi_set}", callback_data="edit_upi"),
         InlineKeyboardButton(f"🖼️ Logo {logo_set}",  callback_data="set_logo")],
        [InlineKeyboardButton("🗑️ Clear UPI",          callback_data="clear_upi"),
         InlineKeyboardButton("🗑️ Clear Logo",         callback_data="clear_logo")],
        [InlineKeyboardButton("🔙 Back",               callback_data="main_menu")],
    ])

def amount_quick_kb():
    amounts = [10, 20, 50, 100, 200, 500, 1000, 2000]
    rows = []
    for i in range(0, len(amounts), 4):
        rows.append([
            InlineKeyboardButton(f"₹{a}", callback_data=f"quick_amt_{a}")
            for a in amounts[i:i+4]
        ])
    rows.append([InlineKeyboardButton("✏️ Custom Amount", callback_data="custom_amount"),
                 InlineKeyboardButton("🔙 Back",           callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = update.effective_user.id
    if uid in db["banned"]:
        await update.message.reply_text("🚫 You are banned.")
        return
    touch_user(db, uid)
    name = update.effective_user.first_name or "User"
    msg = TEXTS["welcome"].format(name=name)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

# ─────────────────────────────────────────────
#  /help
# ─────────────────────────────────────────────
HELP_TEXT = """
╔══════════════════════════════════╗
║  📖  COMPLETE COMMAND GUIDE  📖  ║
╚══════════════════════════════════╝

━━━  👤 USER COMMANDS  ━━━━━━━━━━

🔹 /start       — Launch bot & main menu
🔹 /menu        — Open main menu
🔹 /help        — This help message
🔹 /setupi      — Save your UPI ID & name
🔹 /qr [amt]    — QR with saved UPI
🔹 /newqr       — QR with a custom UPI ID
🔹 /style       — Browse & apply QR styles
🔹 /setlogo     — Upload a center logo
🔹 /removelogo  — Remove your logo
🔹 /myinfo      — View your saved profile
🔹 /stats       — Your personal statistics
🔹 /removeupi   — Delete saved UPI ID

━━━  🎨 QR STYLES (8 total)  ━━━━

🌌 cosmic   💚 neon   🥇 gold   🌸 sakura
🌊 ocean    🔥 fire   🌿 mint   💜 purple

  → Use /style to preview & switch

━━━  🛡️ ADMIN COMMANDS  ━━━━━━━━

🔸 /addadmin [id]  — Promote user to admin
🔸 /rmadmin [id]   — Demote admin
🔸 /listadmins     — List all admins
🔸 /ban [id]       — Ban a user
🔸 /unban [id]     — Unban a user
🔸 /bannedlist     — View all banned users
🔸 /broadcast      — Send msg to all users
🔸 /userinfo [id]  — View user details
🔸 /globalstats    — Total bot statistics

━━━  👑 OWNER COMMANDS  ━━━━━━━━

🔺 /addadmin    — Add new admin
🔺 /rmadmin     — Remove admin
🔺 /ban         — Permanently ban user
🔺 /unban       — Unban user
🔺 /broadcast   — Mass broadcast
🔺 /resetuser   — Reset user data
🔺 /setbotname  — Update bot identity
🔺 /exportdb    — Export full database

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Tip: Use /qr 500 to instantly generate
   a ₹500 QR with your saved UPI ID.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Powered by UPI QR Ultra Bot
"""

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
    if update.message:
        await update.message.reply_text(HELP_TEXT, reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(HELP_TEXT, reply_markup=kb)

# ─────────────────────────────────────────────
#  /setupi  (conversation)
# ─────────────────────────────────────────────
async def cmd_setupi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "╔══════════════════════════╗\n"
        "║  💳  SET YOUR UPI ID  💳  ║\n"
        "╚══════════════════════════╝\n\n"
        "📝 Please enter your **UPI ID**:\n"
        "_(example: yourname@upi or 9876543210@paytm)_",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_UPI

async def received_upi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["temp_upi"] = update.message.text.strip()
    await update.message.reply_text(
        "✅ UPI ID saved!\n\n"
        "👤 Now enter your **display name** (shown on QR):",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_NAME

async def received_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = update.effective_user.id
    user = get_user(db, uid)
    user["upi"]  = ctx.user_data.pop("temp_upi")
    user["name"] = update.message.text.strip()
    save_db(db)
    await update.message.reply_text(
        f"╔════════════════════════╗\n"
        f"║  ✅  PROFILE SAVED  ✅  ║\n"
        f"╚════════════════════════╝\n\n"
        f"💳 **UPI ID:** `{user['upi']}`\n"
        f"👤 **Name:**   {user['name']}\n\n"
        f"🎯 Now use /qr <amount> to generate your QR!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb()
    )
    return ConversationHandler.END

# ─────────────────────────────────────────────
#  /qr  ─ quick with saved UPI
# ─────────────────────────────────────────────
async def cmd_qr(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = update.effective_user.id
    user = get_user(db, uid)
    if not user["upi"]:
        await update.message.reply_text(
            "⚠️ No UPI ID saved!\nUse /setupi first.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 Set UPI Now", callback_data="edit_upi")
            ]])
        )
        return

    args = ctx.args
    if args:
        try:
            amount = float(args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Usage: /qr 500")
            return
        await _send_qr(update, ctx, user, amount)
    else:
        await update.message.reply_text(
            "💰 Select or enter an amount:",
            reply_markup=amount_quick_kb()
        )

async def _send_qr(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user: dict, amount: Optional[float]):
    db = load_db()
    uid = update.effective_user.id
    msg = update.message or update.callback_query.message

    status = await msg.reply_text("⚡ Generating your premium QR code...")

    try:
        logo_bytes = bytes(user["logo"]) if user.get("logo") else None
        img_bytes = generate_qr_image(
            user["upi"], user["name"], amount,
            style_key=user.get("style", "cosmic"),
            logo_bytes=logo_bytes,
        )
    except Exception as e:
        logger.error(f"QR gen error: {e}")
        await status.edit_text("❌ Failed to generate QR. Try again.")
        return

    user["qr_count"] += 1
    db["stats"]["total_qr"] += 1
    save_db(db)

    cap = (
        f"✨ *QR Code Generated!*\n\n"
        f"💳 `{user['upi']}`\n"
        f"👤 {user['name']}\n"
        f"💰 ₹{amount:.2f}\n"
        f"🎨 {QR_STYLES[user.get('style','cosmic')]['name']}\n\n"
        f"📱 _Scan with any UPI app_"
    ) if amount else (
        f"✨ *QR Code Generated!*\n\n"
        f"💳 `{user['upi']}`\n"
        f"👤 {user['name']}\n"
        f"💰 Any amount\n"
        f"🎨 {QR_STYLES[user.get('style','cosmic')]['name']}\n\n"
        f"📱 _Scan with any UPI app_"
    )

    close_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 New QR", callback_data="gen_qr"),
        InlineKeyboardButton("🎨 Style",  callback_data="style_menu"),
    ]])

    await msg.reply_photo(
        photo=InputFile(io.BytesIO(img_bytes), filename="qr.png"),
        caption=cap, parse_mode=ParseMode.MARKDOWN, reply_markup=close_kb
    )
    await status.delete()

# ─────────────────────────────────────────────
#  /newqr  ─ custom UPI (conversation)
# ─────────────────────────────────────────────
async def cmd_newqr(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "╔══════════════════════════════╗\n"
        "║  🆕  CUSTOM UPI QR GENERATOR ║\n"
        "╚══════════════════════════════╝\n\n"
        "📝 Enter in this format:\n"
        "`UPI_ID | Name | Amount`\n\n"
        "Example:\n"
        "`abc@ybl | John Doe | 250`\n\n"
        "_Amount is optional — leave blank for open amount._",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_CUSTOM_UPI_FULL

async def received_custom_upi_full(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    uid = update.effective_user.id
    user = get_user(db, uid)
    parts = [p.strip() for p in update.message.text.split("|")]
    if len(parts) < 2:
        await update.message.reply_text("❌ Invalid format. Use: `UPI | Name | Amount`", parse_mode=ParseMode.MARKDOWN)
        return WAITING_CUSTOM_UPI_FULL

    upi_id = parts[0]
    name   = parts[1]
    amount = None
    if len(parts) >= 3:
        try:
            amount = float(parts[2])
        except ValueError:
            amount = None

    status = await update.message.reply_text("⚡ Generating custom QR...")
    try:
        logo_bytes = bytes(user["logo"]) if user.get("logo") else None
        img_bytes  = generate_qr_image(upi_id, name, amount,
                                        style_key=user.get("style","cosmic"),
                                        logo_bytes=logo_bytes)
    except Exception as e:
        logger.error(e)
        await status.edit_text("❌ Failed. Try again.")
        return ConversationHandler.END

    user["qr_count"] += 1
    db["stats"]["total_qr"] += 1
    save_db(db)

    cap = (
        f"✨ *Custom QR Generated!*\n"
        f"💳 `{upi_id}`\n"
        f"👤 {name}\n"
        f"💰 {'₹' + str(amount) if amount else 'Open'}\n"
        f"🎨 {QR_STYLES[user.get('style','cosmic')]['name']}"
    )
    await update.message.reply_photo(
        photo=InputFile(io.BytesIO(img_bytes), filename="qr.png"),
        caption=cap, parse_mode=ParseMode.MARKDOWN
    )
    await status.delete()
    return ConversationHandler.END

# ─────────────────────────────────────────────
#  /style
# ─────────────────────────────────────────────
async def cmd_style(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    uid = update.effective_user.id
    user = get_user(db, uid)
    text = (
        "╔═══════════════════════════╗\n"
        "║  🎨  QR STYLE SELECTOR  🎨 ║\n"
        "╚═══════════════════════════╝\n\n"
        "Choose your visual style below.\n"
        "Each generates a unique look ✨"
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=style_menu_kb(user.get("style","cosmic")))
    else:
        await update.callback_query.edit_message_text(text, reply_markup=style_menu_kb(user.get("style","cosmic")))

# ─────────────────────────────────────────────
#  /myinfo
# ─────────────────────────────────────────────
async def cmd_myinfo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    uid  = update.effective_user.id
    user = get_user(db, uid)
    tg   = update.effective_user
    text = (
        "╔══════════════════════════╗\n"
        "║  👤  YOUR PROFILE  👤    ║\n"
        "╚══════════════════════════╝\n\n"
        f"🆔 **Telegram ID:** `{uid}`\n"
        f"👤 **Username:** @{tg.username or 'none'}\n"
        f"💳 **UPI ID:** `{user['upi'] or '—'}`\n"
        f"📛 **Display Name:** {user['name'] or '—'}\n"
        f"🎨 **Current Style:** {QR_STYLES.get(user.get('style','cosmic'), {}).get('name','—')}\n"
        f"🖼️ **Custom Logo:** {'✅' if user.get('logo') else '❌'}\n"
        f"📊 **QRs Generated:** {user['qr_count']}\n"
        f"📅 **Joined:** {user.get('joined','—')[:10]}\n"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())

# ─────────────────────────────────────────────
#  /stats
# ─────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    uid  = update.effective_user.id
    user = get_user(db, uid)
    text = (
        "╔═══════════════════════════╗\n"
        "║  📊  YOUR STATISTICS  📊  ║\n"
        "╚═══════════════════════════╝\n\n"
        f"🔢 **Total QRs Generated:** {user['qr_count']}\n"
        f"🎨 **Favourite Style:** {QR_STYLES.get(user.get('style','cosmic'),{}).get('name','—')}\n"
        f"📅 **Member Since:** {user.get('joined','—')[:10]}\n"
        f"🕒 **Last Active:** {(user.get('last_active') or '—')[:10]}\n\n"
        "Keep generating to climb the leaderboard! 🚀"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]])
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)

# ─────────────────────────────────────────────
#  LOGO  (conversation)
# ─────────────────────────────────────────────
async def cmd_setlogo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await (update.message or update.callback_query.message).reply_text(
        "🖼️ Send a **square image** (PNG/JPG) to use as your QR center logo.\n\n"
        "_It will be circularly cropped and embedded in the center._",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_LOGO

async def received_logo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    uid = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("❌ Please send an image (photo).")
        return WAITING_LOGO
    photo = await update.message.photo[-1].get_file()
    buf = io.BytesIO()
    await photo.download_to_memory(buf)
    user = get_user(db, uid)
    user["logo"] = list(buf.getvalue())   # store as list (JSON serializable)
    save_db(db)
    await update.message.reply_text("✅ **Logo saved!** It will appear centered on your QR codes.",
                                     parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_kb())
    return ConversationHandler.END

async def cmd_removelogo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    uid = update.effective_user.id
    user = get_user(db, uid)
    user["logo"] = None
    save_db(db)
    await update.message.reply_text("🗑️ Logo removed.", reply_markup=main_menu_kb())

# ─────────────────────────────────────────────
#  /removeupi
# ─────────────────────────────────────────────
async def cmd_removeupi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    uid = update.effective_user.id
    user = get_user(db, uid)
    user["upi"] = None
    user["name"] = None
    save_db(db)
    await update.message.reply_text("🗑️ UPI ID removed.", reply_markup=main_menu_kb())

# ─────────────────────────────────────────────
#  ADMIN: /addadmin  /rmadmin  /listadmins
# ─────────────────────────────────────────────
@owner_only
async def cmd_addadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args:
        await update.message.reply_text("Usage: /addadmin <user_id>"); return
    try:
        target = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid ID"); return
    if target not in db["admins"]:
        db["admins"].append(target)
        save_db(db)
        await update.message.reply_text(f"✅ User `{target}` promoted to **Admin**.",
                                         parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("ℹ️ Already an admin.")

@owner_only
async def cmd_rmadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args:
        await update.message.reply_text("Usage: /rmadmin <user_id>"); return
    try:
        target = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid ID"); return
    if target in db["admins"]:
        db["admins"].remove(target)
        save_db(db)
        await update.message.reply_text(f"🔻 User `{target}` removed from Admin.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("ℹ️ Not an admin.")

@admin_or_owner
async def cmd_listadmins(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    lines = [f"  • `{a}`" for a in db["admins"]] or ["  _None_"]
    await update.message.reply_text(
        "╔═══════════════════╗\n"
        "║  🛡️  ADMIN LIST  ║\n"
        "╚═══════════════════╝\n\n" +
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )

# ─────────────────────────────────────────────
#  ADMIN: /ban  /unban  /bannedlist
# ─────────────────────────────────────────────
@admin_or_owner
async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args:
        await update.message.reply_text("Usage: /ban <user_id>"); return
    try:
        target = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid ID"); return
    if target == OWNER_ID:
        await update.message.reply_text("⛔ Cannot ban the owner."); return
    if target not in db["banned"]:
        db["banned"].append(target)
        save_db(db)
        await update.message.reply_text(f"🚫 User `{target}` has been **banned**.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("ℹ️ Already banned.")

@admin_or_owner
async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args:
        await update.message.reply_text("Usage: /unban <user_id>"); return
    try:
        target = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid ID"); return
    if target in db["banned"]:
        db["banned"].remove(target)
        save_db(db)
        await update.message.reply_text(f"✅ User `{target}` **unbanned**.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("ℹ️ Not banned.")

@admin_or_owner
async def cmd_bannedlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    lines = [f"  • `{b}`" for b in db["banned"]] or ["  _None_"]
    await update.message.reply_text(
        "╔══════════════════════╗\n"
        "║  🚫  BANNED USERS  🚫 ║\n"
        "╚══════════════════════╝\n\n" + "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN
    )

# ─────────────────────────────────────────────
#  ADMIN: /globalstats
# ─────────────────────────────────────────────
@admin_or_owner
async def cmd_globalstats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    s = db["stats"]
    await update.message.reply_text(
        "╔════════════════════════════╗\n"
        "║  🌐  GLOBAL BOT STATS  🌐  ║\n"
        "╚════════════════════════════╝\n\n"
        f"👥 **Total Users:** {s['total_users']}\n"
        f"🖼️ **Total QRs Generated:** {s['total_qr']}\n"
        f"🛡️ **Admins:** {len(db['admins'])}\n"
        f"🚫 **Banned Users:** {len(db['banned'])}\n"
        f"📅 **Uptime Since:** Bot start",
        parse_mode=ParseMode.MARKDOWN
    )

# ─────────────────────────────────────────────
#  ADMIN: /userinfo
# ─────────────────────────────────────────────
@admin_or_owner
async def cmd_userinfo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args:
        await update.message.reply_text("Usage: /userinfo <user_id>"); return
    target = ctx.args[0]
    u = db["users"].get(target)
    if not u:
        await update.message.reply_text("❌ User not found."); return
    banned = int(target) in db["banned"]
    admin  = int(target) in db["admins"]
    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"║  🔍  USER DETAILS  🔍 ║\n"
        f"╚══════════════════════╝\n\n"
        f"🆔 **ID:** `{target}`\n"
        f"💳 **UPI:** `{u.get('upi') or '—'}`\n"
        f"📛 **Name:** {u.get('name') or '—'}\n"
        f"📊 **QRs:** {u.get('qr_count',0)}\n"
        f"🎨 **Style:** {u.get('style','—')}\n"
        f"📅 **Joined:** {(u.get('joined') or '—')[:10]}\n"
        f"🛡️ **Admin:** {'Yes' if admin else 'No'}\n"
        f"🚫 **Banned:** {'Yes' if banned else 'No'}",
        parse_mode=ParseMode.MARKDOWN
    )

# ─────────────────────────────────────────────
#  OWNER: /broadcast  (conversation)
# ─────────────────────────────────────────────
@owner_only
async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 Send the message you want to broadcast to ALL users.\n"
        "Supports text, photos, documents."
    )
    return WAITING_BROADCAST

@owner_only
async def do_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    users = list(db["users"].keys())
    ok = fail = 0
    status = await update.message.reply_text(f"📡 Broadcasting to {len(users)} users...")
    for uid_str in users:
        try:
            if update.message.photo:
                await ctx.bot.send_photo(int(uid_str), update.message.photo[-1].file_id,
                                          caption=update.message.caption or "")
            else:
                await ctx.bot.send_message(int(uid_str), update.message.text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Broadcast done!\n✔️ Sent: {ok}\n❌ Failed: {fail}")
    return ConversationHandler.END

# ─────────────────────────────────────────────
#  OWNER: /exportdb
# ─────────────────────────────────────────────
@owner_only
async def cmd_exportdb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(DB_FILE):
        await update.message.reply_document(
            document=InputFile(DB_FILE),
            caption="📦 Full database export"
        )
    else:
        await update.message.reply_text("❌ Database file not found.")

# ─────────────────────────────────────────────
#  CALLBACK QUERY ROUTER
# ─────────────────────────────────────────────
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    db  = load_db()
    await q.answer()

    data = q.data

    if data == "main_menu":
        name = q.from_user.first_name or "User"
        await q.edit_message_text(
            TEXTS["welcome"].format(name=name),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb()
        )

    elif data == "help":
        await cmd_help(update, ctx)

    elif data == "my_stats":
        await cmd_stats(update, ctx)

    elif data == "style_menu":
        user = get_user(db, uid)
        await q.edit_message_text(
            "🎨 *Select your QR Style:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=style_menu_kb(user.get("style","cosmic"))
        )

    elif data.startswith("setstyle_"):
        key = data.replace("setstyle_", "")
        if key in QR_STYLES:
            user = get_user(db, uid)
            user["style"] = key
            save_db(db)
            await q.edit_message_text(
                f"✅ Style set to **{QR_STYLES[key]['name']}**!\n\n"
                "Generate a QR to see it in action.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⚡ Generate QR", callback_data="gen_qr"),
                    InlineKeyboardButton("🔙 Back",        callback_data="style_menu"),
                ]])
            )

    elif data == "gen_qr":
        user = get_user(db, uid)
        if not user["upi"]:
            await q.edit_message_text(
                "⚠️ No UPI ID set!\nPlease set your UPI ID first.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("💳 Set UPI", callback_data="edit_upi"),
                    InlineKeyboardButton("🔙 Back",    callback_data="main_menu"),
                ]])
            )
        else:
            await q.edit_message_text(
                "💰 *Select Amount:*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=amount_quick_kb()
            )

    elif data.startswith("quick_amt_"):
        amount = float(data.replace("quick_amt_",""))
        user = get_user(db, uid)
        await _send_qr(update, ctx, user, amount)

    elif data == "custom_amount":
        await q.edit_message_text(
            "✏️ Send the custom amount (number only):",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Cancel", callback_data="gen_qr")
            ]])
        )
        ctx.user_data["awaiting_custom_amount"] = True

    elif data == "my_settings":
        user = get_user(db, uid)
        await q.edit_message_text(
            "╔══════════════════════════╗\n"
            "║  ⚙️  YOUR SETTINGS  ⚙️   ║\n"
            "╚══════════════════════════╝\n\n"
            f"💳 **UPI ID:** `{user.get('upi') or '—'}`\n"
            f"👤 **Name:** {user.get('name') or '—'}\n"
            f"🎨 **Style:** {QR_STYLES.get(user.get('style','cosmic'),{}).get('name','—')}\n"
            f"🖼️ **Logo:** {'✅ Set' if user.get('logo') else '❌ Not set'}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=settings_kb(user)
        )

    elif data in ("edit_upi", "clear_upi", "clear_logo", "set_logo"):
        if data == "clear_upi":
            user = get_user(db, uid)
            user["upi"] = None; user["name"] = None; save_db(db)
            await q.answer("🗑️ UPI cleared!", show_alert=True)
        elif data == "clear_logo":
            user = get_user(db, uid)
            user["logo"] = None; save_db(db)
            await q.answer("🗑️ Logo cleared!", show_alert=True)
        elif data in ("edit_upi", "set_logo"):
            cmd = "/setupi" if data == "edit_upi" else "/setlogo"
            await q.answer(f"Use {cmd} command in chat.", show_alert=True)

    elif data == "rate":
        await q.edit_message_text(
            "⭐ *Love this bot?*\n\n"
            "Share it with friends and help us grow!\n"
            "Your support keeps us running 🙏",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="main_menu")
            ]])
        )

# ─────────────────────────────────────────────
#  PLAIN MESSAGE  ─ catch custom amount input
# ─────────────────────────────────────────────
async def plain_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("awaiting_custom_amount"):
        ctx.user_data.pop("awaiting_custom_amount")
        try:
            amount = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Invalid amount."); return
        db   = load_db()
        uid  = update.effective_user.id
        user = get_user(db, uid)
        await _send_qr(update, ctx, user, amount)

# ─────────────────────────────────────────────
#  ERROR HANDLER
# ─────────────────────────────────────────────
async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {ctx.error}", exc_info=ctx.error)

# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversations
    setupi_conv = ConversationHandler(
        entry_points=[CommandHandler("setupi", cmd_setupi)],
        states={WAITING_UPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_upi)],
                WAITING_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, received_name)]},
        fallbacks=[], allow_reentry=True
    )
    newqr_conv = ConversationHandler(
        entry_points=[CommandHandler("newqr", cmd_newqr)],
        states={WAITING_CUSTOM_UPI_FULL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_custom_upi_full)]},
        fallbacks=[], allow_reentry=True
    )
    logo_conv = ConversationHandler(
        entry_points=[CommandHandler("setlogo", cmd_setlogo),
                      CallbackQueryHandler(cmd_setlogo, pattern="^set_logo$")],
        states={WAITING_LOGO: [MessageHandler(filters.PHOTO, received_logo)]},
        fallbacks=[], allow_reentry=True
    )
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", cmd_broadcast)],
        states={WAITING_BROADCAST: [MessageHandler(filters.ALL & ~filters.COMMAND, do_broadcast)]},
        fallbacks=[], allow_reentry=True
    )

    app.add_handler(setupi_conv)
    app.add_handler(newqr_conv)
    app.add_handler(logo_conv)
    app.add_handler(broadcast_conv)

    # Commands
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("menu",        cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("qr",          cmd_qr))
    app.add_handler(CommandHandler("style",       cmd_style))
    app.add_handler(CommandHandler("myinfo",      cmd_myinfo))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("removeupi",   cmd_removeupi))
    app.add_handler(CommandHandler("removelogo",  cmd_removelogo))
    # Admin
    app.add_handler(CommandHandler("addadmin",    cmd_addadmin))
    app.add_handler(CommandHandler("rmadmin",     cmd_rmadmin))
    app.add_handler(CommandHandler("listadmins",  cmd_listadmins))
    app.add_handler(CommandHandler("ban",         cmd_ban))
    app.add_handler(CommandHandler("unban",       cmd_unban))
    app.add_handler(CommandHandler("bannedlist",  cmd_bannedlist))
    app.add_handler(CommandHandler("globalstats", cmd_globalstats))
    app.add_handler(CommandHandler("userinfo",    cmd_userinfo))
    app.add_handler(CommandHandler("exportdb",    cmd_exportdb))

    # Callbacks & plain text
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_message))

    app.add_error_handler(error_handler)

    logger.info("🚀 UPI QR Ultra Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
