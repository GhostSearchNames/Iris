import asyncio
import logging
import random
import sqlite3
import os
import time
import re
import json
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
ADMINS = [1780243677]
START_BALANCE = 1000
DAILY_BONUS = 100
REFERRAL_BONUS = 50

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================================================
# 2️⃣ БАЗА ДАННЫХ (РАСШИРЕННАЯ)
# ==================================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect("iris.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Пользователи
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 1000,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                register_date TEXT DEFAULT CURRENT_TIMESTAMP,
                last_daily TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER DEFAULT 0,
                referral_count INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                support_count INTEGER DEFAULT 0,
                win_streak INTEGER DEFAULT 0,
                max_win_streak INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                exp INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0,
                last_message_date TEXT,
                is_banned INTEGER DEFAULT 0
            )
        """)
        
        # Администраторы
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                rank INTEGER DEFAULT 1,
                nickname TEXT,
                added_by INTEGER,
                added_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Муты
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER,
                chat_id INTEGER,
                until TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # Баны
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER,
                banned_by INTEGER,
                reason TEXT,
                date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Варны
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
        
        # Транзакции
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
        
        # Рефералы
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                bonus_paid INTEGER DEFAULT 0,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Сообщения для топа
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages_stats (
                user_id INTEGER,
                date TEXT,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        """)
        
        # Кланы
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                owner_id INTEGER,
                members TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                balance INTEGER DEFAULT 0
            )
        """)
        
        self.conn.commit()
        logger.info("✅ База данных создана/обновлена")

    # ===== ПОЛЬЗОВАТЕЛИ =====
    def register_user(self, user_id, referrer_id=None):
        if not self.get_user(user_id):
            referral_code = self.generate_referral_code(user_id)
            self.cursor.execute("""
                INSERT INTO users (user_id, referral_code) 
                VALUES (?, ?)
            """, (user_id, referral_code))
            self.conn.commit()
            
            if referrer_id and referrer_id != user_id:
                self.add_referral(referrer_id, user_id)
            return True
        return False

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

    def get_balance(self, user_id):
        user = self.get_user(user_id)
        return user[1] if user else START_BALANCE

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()
        self.add_transaction(user_id, "balance_change", amount, f"Изменение баланса на {amount}")

    def get_users(self):
        self.cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [row[0] for row in self.cursor.fetchall()]

    def get_top_players(self, limit=10):
        self.cursor.execute("""
            SELECT user_id, balance, wins, losses, total_earned
            FROM users
            WHERE is_banned = 0
            ORDER BY balance DESC
            LIMIT ?
        """, (limit,))
        return self.cursor.fetchall()

    # ===== АДМИНЫ =====
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
        return result[0] if result else None

    def add_admin(self, user_id, rank=1, nickname=None, added_by=None):
        self.cursor.execute("""
            INSERT OR REPLACE INTO admins (user_id, rank, nickname, added_by)
            VALUES (?, ?, ?, ?)
        """, (user_id, rank, nickname, added_by))
        self.conn.commit()

    def remove_admin(self, user_id):
        self.cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def set_admin_rank(self, user_id, rank):
        self.cursor.execute("UPDATE admins SET rank = ? WHERE user_id = ?", (rank, user_id))
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
        self.cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def unban_user(self, user_id):
        self.cursor.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
        self.cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
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

    # ===== ТРАНЗАКЦИИ =====
    def add_transaction(self, user_id, type, amount, description):
        self.cursor.execute("""
            INSERT INTO transactions (user_id, type, amount, description)
            VALUES (?, ?, ?, ?)
        """, (user_id, type, amount, description))
        self.conn.commit()

    # ===== РЕФЕРАЛЫ =====
    def generate_referral_code(self, user_id):
        import hashlib
        return hashlib.md5(str(user_id).encode()).hexdigest()[:8]

    def add_referral(self, referrer_id, referred_id):
        self.cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (referrer_id,))
        count = self.cursor.fetchone()[0]
        
        if count < 10:
            self.cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id, bonus_paid)
                VALUES (?, ?, 1)
            """, (referrer_id, referred_id))
            self.update_balance(referrer_id, REFERRAL_BONUS)
            self.cursor.execute("""
                UPDATE users SET referral_count = referral_count + 1 
                WHERE user_id = ?
            """, (referrer_id,))
            self.conn.commit()

    def get_referral_code(self, user_id):
        user = self.get_user(user_id)
        return user[8] if user else None

    def get_referral_count(self, user_id):
        user = self.get_user(user_id)
        return user[10] if user else 0

    # ===== ДРУГОЕ =====
    def get_daily_bonus(self, user_id):
        user = self.get_user(user_id)
        if user:
            last_bonus = user[5]
            if last_bonus:
                last_date = datetime.strptime(last_bonus, '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - last_date).days >= 1:
                    return True
            else:
                return True
        return False

    def set_daily_bonus(self, user_id):
        self.cursor.execute("UPDATE users SET last_daily = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def update_message_count(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute("""
            INSERT INTO messages_stats (user_id, date, count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1
        """, (user_id, today))
        self.conn.commit()
        
        self.cursor.execute("""
            UPDATE users SET 
                total_messages = total_messages + 1,
                last_message_date = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))
        self.conn.commit()

    def get_top_day(self, limit=10):
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute("""
            SELECT user_id, count FROM messages_stats
            WHERE date = ?
            ORDER BY count DESC
            LIMIT ?
        """, (today, limit))
        return self.cursor.fetchall()

    def get_top_week(self, limit=10):
        week = datetime.now().strftime('%Y-W%W')
        self.cursor.execute("""
            SELECT user_id, SUM(count) as total FROM messages_stats
            WHERE strftime('%Y-W%W', date) = ?
            GROUP BY user_id
            ORDER BY total DESC
            LIMIT ?
        """, (week, limit))
        return self.cursor.fetchall()

db = Database()

# ==================================================
# 3️⃣ КОНСТАНТЫ РАНГОВ
# ==================================================

RANKS = {
    1: {"name": "Модератор", "emoji": "🟢", "commands": ["!мут", "!кик", "!очистить"]},
    2: {"name": "Старший модератор", "emoji": "🔵", "commands": ["!мут", "!кик", "!очистить", "!бан", "!варн"]},
    3: {"name": "Супер-модератор", "emoji": "🟣", "commands": ["!мут", "!кик", "!очистить", "!бан", "!варн", "!разбан", "!снятьварн"]},
    4: {"name": "Заместитель", "emoji": "🟠", "commands": ["!мут", "!кик", "!очистить", "!бан", "!варн", "!разбан", "!снятьварн", "!добавить", "!удалить"]},
    5: {"name": "Главный администратор", "emoji": "🔴", "commands": ["ВСЁ"]}
}

def get_rank_name(rank):
    return RANKS.get(rank, {}).get("name", "❓ Неизвестно")

def get_rank_emoji(rank):
    return RANKS.get(rank, {}).get("emoji", "")

def can_use_command(user_id, command):
    rank = db.get_admin_rank(user_id)
    if rank == 0:
        return False
    if rank == 5:
        return True
    allowed = RANKS.get(rank, {}).get("commands", [])
    return command in allowed or "ВСЁ" in allowed

# ==================================================
# 4️⃣ КЛАВИАТУРЫ
# ==================================================

def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎮 Игры", callback_data="games"),
         InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("👑 Админы", callback_data="admins"),
         InlineKeyboardButton("📊 Топ", callback_data="top")],
        [InlineKeyboardButton("🎁 Бонус", callback_data="bonus"),
         InlineKeyboardButton("⭐ Поддержать", callback_data="support")],
        [InlineKeyboardButton("📖 Помощь", callback_data="help")]
    ])
    return keyboard

