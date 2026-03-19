# 🚀 FIXED MAX VERSION Telegram Proxy SaaS Bot
# Исправлены кнопки, callback'и, admin, UX

import sqlite3
import uuid
from datetime import datetime, timedelta
import os

from aiogram import Bot, Dispatcher, types
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ================= CONFIG =================
API_TOKEN = os.getenv("API_TOKEN")
PAYMENTS_TOKEN = os.getenv("PAYMENTS_TOKEN")
ADMIN_ID = 123456789
PRICE = 14900

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ================= DATABASE =================
conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    subscription_until TEXT,
    referrer_id INTEGER,
    balance INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS proxies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proxy TEXT,
    country TEXT,
    is_used INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS payments (
    id TEXT,
    user_id INTEGER,
    amount INTEGER,
    date TEXT
)""")

conn.commit()

# ================= UI =================
def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🚀 Подключить", callback_data="buy"))
    kb.add(InlineKeyboardButton("📊 Статус", callback_data="status"))
    kb.add(InlineKeyboardButton("👥 Рефералы", callback_data="ref"))
    return kb

# ================= PROXY =================
def get_proxies(limit=2):
    cursor.execute("SELECT id, proxy FROM proxies WHERE is_used=0 LIMIT ?", (limit,))
    return cursor.fetchall()


def use_proxies(ids):
    cursor.executemany("UPDATE proxies SET is_used=1 WHERE id=?", [(i,) for i in ids])
    conn.commit()

# ================= START =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    args = message.get_args()
    user_id = message.from_user.id

    ref_id = int(args) if args.isdigit() else None

    cursor.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, ref_id))
    conn.commit()

    await message.answer("🔥 АнтиБлок Proxy Bot", reply_markup=main_menu())

# ================= BUY =================
@dp.callback_query_handler(lambda c: c.data == "buy")
async def buy(call: types.CallbackQuery):
    await call.answer()

    prices = [LabeledPrice(label="2 прокси", amount=PRICE)]

    await bot.send_invoice(
        chat_id=call.message.chat.id,
        title="Proxy",
        description="2 прокси на 30 дней",
        payload=str(uuid.uuid4()),
        provider_token=PAYMENTS_TOKEN,
        currency="RUB",
        prices=prices
    )

# ================= PAYMENT =================
@dp.pre_checkout_query_handler(lambda q: True)
async def checkout(q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)


@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def success(message: types.Message):
    user_id = message.from_user.id

    proxies = get_proxies()

    if len(proxies) < 2:
        await message.answer("❌ Нет прокси")
        return

    proxy_text = "\n".join([p[1] for p in proxies])
    ids = [p[0] for p in proxies]
    use_proxies(ids)

    expire = datetime.now() + timedelta(days=30)

    cursor.execute("INSERT OR REPLACE INTO users (user_id, subscription_until) VALUES (?, ?)",
                   (user_id, expire.isoformat()))

    cursor.execute("INSERT INTO payments VALUES (?, ?, ?, ?)",
                   (str(uuid.uuid4()), user_id, PRICE, datetime.now().isoformat()))

    cursor.execute("SELECT referrer_id FROM users WHERE user_id=?", (user_id,))
    ref = cursor.fetchone()

    if ref and ref[0]:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (PRICE//10, ref[0]))

    conn.commit()

    await message.answer(f"✅ Оплата прошла\n\n🔐 {proxy_text}\n⏳ до {expire.strftime('%d-%m-%Y')}")

# ================= STATUS =================
@dp.callback_query_handler(lambda c: c.data == "status")
async def status(call: types.CallbackQuery):
    await call.answer()

    cursor.execute("SELECT subscription_until FROM users WHERE user_id=?", (call.from_user.id,))
    row = cursor.fetchone()

    if not row:
        await call.message.answer("❌ У тебя нет подписки")
        return

    expire = datetime.fromisoformat(row[0])
    await call.message.answer(f"⏳ Подписка до {expire.strftime('%d-%m-%Y')}")

# ================= REF =================
@dp.callback_query_handler(lambda c: c.data == "ref")
async def ref(call: types.CallbackQuery):
    await call.answer()

    link = f"https://t.me/{(await bot.get_me()).username}?start={call.from_user.id}"

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    bal = cursor.fetchone()
    bal = bal[0] if bal else 0

    await call.message.answer(f"👥 Ссылка:\n{link}\n\n💰 Баланс: {bal/100}₽")

# ================= ADMIN =================
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа")
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM payments")
    pays = cursor.fetchone()[0]

    await message.answer(f"👨‍💻 USERS: {users}\n💳 PAYMENTS: {pays}")

# ================= RUN =================
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
