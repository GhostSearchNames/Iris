import asyncio
import logging
import random
import sqlite3
import os
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

# ПОДКЛЮЧЕНИЕ К API (пробуем оба варианта)
API_URL = "http://31.76.20.193:8081/bot"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# СОЗДАНИЕ БОТА
try:
    bot = Bot(token=BOT_TOKEN, base=API_URL)
    print(f"✅ Подключено к API: {API_URL}")
except:
    bot = Bot(token=BOT_TOKEN)
    print("✅ Подключено к стандартному API")

dp = Dispatcher()

# ==================================================
# 2️⃣ БАЗА ДАННЫХ
# ==================================================

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
                last_daily TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                rank INTEGER DEFAULT 1
            )
        """)
        
        self.conn.commit()
        logger.info("✅ База данных создана/обновлена")

    def register_user(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        self.conn.commit()

    def get_balance(self, user_id):
        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 1000

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def get_users(self):
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]

    def is_admin(self, user_id):
        self.cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def get_admin_rank(self, user_id):
        self.cursor.execute("SELECT rank FROM admins WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result[0] if result else 0

    def get_all_admins(self):
        self.cursor.execute("SELECT user_id, rank FROM admins ORDER BY rank DESC")
        return self.cursor.fetchall()

db = Database()

# ==================================================
# 3️⃣ КЛАВИАТУРЫ
# ==================================================

def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎮 Игры", callback_data="games"),
         InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("👑 Админы", callback_data="admins"),
         InlineKeyboardButton("🎁 Бонус", callback_data="bonus")],
        [InlineKeyboardButton("⭐ Поддержать", callback_data="support")]
    ])
    return keyboard

# ==================================================
# 4️⃣ КОМАНДЫ
# ==================================================

@dp.message(Command("start"))
async def start_command(message: Message):
    user_id = message.from_user.id
    db.register_user(user_id)
    
    text = f"""
🌸 **IRIS BOT** 🌸

Привет, {message.from_user.first_name}!

🎲 **ИГРЫ:**
!кто гей — случайный выбор 🏳️‍🌈
!кто — случайный человек
!рулетка [ставка] — русская рулетка (х2)
!кости [ставка] — бросок костей (х2)
!битва @user [ставка] — PvP битва

💕 **РП:**
!обнять @user
!поцеловать @user
!дать пять @user

💰 **ЭКОНОМИКА:**
!баланс — проверить баланс
!бонус — ежедневный бонус (+100💎)
!топ — топ игроков

🔥 Удачи!
    """
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())

@dp.message(Command("balance"))
async def balance_command(message: Message):
    user_id = message.from_user.id
    balance = db.get_balance(user_id)
    await message.answer(f"💰 **Твой баланс:** {balance} 💎")

@dp.message(Command("bonus"))
async def bonus_command(message: Message):
    user_id = message.from_user.id
    
    db.cursor.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    result = db.cursor.fetchone()
    
    if result and result[0]:
        last = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last).days >= 1:
            db.update_balance(user_id, 100)
            db.cursor.execute("UPDATE users SET last_daily = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
            db.conn.commit()
            await message.answer("🎁 **Бонус получен!** +100 💎")
        else:
            await message.answer("❌ Ты уже получил бонус сегодня!")
    else:
        db.update_balance(user_id, 100)
        db.cursor.execute("UPDATE users SET last_daily = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        db.conn.commit()
        await message.answer("🎁 **Бонус получен!** +100 💎")

# ==================================================
# 5️⃣ ИГРЫ
# ==================================================

@dp.message()
async def handle_messages(message: Message):
    user_id = message.from_user.id
    text = message.text
    chat_id = message.chat.id
    
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
        
        balance = db.get_balance(user_id)
        if balance < bet:
            await message.answer(f"❌ Недостаточно средств! У тебя {balance} 💎")
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
        
        target_balance = db.get_balance(target_id)
        if target_balance < bet:
            await message.answer("❌ У противника недостаточно средств!")
            return
        
        winner = random.choice([user_id, target_id])
        if winner == user_id:
            db.update_balance(user_id, bet)
            db.update_balance(target_id, -bet)
            await message.answer(f"⚔️ **{message.from_user.first_name} ПОБЕДИЛ!**\n💰 +{bet} 💎")
        else:
            db.update_balance(user_id, -bet)
            db.update_balance(target_id, bet)
            await message.answer(f"⚔️ **{target_username} ПОБЕДИЛ!**\n💸 -{bet} 💎")
        return
    
    # ===== РП КОМАНДЫ =====
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
    
    # ===== АДМИН КОМАНДА =====
    if text.startswith("!админы"):
        admins = db.get_all_admins()
        if not admins:
            await message.answer("👑 В стаффе пока никого нет!")
            return
        
        text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
        for admin_id, rank in admins:
            try:
                user = await bot.get_chat(admin_id)
                name = user.first_name or str(admin_id)
            except:
                name = str(admin_id)
            text += f"{name} (ранг {rank})\n"
        
        await message.answer(text, parse_mode=ParseMode.MARKDOWN)
        return

# ==================================================
# 6️⃣ КНОПКИ
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
            "!битва @user [ставка] — PvP битва\n"
            "!кто гей — случайный выбор\n"
            "!кто — случайный человек"
        )
        await callback.answer()
    
    elif data == "balance":
        balance = db.get_balance(user_id)
        await callback.message.answer(f"💰 **Твой баланс:** {balance} 💎")
        await callback.answer()
    
    elif data == "admins":
        admins = db.get_all_admins()
        if not admins:
            await callback.message.answer("👑 В стаффе пока никого нет!")
            await callback.answer()
            return
        
        text = "👑 **АДМИНИСТРАТОРЫ:**\n\n"
        for admin_id, rank in admins:
            try:
                user = await bot.get_chat(admin_id)
                name = user.first_name or str(admin_id)
            except:
                name = str(admin_id)
            text += f"{name} (ранг {rank})\n"
        
        await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
    
    elif data == "bonus":
        await bonus_command(callback.message)
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
# 7️⃣ ЗАПУСК
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
