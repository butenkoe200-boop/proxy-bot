import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from yookassa import Payment, Configuration
import os

API_TOKEN = os.getenv("API_TOKEN")
SHOP_ID = os.getenv("SHOP_ID")
SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ===== БД =====
conn = sqlite3.connect("db.sqlite")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, key TEXT, expire TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, used INTEGER)")
conn.commit()

# ===== КЛЮЧИ =====
keys_list = [
# ВСТАВЬ СВОИ 20 КЛЮЧЕЙ СЮДА
]

for k in keys_list:
    cursor.execute("INSERT OR IGNORE INTO keys VALUES (?, 0)", (k,))
conn.commit()

payments = {}

def get_key():
    cursor.execute("SELECT key FROM keys WHERE used=0 LIMIT 1")
    row = cursor.fetchone()
    if not row:
        return None
    key = row[0]
    cursor.execute("UPDATE keys SET used=1 WHERE key=?", (key,))
    conn.commit()
    return key

def create_payment(user_id):
    payment = Payment.create({
        "amount": {"value": "149.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/antibloktg_bot"},
        "capture": True,
        "description": str(user_id)
    }, uuid.uuid4())

    payments[payment.id] = user_id
    return payment.confirmation.confirmation_url

# ===== СТАРТ =====
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Купить", callback_data="buy"))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))

    await message.answer("🚀 Telegram без блокировок\n1 устройство = 1 ключ", reply_markup=kb)

# ===== ПОКУПКА =====
@dp.callback_query_handler(lambda c: c.data == "buy")
async def buy(callback: types.CallbackQuery):
    url = create_payment(callback.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=url))

    await bot.send_message(callback.from_user.id, "Оплати доступ:", reply_markup=kb)

# ===== ПРОВЕРКА ОПЛАТ =====
async def check():
    while True:
        for pid in list(payments.keys()):
            payment = Payment.find_one(pid)

            if payment.status == "succeeded":
                user_id = payments[pid]

                cursor.execute("SELECT key, expire FROM users WHERE user_id=?", (user_id,))
                user = cursor.fetchone()

                if user:
                    expire = datetime.fromisoformat(user[1])
                    new_expire = max(expire, datetime.now()) + timedelta(days=30)

                    cursor.execute("UPDATE users SET expire=? WHERE user_id=?", (new_expire.isoformat(), user_id))
                    await bot.send_message(user_id, f"🔄 Продлено до {new_expire}")

                else:
                    key = get_key()
                    if not key:
                        await bot.send_message(user_id, "❌ Нет ключей")
                        continue

                    expire = datetime.now() + timedelta(days=30)
                    cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, key, expire.isoformat()))

                    await bot.send_message(user_id, f"🔐 {key}\nДо: {expire}")

                conn.commit()
                del payments[pid]

        await asyncio.sleep(10)

# ===== АДМИН =====
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]

    await message.answer(f"👥 Пользователей: {count}")

# ===== ЗАПУСК =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check())
    executor.start_polling(dp, skip_updates=True)
