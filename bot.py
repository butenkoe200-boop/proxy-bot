import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from yookassa import Payment, Configuration
import os

# ===== НАСТРОЙКИ =====
API_TOKEN = os.getenv("API_TOKEN")
SHOP_ID = os.getenv("SHOP_ID")
SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_ID = 6542324565

Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ===== БАЗА =====
conn = sqlite3.connect("db.sqlite")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, key TEXT, expire TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS keys (key TEXT PRIMARY KEY, used INTEGER)")
conn.commit()

# ===== ВСЕ ТВОИ КЛЮЧИ =====
keys_list = [

# SERVER 1
"https://t.me/proxy?server=213.165.42.119&port=10001&secret=6b49b65e410394f11cd429a6b7d84e98",
"https://t.me/proxy?server=213.165.42.119&port=10002&secret=5a7b65bfda62dda68fab0907fc16724c",
"https://t.me/proxy?server=213.165.42.119&port=10003&secret=2746c7b761e14fcce479a44c7525b89e",
"https://t.me/proxy?server=213.165.42.119&port=10004&secret=e16b256b44bb768c129c312282c26044",
"https://t.me/proxy?server=213.165.42.119&port=10005&secret=2b08a5e3ef56fda24d58039d22a61dc1",
"https://t.me/proxy?server=213.165.42.119&port=10006&secret=465d5dd479cca63fde250779c98594b7",
"https://t.me/proxy?server=213.165.42.119&port=10007&secret=4d4b3ddd0b900a482c41cf2a125bd222",
"https://t.me/proxy?server=213.165.42.119&port=10008&secret=fbe7acf6209794f121215fb7eb8cbb51",
"https://t.me/proxy?server=213.165.42.119&port=10009&secret=a34fc92f831e33822da49736bf1b481f",
"https://t.me/proxy?server=213.165.42.119&port=10010&secret=9c069b06630f939c36990d823d02366e",

# SERVER 2
"https://t.me/proxy?server=64.188.124.119&port=10001&secret=d0fc37c9b37ad8f0b5e9c0a6ab89ddfe",
"https://t.me/proxy?server=64.188.124.119&port=10002&secret=64238af94b89197bb143be898f3bfaa4",
"https://t.me/proxy?server=64.188.124.119&port=10003&secret=584833e517aba1d6c40593ca89dd629a",
"https://t.me/proxy?server=64.188.124.119&port=10004&secret=57712a1e83b40badae453c8c4586b16d",
"https://t.me/proxy?server=64.188.124.119&port=10005&secret=abcde9aaebd957462c55ba4d965f83f9",
"https://t.me/proxy?server=64.188.124.119&port=10006&secret=7e1c3911693968f1bacad4da702e2b4a",
"https://t.me/proxy?server=64.188.124.119&port=10007&secret=dcd8a655cccf1fba6ec8b33841f66d89",
"https://t.me/proxy?server=64.188.124.119&port=10008&secret=cab71e78310454b0dce0aa2839caa71a",
"https://t.me/proxy?server=64.188.124.119&port=10009&secret=896ca09c76f69e4c50a3d7d239f398c0",
"https://t.me/proxy?server=64.188.124.119&port=10010&secret=874bc10369801a0c9b62c52fd10f66d8"

]

# записываем ключи в базу
for k in keys_list:
    cursor.execute("INSERT OR IGNORE INTO keys VALUES (?, 0)", (k,))
conn.commit()

payments = {}

# ===== ФУНКЦИИ =====
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
    kb.add(types.InlineKeyboardButton("💳 Купить / Продлить", callback_data="buy"))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))

    await message.answer(
        "🚀 Telegram без блокировок\n\n"
        "— Быстро\n"
        "— Без лагов\n"
        "— 1 устройство = 1 ключ",
        reply_markup=kb
    )

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
                        await bot.send_message(user_id, "❌ Нет свободных ключей")
                        continue

                    expire = datetime.now() + timedelta(days=30)

                    cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, key, expire.isoformat()))

                    await bot.send_message(
                        user_id,
                        f"✅ Доступ выдан\n\n🔐 {key}\n\nДо: {expire}\n\nПоддержка: https://t.me/suport_antibloktg"
                    )

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
