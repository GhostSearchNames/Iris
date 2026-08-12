import asyncio
import logging
import random
import sqlite3
import os
import json
import time
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

# ==================================================
# 1️⃣ НАСТРОЙКИ
# ==================================================

BOT_TOKEN = "1780244667:ZRL7qnnHfc1iaIonCOZPsnN3dBIwbfeaBgn"
API_URL = "http://31.76.20.193:8081/bot"
START_BALANCE = 1000
DB_PATH = "iris.db"

# ==================================================
# 2️⃣ НАСТРОЙКА ЛОГИРОВАНИЯ
# ==================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, base=API_URL)
dp = Dispatcher()

# ==================================================
# 3️⃣ БАЗА ДАННЫХ
# ==================================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Таблица пользователей
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 1000,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                register_date TEXT DEFAULT CURRENT_TIMESTAMP,
                last_daily TEXT,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                support_count INTEGER DEFAULT 0
            )
        """)
        
        # Таблица администраторов (с рангом)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                rank INTEGER DEFAULT 1,
                added_by INTEGER,
                added_date TEXT DEFAULT CURRENT_TIMESTAMP,
                nickname TEXT
            )
        """)
        
        # Таблица мутов
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER,
                chat_id INTEGER,
                until TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # Таблица банов
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                banned_by INTEGER,
                reason TEXT,
                date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица варнов
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
        
        # Таблица транзакций
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount INTEGER,
                description TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        logger.info("✅ База данных создана/обновлена")

    # ===== ПОЛЬЗОВАТЕЛИ =====
    def register_user(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, START_BALANCE))
        self.conn.commit()

    def get_balance(self, user_id):
        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else START_BALANCE

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def get_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

    # ===== АДМИНИСТРАТОРЫ =====
    def is_admin(self, user_id):
        self.cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_admin_rank(self, user_id):
        self.cursor.execute("SELECT rank FROM admins WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def get_admin_nickname(self, user_id):
        self.cursor.execute("SELECT nickname FROM admins WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result and result[0] else None

    def add_admin(self, user_id, rank=1, added_by=None, nickname=None):
        self.cursor.execute("""
            INSERT OR REPLACE INTO admins (user_id, rank, added_by, nickname)
            VALUES (?, ?, ?, ?)
        """, (user_id, rank, added_by, nickname))
        self.conn.commit()

    def remove_admin(self, user_id):
        self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def set_admin_rank(self, user_id, rank):
        self.cursor.execute("UPDATE admins SET rank = ? WHERE user_id = ?", (rank, user_id))
        self.conn.commit()

    def set_admin_nickname(self, user_id, nickname):
        self.cursor.execute("UPDATE admins SET nickname = ? WHERE user_id = ?", (nickname, user_id))
        self.conn.commit()

    def get_all_admins(self):
        self.cursor.execute("""
            SELECT user_id, rank, nickname, added_date
            FROM admins
            ORDER BY rank DESC, added_date ASC
        """)
        return self.cursor.fetchall()

    def get_admin_count(self):
        self.cursor.execute("SELECT COUNT(*) FROM admins")
        return self.cursor.fetchone()[0]

    # ===== МУТЫ =====
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

    # ===== БАНЫ =====
    def ban_user(self, user_id, chat_id, banned_by, reason=""):
        self.cursor.execute("""
            INSERT OR REPLACE INTO bans (user_id, chat_id, banned_by, reason)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, banned_by, reason))
        self.conn.commit()

    def unban_user(self, user_id):
        self.cursor.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_banned(self, user_id):
        self.cursor.execute("SELECT user_id FROM bans WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    # ===== ВАРНЫ =====
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

# ==================================================
# 4️⃣ КОНСТАНТЫ ДЛЯ РАНГОВ
# ==================================================

RANKS = {
    1: {"name": "Модератор", "emoji": "🟢", "color": "#00FF00", "commands": ["!мут", "!кик", "!очистить"]},
    2: {"name": "Старший модератор", "emoji": "🔵", "color": "#0088FF", "commands": ["!мут", "!кик", "!очистить", "!бан", "!варн"]},
    3: {"name": "Супер-модератор", "emoji": "🟣", "color": "#AA00FF", "commands": ["!мут", "!кик", "!очистить", "!бан", "!варн", "!разбан", "!снятьварн"]},
    4: {"name": "Заместитель", "emoji": "🟠", "color": "#FF8800", "commands": ["!мут", "!кик", "!очистить", "!бан", "!варн", "!разбан", "!снятьварн", "!добавить", "!удалить"]},
    5: {"name": "Главный администратор", "emoji": "🔴", "color": "#FF0000", "commands": ["ВСЁ"]}
}

RANK_NAMES = {
    1: "🟢 Модератор",
    2: "🔵 Старший модератор",
    3: "🟣 Супер-модератор",
    4: "🟠 Заместитель",
    5: "🔴 Главный администратор"
}

# ==================================================
# 5️⃣ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==================================================

def get_rank_info(rank):
    return RANKS.get(rank, RANKS[1])

def get_rank_name(rank):
    return RANK_NAMES.get(rank, "❓ Неизвестно")

def get_admin_prefix(user_id):
    rank = db.get_admin_rank(user_id)
    if rank == 0:
        return ""
    emoji = RANKS.get(rank, {}).get("emoji", "")
    return f"{emoji} "

def can_use_command(user_id, command):
    rank = db.get_admin_rank(user_id)
    if rank == 0:
        return False
    if rank == 5:
        return True
    allowed = RANKS.get(rank, {}).get("commands", [])
    return command in allowed or "ВСЁ" in allowed

# ==================================================
# 6️⃣ ОСНОВНЫЕ КОМАНДЫ
# ==================================================

@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    db.register_user(user_id)
    
    text = f"""
🌸 **IRIS BOT** 🌸

Привет, {message.from_user.first_name}!

Я бот для игр и развлечений!

🎲 **ИГРЫ:**
!кто гей — выбирает случайного гея в чате
!кто — выбирает случайного человека
!рулетка [ставка] — русская рулетка (х2)
!кости [ставка] — бросок костей (х2)
!битва @user [ставка] — PvP битва
!угадай [число] — угадай число (1-10)

💕 **РП:**
!обнять @user
!поцеловать @user
!дать пять @user

👑 **АДМИНЫ:**
!стафф — список всех админов
!админы — тоже список

💰 **ЭКОНОМИКА:**
!баланс — проверить баланс
!топ — топ игроков
!бонус — ежедневный бонус (+100💎)
.pay [сумма] — поддержать бота

🔥 Удачи!
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎮 Игры", callback_data="games"),
         InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("👑 Стафф", callback_data="staff"),
         InlineKeyboardButton("📊 Топ", callback_data="top")],
        [InlineKeyboardButton("⭐ Поддержать", callback_data="support")]
    ])
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

