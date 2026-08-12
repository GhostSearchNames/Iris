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
# 1️⃣ НАСТРОЙКИ (ГЛАВНОЕ!)
# ==================================================

BOT_TOKEN = "1780244667:ZRL7qnnHfc1iaIonCOZPsnN3dBIwbfeaBgn"

# ПОДКЛЮЧЕНИЕ ЧЕРЕЗ TELESRV API
API_URL = "http://31.76.20.193:8081/bot"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# СОЗДАНИЕ БОТА С API
try:
    bot = Bot(token=BOT_TOKEN, base=API_URL)
    print(f"✅ Подключено к API: {API_URL}")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")
    bot = Bot(token=BOT_TOKEN)
    print("✅ Подключено к стандартному API")

dp = Dispatcher()

# ==================================================
# 2️⃣ БАЗА ДАННЫХ (ПОЛНАЯ)
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
        
        self.conn.commit()
        logger.info("✅ База данных создана/обновлена")

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
        return user[1] if user else 1000

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()
        self.add_transaction(user_id, "balance_change", amount, f"Изменение баланса на {amount}")

    def get_users(self):
        self.cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
        return [row[0] for row in self.cursor.fetchall()]

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
            self.update_balance(referrer_id, 50)
            self.cursor.execute("""
                UPDATE users SET referral_count = referral_count + 1 
                WHERE user_id = ?
            """, (referrer_id,))
            self.conn.commit()

    def add_transaction(self, user_id, type, amount, description):
        self.cursor.execute("""
            INSERT INTO transactions (user_id, type, amount, description)
            VALUES (?, ?, ?, ?)
        """, (user_id, type, amount, description))
        self.conn.commit()

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

    def set_admin_rank(self, user_id, rank):
        self.cursor.execute("UPDATE admins SET rank = ? WHERE user_id = ?", (rank, user_id))
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

db = Database()

# ==================================================
# 3️⃣ КОМАНДЫ
# ==================================================

@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    db.register_user(user_id)
    
    text = f"""
🌸 **IRIS BOT** 🌸

Привет, {message.from_user.first_name}!

🎲 **ИГРЫ:**
!рулетка [ставка] — русская рулетка (х2)
!кости [ставка] — бросок костей (х2)
!кто гей — случайный выбор 🏳️‍🌈
!кто — случайный человек

💕 **РП:**
!обнять @user
!поцеловать @user
!дать пять @user

💰 **ЭКОНОМИКА:**
!баланс — проверить баланс
!бонус — ежедневный бонус (+100💎)
!топ — топ игроков

👑 **АДМИНЫ:**
!админы — список админов

🔥 Удачи!
    """
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("balance"))
async def balance_command(message: Message):
    user_id = message.from_user.id
    balance = db.get_balance(user_id)
    await message.answer(f"💰 **Твой баланс:** {balance} 💎")

@dp.message(Command("bonus"))
async def bonus_command(message: Message):
    user_id = message.from_user.id
    
    if db.get_daily_bonus(user_id):
        db.update_balance(user_id, 100)
        db.set_daily_bonus(user_id)
        balance = db.get_balance(user_id)
        await message.answer(f"🎁 **БОНУС ПОЛУЧЕН!**\n+100 💎\n💰 Баланс: {balance} 💎")
    else:
        await message.answer("❌ Ты уже получил бонус сегодня!\nПриходи завтра! 🔥")

# ==================================================
# 4️⃣ ИГРЫ
# ==================================================

@dp.message()
async def handle_messages(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    if not text:
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
        
        dice = random.randint(1, 6)
        win = dice >= 4
        
        if win:
            db.update_balance(user_id, bet)
            await message.answer(f"🎲 **ВЫПАЛО: {dice}**\n🎉 **ТЫ ВЫИГРАЛ!**\n💰 +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            await message.answer(f"🎲 **ВЫПАЛО: {dice}**\n💀 **ТЫ ПРОИГРАЛ!**\n💸 -{bet} 💎")
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
    
    # ===== РП =====
    rp_commands = {
        "!обнять": "🤗 обнял(а)",
        "!поцеловать": "💋 поцеловал(а)",
        "!дать пять": "✋ дал(а) пять"
    }
    
    for cmd, action in rp_commands.items():
        if text.startswith(cmd):
            target = text.replace(cmd, "").strip()
            if not target:
                await message.answer(f"❌ Кого? Напиши: {cmd} @user")
                return
            await message.answer(f"💕 {message.from_user.first_name} {action} {target}! ❤️")
            return
    
    # ===== АДМИНЫ =====
    if text.startswith("!админы"):
        admins = db.get_all_admins()
        if not admins:
            await message.answer("👑 В стаффе пока никого нет!")
            return
        
        text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
        for admin_id, rank, nickname in admins:
            try:
                user = await bot.get_chat(admin_id)
                name = user.first_name or str(admin_id)
                if user.username:
                    name += f" (@{user.username})"
            except:
                name = str(admin_id)
            
            rank_names = {1: "🟢 Модератор", 2: "🔵 Старший модератор", 3: "🟣 Супер-модератор", 4: "🟠 Заместитель", 5: "🔴 Главный"}
            rank_name = rank_names.get(rank, f"Ранг {rank}")
            nick = f" [{nickname}]" if nickname else ""
            text += f"{rank_name} — {name}{nick}\n"
        
        await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        return

# ==================================================
# 5️⃣ ЗАПУСК
# ==================================================

async def main():
    print("\n" + "="*60)
    print("🌸 IRIS BOT ЗАПУЩЕН!")
    print("🎲 ИГРЫ АКТИВНЫ!")
    print("💕 РП КОМАНДЫ РАБОТАЮТ!")
    print("="*60 + "\n")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
