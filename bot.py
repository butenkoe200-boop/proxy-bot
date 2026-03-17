import os
import uuid
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from yookassa import Payment, Configuration

API_TOKEN = os.getenv("API_TOKEN")
SHOP_ID = os.getenv("SHOP_ID")
SECRET_KEY = os.getenv("SECRET_KEY")

Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

users = {}
payments = {}

# 🔥 ВСТАВЬ СЮДА СВОЮ ССЫЛКУ
PROXY_LINK = "https://t.me/proxy?server=64.188.124.119&port=443&secret=6fe2b38caff28f65afa6e25746446372"

def create_payment(user_id):
    payment = Payment.create({
        "amount": {"value": "149.00", "currency": "RUB"},
        "confirmation": {
    "type": "redirect",
    "return_url": "https://t.me/antibloktg_bot"
},
        "capture": True,
        "description": str(user_id)
    }, uuid.uuid4())

    payments[payment.id] = user_id
    return payment.confirmation.confirmation_url

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Купить доступ (149₽)", callback_data="buy"))

    await message.answer(
        "🚀 Telegram работает без VPN\n\n"
        "— Без лагов\n"
        "— Подключение за 30 секунд\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data == "buy")
async def buy(callback: types.CallbackQuery):
    url = create_payment(callback.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=url))

    await bot.send_message(callback.from_user.id, "Оплати доступ:", reply_markup=kb)

async def check_payments():
    while True:
        for payment_id in list(payments.keys()):
            payment = Payment.find_one(payment_id)

            if payment.status == "succeeded":
                user_id = payments[payment_id]

                users[user_id] = {
                    "expire": datetime.now() + timedelta(days=30)
                }

                await bot.send_message(
                    user_id,
                    "✅ Оплата прошла!\n\nНажми кнопку:",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🚀 Подключить Telegram", url=PROXY_LINK)
                    )
                )

                del payments[payment_id]

        await asyncio.sleep(10)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    executor.start_polling(dp, skip_updates=True)