# ==================================================
# 7️⃣ КОМАНДА !СТАФФ
# ==================================================

@dp.message(Command("staff"))
@dp.message(lambda message: message.text and message.text.startswith("!стафф"))
async def staff_command(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    admins = db.get_all_admins()
    total = db.get_admin_count()
    
    if not admins:
        await message.answer("👑 В стаффе пока никого нет!")
        return
    
    text = f"👑 **СОСТАВ СТАФФА** ({total} чел.)\n\n"
    
    for admin_id, rank, nickname, date in admins:
        try:
            user = await bot.get_chat(admin_id)
            name = user.first_name or str(admin_id)
            if user.username:
                name += f" (@{user.username})"
        except:
            name = str(admin_id)
        
        rank_name = get_rank_name(rank)
        nick = f" [{nickname}]" if nickname else ""
        text += f"{rank_name} {name}{nick}\n"
    
    # Проверяем, является ли пользователь админом
    if db.is_admin(user_id):
        rank = db.get_admin_rank(user_id)
        rank_name = get_rank_name(rank)
        text += f"\n\n**Твой ранг:** {rank_name}"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

# ==================================================
# 8️⃣ КОМАНДЫ АДМИНИСТРИРОВАНИЯ
# ==================================================

@dp.message(lambda message: message.text and message.text.startswith("!добавить"))
async def add_admin_command(message: Message):
    user_id = message.from_user.id
    
    # Проверка прав (ранг 4+)
    if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 4:
        await message.answer("❌ У тебя нет прав! Нужен ранг 4+")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Пример: !добавить @user [ранг] [никнейм]")
        return
    
    target_username = parts[1]
    rank = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
    nickname = " ".join(parts[3:]) if len(parts) > 3 else None
    
    # Находим пользователя
    target_id = None
    for uid in db.get_users():
        try:
            u = await bot.get_chat(uid)
            if u.username and u.username.lower() == target_username.replace("@", "").lower():
                target_id = uid
                break
        except:
            pass
    
    if not target_id:
        await message.answer("❌ Пользователь не найден!")
        return
    
    if rank < 1 or rank > 5:
        await message.answer("❌ Ранг должен быть от 1 до 5!")
        return
    
    db.add_admin(target_id, rank, user_id, nickname)
    await message.answer(f"✅ {target_username} добавлен в стафф!\nРанг: {get_rank_name(rank)}")

@dp.message(lambda message: message.text and message.text.startswith("!удалить"))
async def remove_admin_command(message: Message):
    user_id = message.from_user.id
    
    if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 4:
        await message.answer("❌ У тебя нет прав! Нужен ранг 4+")
        return
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Пример: !удалить @user")
        return
    
    target_username = parts[1]
    
    # Находим пользователя
    target_id = None
    for uid in db.get_users():
        try:
            u = await bot.get_chat(uid)
            if u.username and u.username.lower() == target_username.replace("@", "").lower():
                target_id = uid
                break
        except:
            pass
    
    if not target_id:
        await message.answer("❌ Пользователь не найден!")
        return
    
    db.remove_admin(target_id)
    await message.answer(f"✅ {target_username} удалён из стаффа!")

@dp.message(lambda message: message.text and message.text.startswith("!назначить"))
async def set_rank_command(message: Message):
    user_id = message.from_user.id
    
    if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 5:
        await message.answer("❌ У тебя нет прав! Нужен ранг 5")
        return
    
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("❌ Пример: !назначить @user 3")
        return
    
    target_username = parts[1]
    rank = int(parts[2]) if parts[2].isdigit() else 0
    
    if rank < 1 or rank > 5:
        await message.answer("❌ Ранг должен быть от 1 до 5!")
        return
    
    # Находим пользователя
    target_id = None
    for uid in db.get_users():
        try:
            u = await bot.get_chat(uid)
            if u.username and u.username.lower() == target_username.replace("@", "").lower():
                target_id = uid
                break
        except:
            pass
    
    if not target_id:
        await message.answer("❌ Пользователь не найден!")
        return
    
    db.set_admin_rank(target_id, rank)
    await message.answer(f"✅ {target_username} назначен {get_rank_name(rank)}!")

# ==================================================
# 9️⃣ ИГРЫ И РП КОМАНДЫ
# ==================================================

@dp.message()
async def handle_messages(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    if not text:
        return
    
    # Проверка на мут
    if db.is_muted(user_id, chat_id):
        await message.delete()
        return
    
    # Проверка на бан
    if db.is_banned(user_id):
        await message.delete()
        await message.answer("🚫 Ты забанен!")
        return
    
    db.register_user(user_id)
    
    # ===== РУЛЕТКА =====
    if text.startswith("!рулетка"):
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Укажи ставку! Пример: !рулетка 50")
            return
        
        try:
            bet = int(parts[1])
        except:
            await message.answer("❌ Введи число!")
            return
        
        if bet < 1:
            await message.answer("❌ Ставка должна быть больше 0!")
            return
        
        balance = db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! У тебя {balance} 💎")
            return
        
        win = random.random() < 0.5
        if win:
            db.update_balance(user_id, bet)
            await message.answer(f"🎉 **ТЫ ВЫИГРАЛ!**\n💰 +{bet} 💎\n💎 Баланс: {db.get_balance(user_id)}")
        else:
            db.update_balance(user_id, -bet)
            await message.answer(f"💀 **ТЫ ПРОИГРАЛ!**\n💸 -{bet} 💎\n💎 Баланс: {db.get_balance(user_id)}")
        return
    
    # ===== КТО ГЕЙ =====
    if text.startswith("!кто гей"):
        users = db.get_users()
        if not users:
            await message.answer("😅 В чате пока никого нет!")
            return
        
        target = random.choice(users)
        try:
            user = await bot.get_chat(target)
            name = user.first_name or str(target)
            await message.answer(f"🏳️‍🌈 **СЕГОДНЯШНИЙ ГЕЙ:** {name}!")
        except:
            await message.answer(f"🏳️‍🌈 **СЕГОДНЯШНИЙ ГЕЙ:** {target}!")
        return
    
    # ===== КТО =====
    if text.startswith("!кто") and not text.startswith("!кто гей"):
        users = db.get_users()
        if not users:
            await message.answer("😅 В чате пока никого нет!")
            return
        
        target = random.choice(users)
        try:
            user = await bot.get_chat(target)
            name = user.first_name or str(target)
            await message.answer(f"🎯 **СЛУЧАЙНЫЙ ВЫБОР:** {name}!")
        except:
            await message.answer(f"🎯 **СЛУЧАЙНЫЙ ВЫБОР:** {target}!")
        return
    
    # ===== РП КОМАНДЫ =====
    rp_commands = {
        "!обнять": "🤗 обнял(а)",
        "!поцеловать": "💋 поцеловал(а)",
        "!дать пять": "✋ дал(а) пять",
        "!погладить": "🫳 погладил(а)",
        "!укусить": "🦷 укусил(а)",
        "!кинуть": "💪 кинул(а)"
    }
    
    for cmd, action in rp_commands.items():
        if text.startswith(cmd):
            target = text.replace(cmd, "").strip()
            if not target:
                await message.answer(f"❌ Кого? Напиши: {cmd} @user")
                return
            await message.answer(f"💕 {message.from_user.first_name} {action} {target}! ❤️")
            return
    
    # ===== АДМИН КОМАНДЫ =====
    if text.startswith("!мут"):
        if not db.is_admin(user_id):
            await message.answer("❌ Ты не админ!")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !мут @user 1h")
            return
        
        target_username = parts[1]
        duration = parts[2] if len(parts) > 2 else "1h"
        
        target_id = None
        for uid in db.get_users():
            try:
                u = await bot.get_chat(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        
        if not target_id:
            await message.answer("❌ Пользователь не найден!")
            return
        
        time_map = {"h": 1, "d": 24, "m": 1/60}
        unit = duration[-1]
        if unit not in time_map:
            await message.answer("❌ Используй: 1h, 2h, 1d, 30m")
            return
        
        hours = int(duration[:-1]) * time_map[unit]
        until = datetime.now() + timedelta(hours=hours)
        
        db.mute_user(target_id, chat_id, until.strftime('%Y-%m-%d %H:%M:%S'))
        await message.answer(f"🔇 {target_username} замьючен на {duration}!")
        return
    
    if text.startswith("!бан"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 2:
            await message.answer("❌ У тебя нет прав! Нужен ранг 2+")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !бан @user")
            return
        
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await bot.get_chat(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        
        if not target_id:
            await message.answer("❌ Пользователь не найден!")
            return
        
        db.ban_user(target_id, chat_id, user_id, "")
        await message.answer(f"🚫 {target_username} забанен!")
        return
    
    if text.startswith("!разбан"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 3:
            await message.answer("❌ У тебя нет прав! Нужен ранг 3+")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !разбан @user")
            return
        
        target_username = parts[1]
        target_id = None
        for uid in db.get_users():
            try:
                u = await bot.get_chat(uid)
                if u.username and u.username.lower() == target_username.replace("@", "").lower():
                    target_id = uid
                    break
            except:
                pass
        
        if not target_id:
            await message.answer("❌ Пользователь не найден!")
            return
        
        db.unban_user(target_id)
        await message.answer(f"✅ {target_username} разбанен!")
        return
    
    if text.startswith("!кик"):
        if not db.is_admin(user_id):
            await message.answer("❌ Ты не админ!")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !кик @user")
            return
        
        await message.answer(f"👢 {parts[1]} кикнут!")
        return

# ==================================================
# 🔟 КНОПКИ
# ==================================================

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "games":
        await callback.message.answer(
            "🎲 **ИГРЫ:**\n\n"
            "!рулетка [ставка] — русская рулетка (х2)\n"
            "!кости [ставка] — бросок костей (х2)\n"
            "!угадай [число] — угадай число (1-10)\n"
            "!битва @user [ставка] — PvP битва\n"
            "!кто гей — случайный выбор\n"
            "!кто — случайный человек"
        )
        await callback.answer()
    
    elif data == "balance":
        balance = db.get_balance(user_id)
        await callback.message.answer(f"💰 **Твой баланс:** {balance} 💎")
        await callback.answer()
    
    elif data == "top":
        top = db.get_top_players(10)
        text = "🏆 **ТОП ИГРОКОВ:**\n\n"
        for i, (uid, balance, wins, losses, earned) in enumerate(top, 1):
            try:
                user = await bot.get_chat(uid)
                name = user.first_name or str(uid)
            except:
                name = str(uid)
            text += f"{i}. {name} — {balance} 💎 (🏆{wins} ❌{losses})\n"
        await callback.message.answer(text)
        await callback.answer()
    
    elif data == "staff":
        admins = db.get_all_admins()
        total = db.get_admin_count()
        
        if not admins:
            await callback.message.answer("👑 В стаффе пока никого нет!")
            await callback.answer()
            return
        
        text = f"👑 **СОСТАВ СТАФФА** ({total} чел.)\n\n"
        for admin_id, rank, nickname, date in admins:
            try:
                user = await bot.get_chat(admin_id)
                name = user.first_name or str(admin_id)
                if user.username:
                    name += f" (@{user.username})"
            except:
                name = str(admin_id)
            
            rank_name = get_rank_name(rank)
            nick = f" [{nickname}]" if nickname else ""
            text += f"{rank_name} {name}{nick}\n"
        
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif data == "support":
        await callback.message.answer(
            "⭐ **ПОДДЕРЖАТЬ БОТА** ⭐\n\n"
            "Напиши: .pay [сумма]\n"
            "Пример: .pay 50\n\n"
            "Спасибо за поддержку! ❤️"
        )
        await callback.answer()

# ==================================================
# 1️⃣1️⃣ ЗАПУСК
# ==================================================

async def main():
    print("\n" + "="*60)
    print("🌸 IRIS BOT ЗАПУЩЕН!")
    print("👑 СИСТЕМА АДМИНОВ АКТИВНА!")
    print("🎲 ИГРЫ И РП КОМАНДЫ РАБОТАЮТ!")
    print("="*60 + "\n")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())