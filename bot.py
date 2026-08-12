import asyncio
import random
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode

# ========================================
# 1️⃣ НАСТРОЙКИ
# ========================================

BOT_TOKEN = "1780244667:ZRL7qnnHfc1iaIonCOZPsnN3dBIwbfeaBgn"
API_ID = 6  # Для OpenGram обычно 6
API_HASH = "eb06d4abfb49dc3eeb1aeb98ae0f581e"  # Дефолтный для telesrv

# ПОДКЛЮЧЕНИЕ К OPENGRAM
app = Client(
    "iris_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
    base_url="http://31.76.20.193:8081/",
    workers=10
)

# ========================================
# 2️⃣ БАЗА ДАННЫХ
# ========================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect("iris.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 1000,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                register_date TEXT DEFAULT CURRENT_TIMESTAMP,
                last_daily TEXT,
                referral_code TEXT UNIQUE,
                referral_count INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                rank INTEGER DEFAULT 1,
                nickname TEXT,
                added_by INTEGER
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER,
                chat_id INTEGER,
                until TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                banned_by INTEGER,
                reason TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                warned_by INTEGER,
                reason TEXT,
                date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()

    def register_user(self, user_id):
        if not self.get_user(user_id):
            code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
            self.cursor.execute("""
                INSERT INTO users (user_id, referral_code) VALUES (?, ?)
            """, (user_id, code))
            self.conn.commit()

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

    def get_balance(self, user_id):
        user = self.get_user(user_id)
        return user[1] if user else 1000

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def get_users(self):
        self.cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [row[0] for row in self.cursor.fetchall()]

    def get_top_players(self, limit=10):
        self.cursor.execute("""
            SELECT user_id, balance, wins, losses
            FROM users WHERE is_banned = 0
            ORDER BY balance DESC LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()

    def get_daily_bonus(self, user_id):
        user = self.get_user(user_id)
        if user:
            last = user[5]
            if last:
                last_date = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - last_date).days >= 1:
                    return True
            else:
                return True
        return False

    def set_daily_bonus(self, user_id):
        self.cursor.execute("UPDATE users SET last_daily = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_admin(self, user_id):
        self.cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_admin_rank(self, user_id):
        self.cursor.execute("SELECT rank FROM admins WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def get_all_admins(self):
        self.cursor.execute("SELECT user_id, rank, nickname FROM admins ORDER BY rank DESC")
        return self.cursor.fetchall()

    def add_admin(self, user_id, rank=1, nickname=None):
        self.cursor.execute("""
            INSERT OR REPLACE INTO admins (user_id, rank, nickname)
            VALUES (?, ?, ?)
        """, (user_id, rank, nickname))
        self.conn.commit()

    def remove_admin(self, user_id):
        self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def mute_user(self, user_id, chat_id, until):
        self.cursor.execute("""
            INSERT OR REPLACE INTO mutes (user_id, chat_id, until)
            VALUES (?, ?, ?)
        """, (user_id, chat_id, until))
        self.conn.commit()

    def unmute_user(self, user_id, chat_id):
        self.cursor.execute("DELETE FROM mutes WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        self.conn.commit()

    def is_muted(self, user_id, chat_id):
        self.cursor.execute("SELECT until FROM mutes WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        result = self.cursor.fetchone()
        if result:
            until = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            if datetime.now() < until:
                return True
            self.unmute_user(user_id, chat_id)
        return False

    def ban_user(self, user_id, chat_id, banned_by, reason=""):
        self.cursor.execute("""
            INSERT OR REPLACE INTO bans (user_id, chat_id, banned_by, reason)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, banned_by, reason))
        self.cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def unban_user(self, user_id):
        self.cursor.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
        self.cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_banned(self, user_id):
        self.cursor.execute("SELECT user_id FROM bans WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def add_warn(self, user_id, chat_id, warned_by, reason=""):
        self.cursor.execute("""
            INSERT INTO warns (user_id, chat_id, warned_by, reason)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, warned_by, reason))
        self.conn.commit()
        return self.get_warn_count(user_id)

    def get_warn_count(self, user_id):
        self.cursor.execute("SELECT COUNT(*) FROM warns WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()[0]

    def clear_warns(self, user_id):
        self.cursor.execute("DELETE FROM warns WHERE user_id = ?", (user_id,))
        self.conn.commit()

db = Database()

# ========================================
# 3️⃣ КОНСТАНТЫ
# ========================================

RANK_NAMES = {
    1: "🟢 Модератор",
    2: "🔵 Старший модератор",
    3: "🟣 Супер-модератор",
    4: "🟠 Заместитель",
    5: "🔴 Главный администратор"
}

def get_rank_name(rank):
    return RANK_NAMES.get(rank, "❓ Неизвестно")

# ========================================
# 4️⃣ КЛАВИАТУРЫ
# ========================================

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Игры", callback_data="games"),
         InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("👑 Админы", callback_data="admins"),
         InlineKeyboardButton("📊 Топ", callback_data="top")],
        [InlineKeyboardButton("🎁 Бонус", callback_data="bonus"),
         InlineKeyboardButton("⭐ Поддержать", callback_data="support")],
        [InlineKeyboardButton("📖 Помощь", callback_data="help")]
    ])

# ========================================
# 5️⃣ КОМАНДЫ
# ========================================

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    db.register_user(user_id)
    
    await message.reply_text(
        f"🌸 **IRIS BOT**\n\n"
        f"Привет, {message.from_user.first_name}!\n"
        f"💰 Баланс: {db.get_balance(user_id)} 💎\n\n"
        f"🎮 **ИГРЫ:**\n"
        f"!рулетка [ставка]\n"
        f"!кости [ставка]\n"
        f"!битва @user [ставка]\n"
        f"!кто гей\n"
        f"!кто\n"
        f"!угадай [число]\n\n"
        f"💕 **РП:**\n"
        f"!обнять @user\n"
        f"!поцеловать @user\n"
        f"!дать пять @user\n"
        f"!погладить @user\n"
        f"!укусить @user\n\n"
        f"👑 **АДМИНЫ:**\n"
        f"!админы\n"
        f"!мут @user [время]\n"
        f"!бан @user\n"
        f"!кик @user\n"
        f"!варн @user [причина]\n"
        f"!добавить @user [ранг]\n"
        f"!удалить @user",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )

@app.on_message(filters.command("balance"))
async def balance_cmd(client, message):
    await message.reply_text(f"💰 **Баланс:** {db.get_balance(message.from_user.id)} 💎")

@app.on_message(filters.command("bonus"))
async def bonus_cmd(client, message):
    user_id = message.from_user.id
    if db.get_daily_bonus(user_id):
        db.update_balance(user_id, 100)
        db.set_daily_bonus(user_id)
        await message.reply_text(f"🎁 **+100 💎**\n💰 Баланс: {db.get_balance(user_id)}")
    else:
        await message.reply_text("❌ Бонус уже получен сегодня!")

@app.on_message(filters.command("top"))
async def top_cmd(client, message):
    top = db.get_top_players(10)
    if not top:
        await message.reply_text("Пока нет игроков 😔")
        return
    text = "🏆 **ТОП ИГРОКОВ:**\n\n"
    for i, (uid, balance, wins, losses) in enumerate(top, 1):
        try:
            user = await client.get_users(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        text += f"{i}. {name} — {balance} 💎 (🏆{wins} ❌{losses})\n"
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("admins"))
async def admins_cmd(client, message):
    admins = db.get_all_admins()
    if not admins:
        await message.reply_text("👑 Админов пока нет!")
        return
    text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
    for uid, rank, nickname in admins:
        try:
            user = await client.get_users(uid)
            name = user.first_name or str(uid)
            if user.username:
                name += f" (@{user.username})"
        except:
            name = str(uid)
        rank_name = get_rank_name(rank)
        nick = f" [{nickname}]" if nickname else ""
        text += f"{rank_name} — {name}{nick}\n"
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "📖 **ВСЕ КОМАНДЫ**\n\n"
        "🎮 **ИГРЫ:**\n"
        "!рулетка [ставка]\n"
        "!кости [ставка]\n"
        "!битва @user [ставка]\n"
        "!кто гей\n"
        "!кто\n"
        "!угадай [число]\n\n"
        "💕 **РП:**\n"
        "!обнять @user\n"
        "!поцеловать @user\n"
        "!дать пять @user\n"
        "!погладить @user\n"
        "!укусить @user\n\n"
        "💰 **ЭКОНОМИКА:**\n"
        "/balance\n"
        "/bonus\n"
        "/top\n\n"
        "👑 **АДМИНЫ:**\n"
        "!админы — список\n"
        "!мут @user [время] — 1h, 1d, 30m\n"
        "!бан @user\n"
        "!кик @user\n"
        "!варн @user [причина]\n"
        "!добавить @user [ранг] — 1-5\n"
        "!удалить @user",
        parse_mode=ParseMode.MARKDOWN
    )

# ========================================
# 6️⃣ ОБРАБОТКА СООБЩЕНИЙ
# ========================================

@app.on_message(filters.text & filters.private)
async def handle_messages(client, message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    if not text:
        return
    
    if db.is_banned(user_id):
        await message.delete()
        return
    
    if db.is_muted(user_id, chat_id):
        await message.delete()
        return
    
    db.register_user(user_id)
    
    # ===== ИГРЫ =====
    if text.startswith("!рулетка"):
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !рулетка 50")
            return
        try:
            bet = int(parts[1])
        except:
            await message.reply_text("❌ Введи число!")
            return
        if bet < 1:
            await message.reply_text("❌ Ставка > 0!")
            return
        if db.get_balance(user_id) < bet:
            await message.reply_text(f"❌ Не хватает! У тебя {db.get_balance(user_id)} 💎")
            return
        if random.random() < 0.5:
            db.update_balance(user_id, bet)
            await message.reply_text(f"🎉 ВЫИГРАЛ! +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            await message.reply_text(f"💀 ПРОИГРАЛ! -{bet} 💎")
        return
    
    if text.startswith("!кости"):
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !кости 50")
            return
        try:
            bet = int(parts[1])
        except:
            await message.reply_text("❌ Введи число!")
            return
        if db.get_balance(user_id) < bet:
            await message.reply_text(f"❌ Не хватает! У тебя {db.get_balance(user_id)} 💎")
            return
        dice = random.randint(1, 6)
        if dice >= 4:
            db.update_balance(user_id, bet)
            await message.reply_text(f"🎲 ВЫПАЛО: {dice} 🎉 ВЫИГРАЛ! +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            await message.reply_text(f"🎲 ВЫПАЛО: {dice} 💀 ПРОИГРАЛ! -{bet} 💎")
        return
    
    if text.startswith("!битва"):
        parts = text.split()
        if len(parts) < 3:
            await message.reply_text("❌ !битва @user 50")
            return
        target_username = parts[1]
        try:
            bet = int(parts[2])
        except:
            await message.reply_text("❌ Введи число!")
            return
        if db.get_balance(user_id) < bet:
            await message.reply_text(f"❌ Не хватает! У тебя {db.get_balance(user_id)} 💎")
            return
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        if target_id == user_id:
            await message.reply_text("❌ Нельзя биться с собой!")
            return
        if db.get_balance(target_id) < bet:
            await message.reply_text("❌ У противника не хватает!")
            return
        winner = random.choice([user_id, target_id])
        if winner == user_id:
            db.update_balance(user_id, bet)
            db.update_balance(target_id, -bet)
            await message.reply_text(f"⚔️ ПОБЕДА! +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            db.update_balance(target_id, bet)
            await message.reply_text(f"⚔️ ПОРАЖЕНИЕ! -{bet} 💎")
        return
    
    if text == "!кто гей":
        users = db.get_users()
        if not users:
            await message.reply_text("😅 В чате никого нет!")
            return
        target = random.choice(users)
        try:
            user = await client.get_users(target)
            name = user.first_name or str(target)
        except:
            name = str(target)
        await message.reply_text(f"🏳️‍🌈 СЕГОДНЯШНИЙ ГЕЙ: {name}!")
        return
    
    if text == "!кто":
        users = db.get_users()
        if not users:
            await message.reply_text("😅 В чате никого нет!")
            return
        target = random.choice(users)
        try:
            user = await client.get_users(target)
            name = user.first_name or str(target)
        except:
            name = str(target)
        await message.reply_text(f"🎯 СЛУЧАЙНЫЙ ВЫБОР: {name}!")
        return
    
    if text.startswith("!угадай"):
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !угадай 5")
            return
        try:
            guess = int(parts[1])
        except:
            await message.reply_text("❌ Введи число!")
            return
        if guess < 1 or guess > 10:
            await message.reply_text("❌ Число 1-10!")
            return
        target = random.randint(1, 10)
        if guess == target:
            db.update_balance(user_id, 50)
            await message.reply_text(f"🎉 ПРАВИЛЬНО! Было {target}! +50 💎")
        else:
            await message.reply_text(f"❌ НЕ УГАДАЛ! Было {target}!")
        return
    
    # ===== РП =====
    rp = {
        "!обнять": "🤗 обнял(а)",
        "!поцеловать": "💋 поцеловал(а)",
        "!дать пять": "✋ дал(а) пять",
        "!погладить": "🫳 погладил(а)",
        "!укусить": "🦷 укусил(а)",
        "!кинуть": "💪 кинул(а)"
    }
    
    for cmd, action in rp.items():
        if text.startswith(cmd):
            target = text.replace(cmd, "").strip()
            if not target:
                await message.reply_text(f"❌ Кого? {cmd} @user")
                return
            await message.reply_text(f"💕 {message.from_user.first_name} {action} {target}! ❤️")
            return
    
    # ===== АДМИН КОМАНДЫ =====
    
    if text == "!админы" or text == "!стафф":
        admins = db.get_all_admins()
        if not admins:
            await message.reply_text("👑 Админов пока нет!")
            return
        text = "👑 **СОСТАВ СТАФФА:**\n\n"
        for uid, rank, nickname in admins:
            try:
                user = await client.get_users(uid)
                name = user.first_name or str(uid)
                if user.username:
                    name += f" (@{user.username})"
            except:
                name = str(uid)
            rank_name = get_rank_name(rank)
            nick = f" [{nickname}]" if nickname else ""
            text += f"{rank_name} — {name}{nick}\n"
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    if text.startswith("!мут"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 1:
            await message.reply_text("❌ Нет прав! Нужен ранг 1+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !мут @user 1h")
            return
        target_username = parts[1]
        duration = parts[2] if len(parts) > 2 else "1h"
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        time_map = {"h": 1, "d": 24, "m": 1/60}
        unit = duration[-1]
        if unit not in time_map:
            await message.reply_text("❌ Используй: 1h, 2h, 1d, 30m")
            return
        hours = int(duration[:-1]) * time_map[unit]
        until = datetime.now() + timedelta(hours=hours)
        db.mute_user(target_id, chat_id, until.strftime('%Y-%m-%d %H:%M:%S'))
        await message.reply_text(f"🔇 {target_username} замьючен на {duration}!")
        return
    
    if text.startswith("!бан"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 2:
            await message.reply_text("❌ Нет прав! Нужен ранг 2+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !бан @user")
            return
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        db.ban_user(target_id, chat_id, user_id, "")
        await message.reply_text(f"🚫 {target_username} забанен!")
        return
    
    if text.startswith("!разбан"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 3:
            await message.reply_text("❌ Нет прав! Нужен ранг 3+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !разбан @user")
            return
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        db.unban_user(target_id)
        await message.reply_text(f"✅ {target_username} разбанен!")
        return
    
    if text.startswith("!кик"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 1:
            await message.reply_text("❌ Нет прав! Нужен ранг 1+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !кик @user")
            return
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        await message.reply_text(f"👢 {target_username} кикнут!")
        return
    
    if text.startswith("!варн"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 2:
            await message.reply_text("❌ Нет прав! Нужен ранг 2+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !варн @user [причина]")
            return
        target_username = parts[1]
        reason = " ".join(parts[2:]) if len(parts) > 2 else "Без причины"
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        warn_count = db.add_warn(target_id, chat_id, user_id, reason)
        await message.reply_text(f"⚠️ {target_username} получил варн!\nПричина: {reason}\nВсего: {warn_count}/3")
        if warn_count >= 3:
            db.ban_user(target_id, chat_id, user_id, "3 варна")
            await message.reply_text(f"🚫 {target_username} забанен за 3 варна!")
        return
    
    if text.startswith("!снятьварн"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 3:
            await message.reply_text("❌ Нет прав! Нужен ранг 3+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !снятьварн @user")
            return
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        db.clear_warns(target_id)
        await message.reply_text(f"✅ У {target_username} сняты все варны!")
        return
    
    if text.startswith("!добавить"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 4:
            await message.reply_text("❌ Нет прав! Нужен ранг 4+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !добавить @user [ранг]")
            return
        target_username = parts[1]
        rank = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        if rank < 1 or rank > 5:
            await message.reply_text("❌ Ранг 1-5!")
            return
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        db.add_admin(target_id, rank)
        await message.reply_text(f"✅ {target_username} добавлен! Ранг: {get_rank_name(rank)}")
        return
    
    if text.startswith("!удалить"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 4:
            await message.reply_text("❌ Нет прав! Нужен ранг 4+")
            return
        parts = text.split()
        if len(parts) < 2:
            await message.reply_text("❌ !удалить @user")
            return
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await client.get_users(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        if not target_id:
            await message.reply_text("❌ Пользователь не найден!")
            return
        db.remove_admin(target_id)
        await message.reply_text(f"✅ {target_username} удалён из стаффа!")
        return

# ========================================
# 7️⃣ КНОПКИ
# ========================================

@app.on_callback_query()
async def handle_callback(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "games":
        await callback.message.reply_text(
            "🎲 **ИГРЫ:**\n\n"
            "!рулетка [ставка]\n"
            "!кости [ставка]\n"
            "!битва @user [ставка]\n"
            "!кто гей\n"
            "!кто\n"
            "!угадай [число]"
        )
        await callback.answer()
        return
    
    if data == "balance":
        await callback.message.reply_text(f"💰 **Баланс:** {db.get_balance(user_id)} 💎")
        await callback.answer()
        return
    
    if data == "admins":
        admins = db.get_all_admins()
        if not admins:
            await callback.message.reply_text("👑 Админов пока нет!")
            await callback.answer()
            return
        text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
        for uid, rank, nickname in admins:
            try:
                user = await client.get_users(uid)
                name = user.first_name or str(uid)
                if user.username:
                    name += f" (@{user.username})"
            except:
                name = str(uid)
            rank_name = get_rank_name(rank)
            nick = f" [{nickname}]" if nickname else ""
            text += f"{rank_name} — {name}{nick}\n"
        await callback.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "top":
        top = db.get_top_players(10)
        if not top:
            await callback.message.reply_text("Пока нет игроков 😔")
            await callback.answer()
            return
        text = "🏆 **ТОП ИГРОКОВ:**\n\n"
        for i, (uid, balance, wins, losses) in enumerate(top, 1):
            try:
                user = await client.get_users(uid)
                name = user.first_name or str(uid)
            except:
                name = str(uid)
            text += f"{i}. {name} — {balance} 💎 (🏆{wins} ❌{losses})\n"
        await callback.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "bonus":
        if db.get_daily_bonus(user_id):
            db.update_balance(user_id, 100)
            db.set_daily_bonus(user_id)
            await callback.message.reply_text(f"🎁 **+100 💎**\n💰 Баланс: {db.get_balance(user_id)}")
        else:
            await callback.message.reply_text("❌ Бонус уже получен сегодня!")
        await callback.answer()
        return
    
    if data == "support":
        await callback.message.reply_text(
            "⭐ **ПОДДЕРЖАТЬ БОТА** ⭐\n\n"
            "Напиши: .pay [сумма]\n"
            "Пример: .pay 50\n\n"
            "Спасибо! ❤️"
        )
        await callback.answer()
        return
    
    if data == "help":
        await help_cmd(client, callback.message)
        await callback.answer()
        return

# ========================================
# 8️⃣ ЗАПУСК
# ========================================

print("\n🌸 IRIS BOT (PYROGRAM) ЗАПУЩЕН!")
print("🎲 ИГРЫ АКТИВНЫ!")
print("💕 РП КОМАНДЫ РАБОТАЮТ!")
print("👑 АДМИН-ПАНЕЛЬ АКТИВНА!")
print("="*50)

app.run()