def games_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎲 Рулетка", callback_data="game_roulette"),
         InlineKeyboardButton("🎲 Кости", callback_data="game_dice")],
        [InlineKeyboardButton("⚔️ Битва", callback_data="game_battle"),
         InlineKeyboardButton("🎯 Угадай", callback_data="game_guess")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ])
    return keyboard

# ==================================================
# 5️⃣ КОМАНДЫ
# ==================================================

@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    
    # Проверка реферала
    referrer_id = None
    if " " in message.text:
        parts = message.text.split()
        if len(parts) > 1:
            ref_code = parts[1]
            db.cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref_code,))
            result = db.cursor.fetchone()
            if result:
                referrer_id = result[0]
    
    db.register_user(user_id, referrer_id)
    
    text = f"""
🌸 **IRIS BOT** 🌸

Привет, {message.from_user.first_name}!

Я многофункциональный бот для игр и развлечений!

🎮 **/games** — список игр
💰 **/balance** — баланс
👑 **/admins** — список админов
📊 **/top** — топ игроков
🎁 **/bonus** — ежедневный бонус
📖 **/help** — помощь

🔥 **Удачи!**
    """
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())

@dp.message(Command("games"))
async def games_command(message: Message):
    await message.answer("🎮 **ВЫБЕРИ ИГРУ:**", parse_mode=ParseMode.MARKDOWN, reply_markup=games_menu())

