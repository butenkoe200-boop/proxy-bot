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
                    "expire": datetime.now() + timedelta(days=30),
                    "notified_2days": False,
                    "notified_expired": False
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


async def remind_users():
    while True:
        for user_id, data in users.items():
            expire = data["expire"]
            now = datetime.now()

            # 🔔 За 2 дня (1 раз)
            if 0 < (expire - now).days <= 2 and not data.get("notified_2days"):
                await bot.send_message(
                    user_id,
                    "⚠️ Осталось меньше 2 дней доступа\n\nПродли сейчас 👇",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("💳 Продлить (149₽)", callback_data="buy")
                    )
                )
                data["notified_2days"] = True

            # ⛔ Доступ закончился (1 раз)
            elif expire < now and not data.get("notified_expired"):
                await bot.send_message(
                    user_id,
                    "❌ Доступ закончился\n\nПродли доступ 👇",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("💳 Продлить", callback_data="buy")
                    )
                )
                data["notified_expired"] = True

        await asyncio.sleep(3600)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    loop.create_task(remind_users())
    executor.start_polling(dp, skip_updates=True)