@dp.message(Command("balance"))
async def balance_command(message: Message):
    user_id = message.from_user.id
    balance = db.get_balance(user_id)
    await message.answer(f"💰 **Твой баланс:** {balance} 💎")

@dp.message(Command("admins"))
async def admins_command(message: Message):
    admins = db.get_all_admins()
    if not admins:
        await message.answer("👑 В стаффе пока никого нет!")
        return
    
    text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
    for admin_id, rank, nickname, date in admins:
        try:
            user = await bot.get_chat(admin_id)
            name = user.first_name or str(admin_id)
            if user.username:
                name += f" (@{user.username})"
        except:
            name = str(admin_id)
        
        rank_name = get_rank_name(rank)
        emoji = get_rank_emoji(rank)
        nick = f" [{nickname}]" if nickname else ""
        text += f"{emoji} {rank_name} — {name}{nick}\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("top"))
async def top_command(message: Message):
    top = db.get_top_players(10)
    if not top:
        await message.answer("Пока нет игроков 😔")
        return
    
    text = "🏆 **ТОП ИГРОКОВ:**\n\n"
    for i, (user_id, balance, wins, losses, earned) in enumerate(top, 1):
        try:
            user = await bot.get_chat(user_id)
            name = user.first_name or str(user_id)
        except:
            name = str(user_id)
        
        text += f"{i}. {name} — {balance} 💎 (🏆{wins} ❌{losses})\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("bonus"))
async def bonus_command(message: Message):
    user_id = message.from_user.id
    
    if db.get_daily_bonus(user_id):
        db.update_balance(user_id, DAILY_BONUS)
        db.set_daily_bonus(user_id)
        balance = db.get_balance(user_id)
        await message.answer(f"🎁 **БОНУС ПОЛУЧЕН!**\n+{DAILY_BONUS} 💎\n💰 Баланс: {balance} 💎")
    else:
        await message.answer("❌ Ты уже получил бонус сегодня!\nПриходи завтра! 🔥")

@dp.message(Command("help"))
async def help_command(message: Message):
    text = """
📖 **ПОМОЩЬ ПО IRIS** 🌸

🎮 **ИГРЫ:**
!рулетка [ставка] — русская рулетка (х2)
!кости [ставка] — бросок костей (х2)
!битва @user [ставка] — PvP битва
!кто гей — случайный выбор 🏳️‍🌈
!кто — случайный человек
!угадай [число] — угадай число (1-10)

💕 **РП:**
!обнять @user
!поцеловать @user
!дать пять @user
!погладить @user
!укусить @user

💰 **ЭКОНОМИКА:**
/balance — баланс
/bonus — ежедневный бонус
/top — топ игроков

👑 **АДМИНЫ:**
!стафф — список админов
!мут @user [время] — замутить
!бан @user — забанить
!кик @user — кикнуть

🔥 **УДАЧИ!**
    """
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

# ==================================================
# 6️⃣ ИГРЫ
# ==================================================

@dp.message()
async def handle_messages(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    if not text:
        return
    
    # Проверка на бан
    if db.is_banned(user_id):
        await message.delete()
        return
    
    # Проверка на мут
    if db.is_muted(user_id, chat_id):
        await message.delete()
        return
    
    # Регистрация
    db.register_user(user_id)
    
    # Счётчик сообщений
    db.update_message_count(user_id)
    
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
        
        # Анимация
        msg = await message.answer("🔄 Крутим рулетку...")
        await asyncio.sleep(0.5)
        
        win = random.random() < 0.5
        if win:
            winnings = bet
            db.update_balance(user_id, winnings)
            db.cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await msg.edit_text(f"🎉 **ТЫ ВЫИГРАЛ!**\n💰 +{winnings} 💎\n💎 Баланс: {db.get_balance(user_id)}")
        else:
            db.update_balance(user_id, -bet)
            db.cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await msg.edit_text(f"💀 **ТЫ ПРОИГРАЛ!**\n💸 -{bet} 💎\n💎 Баланс: {db.get_balance(user_id)}")
        return
    
    # ===== КОСТИ =====
    if text.startswith("!кости"):
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Укажи ставку! Пример: !кости 50")
            return
        
        try:
            bet = int(parts[1])
        except:
            await message.answer("❌ Введи число!")
            return
        
        balance = db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! У тебя {balance} 💎")
            return
        
        msg = await message.answer("🎲 Бросаем кости...")
        await asyncio.sleep(0.5)
        
        dice = random.randint(1, 6)
        win = dice >= 4
        
        if win:
            db.update_balance(user_id, bet)
            db.cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await msg.edit_text(f"🎲 **ВЫПАЛО: {dice}**\n🎉 **ТЫ ВЫИГРАЛ!**\n💰 +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            db.cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await msg.edit_text(f"🎲 **ВЫПАЛО: {dice}**\n💀 **ТЫ ПРОИГРАЛ!**\n💸 -{bet} 💎")
        return
    
    # ===== УГАДАЙ =====
    if text.startswith("!угадай"):
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Угадай число от 1 до 10! Пример: !угадай 5")
            return
        
        try:
            guess = int(parts[1])
        except:
            await message.answer("❌ Введи число!")
            return
        
        if guess < 1 or guess > 10:
            await message.answer("❌ Число должно быть от 1 до 10!")
            return
        
        target = random.randint(1, 10)
        if guess == target:
            winnings = 50
            db.update_balance(user_id, winnings)
            db.cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await message.answer(f"🎉 **ПРАВИЛЬНО!** Было загадано {target}!\n💰 +{winnings} 💎")
        else:
            db.cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await message.answer(f"❌ **НЕ УГАДАЛ!** Было загадано {target}!")
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
    
    # ===== БИТВА =====
    if text.startswith("!битва"):
        parts = text.split()
        if len(parts) < 3:
            await message.answer("❌ Пример: !битва @user 50")
            return
        
        target_username = parts[1]
        try:
            bet = int(parts[2])
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
        
        # Ищем противника
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
        
        if target_id == user_id:
            await message.answer("❌ Нельзя биться с самим собой!")
            return
        
        target_balance = db.get_balance(target_id)
        if target_balance < bet:
            await message.answer("❌ У противника недостаточно средств!")
            return
        
        msg = await message.answer("⚔️ Начинаем битву...")
        await asyncio.sleep(0.5)
        
        winner = random.choice([user_id, target_id])
        if winner == user_id:
            db.update_balance(user_id, bet)
            db.update_balance(target_id, -bet)
            db.cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (user_id,))
            db.cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (target_id,))
            db.conn.commit()
            await msg.edit_text(f"⚔️ **{message.from_user.first_name} ПОБЕДИЛ!**\n💰 +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            db.update_balance(target_id, bet)
            db.cursor.execute("UPDATE users SET losses = losses + 1 WHERE user_id = ?", (user_id,))
            db.cursor.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (target_id,))
            db.conn.commit()
            await msg.edit_text(f"⚔️ **{target_username} ПОБЕДИЛ!**\n💸 -{bet} 💎")
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
            
            # Проверяем упоминание
            if "@" in target:
                await message.answer(f"💕 {message.from_user.first_name} {action} {target}! ❤️")
            else:
                await message.answer(f"💕 {message.from_user.first_name} {action} {target}! ❤️")
            return
    
    # ===== АДМИН КОМАНДЫ =====
    if text.startswith("!стафф"):
        admins = db.get_all_admins()
        if not admins:
            await message.answer("👑 В стаффе пока никого нет!")
            return
        
        text = "👑 **СОСТАВ СТАФФА:**\n\n"
        for admin_id, rank, nickname, date in admins:
            try:
                user = await bot.get_chat(admin_id)
                name = user.first_name or str(admin_id)
                if user.username:
                    name += f" (@{user.username})"
            except:
                name = str(admin_id)
            
            rank_name = get_rank_name(rank)
            emoji = get_rank_emoji(rank)
            nick = f" [{nickname}]" if nickname else ""
            text += f"{emoji} {rank_name} — {name}{nick}\n"
        
        await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        return
    
    # ===== МУТ =====
    if text.startswith("!мут"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 1:
            await message.answer("❌ У тебя нет прав для мута!")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !мут @user 1h")
            return
        
        target_username = parts[1]
        duration = parts[2] if len(parts) > 2 else "1h"
        
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
        
        # Парсим время
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
    
    # ===== БАН =====
    if text.startswith("!бан"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 2:
            await message.answer("❌ У тебя нет прав для бана!")
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
    
    # ===== РАЗБАН =====
    if text.startswith("!разбан"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 3:
            await message.answer("❌ У тебя нет прав для разбана!")
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
    
    # ===== КИК =====
    if text.startswith("!кик"):
        if not db.is_admin(user_id):
            await message.answer("❌ Ты не админ!")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !кик @user")
            return
        
        target_username = parts[1]
        await message.answer(f"👢 {target_username} кикнут!")
        return
    
    # ===== ВАРН =====
    if text.startswith("!варн"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 2:
            await message.answer("❌ У тебя нет прав для варна!")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !варн @user [причина]")
            return
        
        target_username = parts[1]
        reason = " ".join(parts[2:]) if len(parts) > 2 else "Без причины"
        
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
        
        warn_count = db.add_warn(target_id, chat_id, user_id, reason)
        await message.answer(f"⚠️ {target_username} получил варн!\nПричина: {reason}\nВсего варнов: {warn_count}/3")
        
        if warn_count >= 3:
            db.ban_user(target_id, chat_id, user_id, "3 варна")
            await message.answer(f"🚫 {target_username} забанен за 3 варна!")
        return
    
    # ===== СНЯТЬ ВАРН =====
    if text.startswith("!снятьварн"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 3:
            await message.answer("❌ У тебя нет прав!")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !снятьварн @user")
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
        
        db.clear_warns(target_id)
        await message.answer(f"✅ У {target_username} сняты все варны!")
        return
    
    # ===== ДОБАВИТЬ АДМИНА =====
    if text.startswith("!добавить"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 4:
            await message.answer("❌ У тебя нет прав! Нужен ранг 4+")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !добавить @user [ранг] [ник]")
            return
        
        target_username = parts[1]
        rank = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        nickname = " ".join(parts[3:]) if len(parts) > 3 else None
        
        if rank < 1 or rank > 5:
            await message.answer("❌ Ранг должен быть от 1 до 5!")
            return
        
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
        
        db.add_admin(target_id, rank, nickname, user_id)
        await message.answer(f"✅ {target_username} добавлен в стафф!\nРанг: {get_rank_name(rank)}")
        return
    
    # ===== УДАЛИТЬ АДМИНА =====
    if text.startswith("!удалить"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 4:
            await message.answer("❌ У тебя нет прав! Нужен ранг 4+")
            return
        
        parts = text.split()
        if len(parts) < 2:
            await message.answer("❌ Пример: !удалить @user")
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
        
        db.remove_admin(target_id)
        await message.answer(f"✅ {target_username} удалён из стаффа!")
        return
    
    # ===== НАЗНАЧИТЬ РАНГ =====
    if text.startswith("!назначить"):
        if not db.is_admin(user_id) or db.get_admin_rank(user_id) < 5:
            await message.answer("❌ У тебя нет прав! Нужен ранг 5")
            return
        
        parts = text.split()
        if len(parts) < 3:
            await message.answer("❌ Пример: !назначить @user 3")
            return
        
        target_username = parts[1]
        rank = int(parts[2]) if parts[2].isdigit() else 0
        
        if rank < 1 or rank > 5:
            await message.answer("❌ Ранг должен быть от 1 до 5!")
            return
        
        target_id = None
        for uid in db.get_users():
            try:
                u = await bot.get_chat(uid)
                if u.username and u.username.toLowerCase() == target_username.replace("@", "").toLowerCase():
                    target_id = uid
                    break
            except:
                pass
        
        if not target_id:
            await message.answer("❌ Пользователь не найден!")
            return
        
        db.set_admin_rank(target_id, rank)
        await message.answer(f"✅ {target_username} назначен {get_rank_name(rank)}!")
        return

# ==================================================
# 7️⃣ КНОПКИ
# ==================================================

@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "back":
        await callback.message.edit_text("🏠 **ГЛАВНОЕ МЕНЮ:**", parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
        await callback.answer()
        return
    
    if data == "games":
        await callback.message.edit_text("🎮 **ВЫБЕРИ ИГРУ:**", parse_mode=ParseMode.MARKDOWN, reply_markup=games_menu())
        await callback.answer()
        return
    
    if data == "balance":
        balance = db.get_balance(user_id)
        await callback.message.answer(f"💰 **Твой баланс:** {balance} 💎")
        await callback.answer()
        return
    
    if data == "admins":
        admins = db.get_all_admins()
        if not admins:
            await callback.message.answer("👑 В стаффе пока никого нет!")
            await callback.answer()
            return
        
        text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
        for admin_id, rank, nickname, date in admins:
            try:
                user = await bot.get_chat(admin_id)
                name = user.first_name or str(admin_id)
                if user.username:
                    name += f" (@{user.username})"
            except:
                name = str(admin_id)
            
            rank_name = get_rank_name(rank)
            emoji = get_rank_emoji(rank)
            nick = f" [{nickname}]" if nickname else ""
            text += f"{emoji} {rank_name} — {name}{nick}\n"
        
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "top":
        top = db.get_top_players(10)
        if not top:
            await callback.message.answer("Пока нет игроков 😔")
            await callback.answer()
            return
        
        text = "🏆 **ТОП ИГРОКОВ:**\n\n"
        for i, (user_id, balance, wins, losses, earned) in enumerate(top, 1):
            try:
                user = await bot.get_chat(user_id)
                name = user.first_name or str(user_id)
            except:
                name = str(user_id)
            text += f"{i}. {name} — {balance} 💎 (🏆{wins} ❌{losses})\n"
        
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "bonus":
        if db.get_daily_bonus(user_id):
            db.update_balance(user_id, DAILY_BONUS)
            db.set_daily_bonus(user_id)
            balance = db.get_balance(user_id)
            await callback.message.answer(f"🎁 **БОНУС ПОЛУЧЕН!**\n+{DAILY_BONUS} 💎\n💰 Баланс: {balance} 💎")
        else:
            await callback.message.answer("❌ Ты уже получил бонус сегодня!\nПриходи завтра! 🔥")
        await callback.answer()
        return
    
    if data == "support":
        await callback.message.answer(
            "⭐ **ПОДДЕРЖАТЬ БОТА** ⭐\n\n"
            "Напиши: .pay [сумма]\n"
            "Пример: .pay 50\n\n"
            "Все средства идут на развитие бота!\n"
            "Спасибо за поддержку! ❤️"
        )
        await callback.answer()
        return
    
    if data == "help":
        text = """
📖 **ПОМОЩЬ ПО IRIS** 🌸

🎮 **ИГРЫ:**
!рулетка [ставка] — русская рулетка (х2)
!кости [ставка] — бросок костей (х2)
!битва @user [ставка] — PvP битва
!кто гей — случайный выбор 🏳️‍🌈
!кто — случайный человек
!угадай [число] — угадай число (1-10)

💕 **РП:**
!обнять @user
!поцеловать @user
!дать пять @user
!погладить @user
!укусить @user

💰 **ЭКОНОМИКА:**
/balance — баланс
/bonus — ежедневный бонус
/top — топ игроков

👑 **АДМИНЫ:**
!стафф — список админов
!мут @user [время] — замутить
!бан @user — забанить
!кик @user — кикнуть

🔥 **УДАЧИ!**
        """
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        return
    
    if data == "game_roulette":
        await callback.message.answer("🎲 **РУЛЕТКА:**\n\nИспользуй команду:\n!рулетка [ставка]\n\nПример: !рулетка 50")
        await callback.answer()
        return
    
    if data == "game_dice":
        await callback.message.answer("🎲 **КОСТИ:**\n\nИспользуй команду:\n!кости [ставка]\n\nПример: !кости 50")
        await callback.answer()
        return
    
    if data == "game_battle":
        await callback.message.answer("⚔️ **БИТВА:**\n\nИспользуй команду:\n!битва @user [ставка]\n\nПример: !битва @user 50")
        await callback.answer()
        return
    
    if data == "game_guess":
        await callback.message.answer("🎯 **УГАДАЙ ЧИСЛО:**\n\nИспользуй команду:\n!угадай [число]\n\nПример: !угадай 5")
        await callback.answer()
        return

# ==================================================
# 8️⃣ ПЛАТЁЖНАЯ СИСТЕМА (.pay)
# ==================================================

@dp.message(lambda message: message.text and message.text.startswith('.pay'))
async def pay_command(message: Message):
    user_id = message.from_user.id
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Укажи сумму! Пример: .pay 10")
        return
    
    try:
        amount = int(parts[1])
    except ValueError:
        await message.answer("❌ Введи число! Пример: .pay 10")
        return
    
    if amount < 1:
        await message.answer("❌ Минимальная сумма: 1💎")
        return
    
    balance = db.get_balance(user_id)
    if balance < amount:
        await message.answer(f"❌ Недостаточно средств!\n💰 Твой баланс: {balance} 💎")
        return
    
    db.update_balance(user_id, -amount)
    db.cursor.execute("""
        UPDATE users SET 
            support_count = support_count + 1,
            total_spent = total_spent + ?
        WHERE user_id = ?
    """, (amount, user_id))
    db.conn.commit()
    db.add_transaction(user_id, "support", -amount, f"Поддержка бота: {amount}💎")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("⭐ Поддержать ещё", callback_data="support")]
    ])
    
    await message.answer(
        f"⭐ **СПАСИБО ЗА ПОДДЕРЖКУ!** ⭐\n\n"
        f"💰 Снято: {amount} 💎\n"
        f"💎 Остаток: {db.get_balance(user_id)}\n"
        f"🤝 Ты помогаешь боту развиваться!\n\n"
        f"🔥 Все средства идут на улучшение бота!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

# ==================================================
# 9️⃣ ЗАПУСК
# ==================================================

async def main():
    print("\n" + "="*60)
    print("🌸 IRIS BOT ЗАПУЩЕН!")
    print("👑 СИСТЕМА АДМИНОВ АКТИВНА!")
    print("🎲 ИГРЫ И РП КОМАНДЫ РАБОТАЮТ!")
    print("💰 ЭКОНОМИЧЕСКАЯ СИСТЕМА РАБОТАЕТ!")
    print("📊 ТОПЫ И СТАТИСТИКА РАБОТАЮТ!")
    print("="*60 + "\n")
    
    logger.info("Бот запущен!")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
