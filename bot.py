import sqlite3
import uuid
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from yookassa import Payment, Configuration
import os

# ===== НАСТРОЙКИ =====
API_TOKEN = os.getenv("API_TOKEN")
SHOP_ID = os.getenv("SHOP_ID")
SECRET_KEY = os.getenv("SECRET_KEY")
ADMIN_ID = 6542324565

PRICE = 149
REFERRAL_PERCENT = 20  # 20% от каждой оплаты рефала

if not API_TOKEN:
    raise ValueError("❌ API_TOKEN не найден")

Configuration.account_id = SHOP_ID
Configuration.secret_key = SECRET_KEY

storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

# ===== FSM STATES =====
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_grant_user_id = State()
    waiting_for_broadcast = State()

# ===== БАЗА =====
conn = sqlite3.connect("db.sqlite", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    expire TEXT DEFAULT '0',
    notified_2days INTEGER DEFAULT 0,
    notified_expired INTEGER DEFAULT 0,
    referred_by INTEGER DEFAULT NULL,
    join_date TEXT DEFAULT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    date TEXT,
    payment_id TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS referral_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER,
    referred_id INTEGER,
    amount INTEGER,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS referral_balance (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    total_earned INTEGER DEFAULT 0
)
""")

conn.commit()

# ===== ПРОКСИ =====
PROXIES = [
    "https://t.me/proxy?server=213.165.42.119&port=443&secret=5c95fa91e3ba74956468698b3c3ae6ae",
    "https://t.me/proxy?server=64.188.124.119&port=443&secret=0feeb7f54cbb7b09c6426c1f1cb984b8"
]

payments_pending = {}

# ===== КНОПКИ =====
def main_kb(user_id=None):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"💳 Купить / Продлить ({PRICE}₽/мес)", callback_data="buy"))
    kb.add(types.InlineKeyboardButton("👤 Мой аккаунт", callback_data="my_account"))
    kb.add(types.InlineKeyboardButton("👥 Реферальная программа", callback_data="referral"))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))
    return kb

def admin_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 Все юзеры", callback_data="all_users"),
        types.InlineKeyboardButton("✅ Активные", callback_data="active")
    )
    kb.add(
        types.InlineKeyboardButton("❌ Неактивные", callback_data="expired"),
        types.InlineKeyboardButton("💰 Статистика", callback_data="stats")
    )
    kb.add(
        types.InlineKeyboardButton("🔍 Найти юзера", callback_data="find"),
        types.InlineKeyboardButton("🎁 Выдать доступ", callback_data="grant")
    )
    kb.add(types.InlineKeyboardButton("📢 Рассылка", callback_data="broadcast"))
    return kb

# ===== ХЕЛПЕРЫ =====
def get_or_create_ref_balance(user_id):
    cursor.execute("INSERT OR IGNORE INTO referral_balance (user_id, balance, total_earned) VALUES (?, 0, 0)", (user_id,))
    conn.commit()

def get_ref_balance(user_id):
    get_or_create_ref_balance(user_id)
    cursor.execute("SELECT balance, total_earned FROM referral_balance WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def add_ref_reward(referrer_id, referred_id, payment_amount):
    reward = int(payment_amount * REFERRAL_PERCENT / 100)
    get_or_create_ref_balance(referrer_id)
    cursor.execute("""
    UPDATE referral_balance SET balance=balance+?, total_earned=total_earned+? WHERE user_id=?
    """, (reward, reward, referrer_id))
    cursor.execute("""
    INSERT INTO referral_rewards (referrer_id, referred_id, amount, date) VALUES (?, ?, ?, ?)
    """, (referrer_id, referred_id, reward, datetime.now().isoformat()))
    conn.commit()
    return reward

def count_referrals(user_id):
    cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,))
    return cursor.fetchone()[0]

def is_active(expire_str):
    if not expire_str or expire_str == '0':
        return False
    try:
        return datetime.fromisoformat(expire_str) > datetime.now()
    except:
        return False

# ===== СТАРТ =====
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    args = message.get_args()
    referred_by = None

    if args and args.isdigit():
        ref_id = int(args)
        if ref_id != user_id:
            cursor.execute("SELECT user_id FROM users WHERE user_id=?", (ref_id,))
            if cursor.fetchone():
                referred_by = ref_id

    cursor.execute("SELECT user_id, referred_by FROM users WHERE user_id=?", (user_id,))
    existing = cursor.fetchone()

    if existing:
        # Обновляем только username/first_name
        cursor.execute("""
        UPDATE users SET username=?, first_name=? WHERE user_id=?
        """, (message.from_user.username, message.from_user.first_name, user_id))
    else:
        cursor.execute("""
        INSERT INTO users (user_id, username, first_name, expire, referred_by, join_date)
        VALUES (?, ?, ?, '0', ?, ?)
        """, (
            user_id,
            message.from_user.username,
            message.from_user.first_name,
            referred_by,
            datetime.now().isoformat()
        ))

    conn.commit()

    # Уведомить реферера о новом приглашённом
    if referred_by and not existing:
        try:
            await bot.send_message(
                referred_by,
                f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                f"Вы получите {REFERRAL_PERCENT}% от его оплаты на ваш баланс 💰"
            )
        except:
            pass

    await message.answer(
        "🚀 Telegram без блокировок\n\n"
        "— Подключение за 30 секунд\n"
        "— Работает на мобильном\n"
        "— Без лагов\n\n"
        f"💳 Цена: {PRICE}₽ / месяц\n\n"
        "Нажми ниже 👇",
        reply_markup=main_kb(user_id)
    )

# ===== МОЙ АККАУНТ =====
@dp.callback_query_handler(lambda c: c.data == "my_account")
async def my_account(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    cursor.execute("SELECT expire, referred_by FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("Ошибка. Напишите /start")
        return

    expire, referred_by = row
    active = is_active(expire)

    ref_count = count_referrals(user_id)
    balance_row = get_ref_balance(user_id)
    balance = balance_row[0] if balance_row else 0
    total_earned = balance_row[1] if balance_row else 0

    status = f"✅ Активен до {datetime.fromisoformat(expire).strftime('%d.%m.%Y')}" if active else "❌ Нет доступа"

    text = (
        f"👤 Ваш аккаунт\n\n"
        f"ID: {user_id}\n"
        f"Статус: {status}\n\n"
        f"👥 Рефералов приглашено: {ref_count}\n"
        f"💰 Реферальный баланс: {balance}₽\n"
        f"📈 Всего заработано: {total_earned}₽"
    )

    kb = types.InlineKeyboardMarkup()

    if active:
        # Показываем прокси прямо в аккаунте
        text += "\n\n🔌 Ваши серверы для подключения:"
        kb.add(types.InlineKeyboardButton("🚀 Основной сервер", url=PROXIES[0]))
        kb.add(types.InlineKeyboardButton("🛟 Резервный сервер", url=PROXIES[1]))
        kb.add(types.InlineKeyboardButton(f"💳 Продлить ({PRICE}₽)", callback_data="buy"))
    else:
        kb.add(types.InlineKeyboardButton(f"💳 Купить доступ ({PRICE}₽)", callback_data="buy"))

    kb.add(types.InlineKeyboardButton("👥 Реферальная программа", callback_data="referral"))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_main"))

    # Отправляем новым сообщением — не трогаем предыдущие
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "🚀 Telegram без блокировок\n\n"
        "— Подключение за 30 секунд\n"
        "— Работает на мобильном\n"
        "— Без лагов\n\n"
        f"💳 Цена: {PRICE}₽ / месяц\n\n"
        "Нажми ниже 👇",
        reply_markup=main_kb(callback.from_user.id)
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "back_account")
async def back_account(callback: types.CallbackQuery):
    await callback.message.delete()
    await my_account(callback)

# ===== РЕФЕРАЛЬНАЯ СИСТЕМА =====
@dp.callback_query_handler(lambda c: c.data == "referral")
async def referral_info(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={user_id}"

    ref_count = count_referrals(user_id)
    balance_row = get_ref_balance(user_id)
    balance = balance_row[0] if balance_row else 0
    total_earned = balance_row[1] if balance_row else 0

    # Список последних рефералов
    cursor.execute("""
    SELECT username, first_name, expire FROM users 
    WHERE referred_by=? ORDER BY join_date DESC LIMIT 5
    """, (user_id,))
    refs = cursor.fetchall()

    refs_text = ""
    if refs:
        refs_text = "\n\n👥 Последние рефералы:\n"
        for r in refs:
            name = f"@{r[0]}" if r[0] else r[1] or "Аноним"
            status = "✅" if is_active(r[2]) else "❌"
            refs_text += f"{status} {name}\n"

    text = (
        f"👥 Реферальная программа\n\n"
        f"Получайте {REFERRAL_PERCENT}% от каждого платежа приглашённого!\n\n"
        f"💰 Ваш баланс: {balance}₽\n"
        f"📈 Всего заработано: {total_earned}₽\n"
        f"👤 Приглашено: {ref_count} чел.\n"
        f"{refs_text}"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📤 Поделиться ссылкой", switch_inline_query=f"Присоединяйся! {ref_link}"))
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_account"))

    # Реф-ссылку оборачиваем в code-тег для удобного копирования
    text_html = text + f"\n\n🔗 Ваша реф. ссылка:\n<code>{ref_link}</code>"

    # Отправляем новым сообщением — не трогаем предыдущие
    await callback.message.answer(text_html, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

# ===== ОПЛАТА =====
def create_payment(user_id):
    payment = Payment.create({
        "amount": {"value": f"{PRICE}.00", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/antibloktg_bot"
        },
        "capture": True,
        "description": f"Доступ к прокси | user_id: {user_id}"
    }, str(uuid.uuid4()))

    payments_pending[payment.id] = user_id
    return payment.confirmation.confirmation_url

@dp.callback_query_handler(lambda c: c.data == "buy")
async def buy(callback: types.CallbackQuery):
    url = create_payment(callback.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Оплатить", url=url))
    kb.add(types.InlineKeyboardButton("✅ Я оплатил", callback_data="check_payment"))

    await bot.send_message(
        callback.from_user.id,
        f"💳 Оплата доступа\n\n"
        f"Сумма: {PRICE}₽ / 30 дней\n\n"
        f"Нажми кнопку ниже для оплаты.\n"
        f"После оплаты нажми «Я оплатил»",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data == "check_payment")
async def check_payment_manual(callback: types.CallbackQuery):
    await callback.answer("⏳ Проверяем оплату... Подождите до 30 сек.", show_alert=True)

# ===== ВЫДАЧА =====
def get_proxies_message(expire):
    text = (
        f"✅ Доступ активирован!\n\n"
        f"📅 Действует до: {expire.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"👇 Выбери сервер для подключения:"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🚀 Основной сервер", url=PROXIES[0]))
    kb.add(types.InlineKeyboardButton("🛟 Резервный сервер", url=PROXIES[1]))
    kb.add(types.InlineKeyboardButton("👥 Пригласить друга +{REFERRAL_PERCENT}%", callback_data="referral"))
    kb.add(types.InlineKeyboardButton("🛠 Поддержка", url="https://t.me/suport_antibloktg"))

    return text, kb

# ===== ПРОВЕРКА ОПЛАТ =====
async def check_payments():
    while True:
        for pid in list(payments_pending.keys()):
            try:
                payment = Payment.find_one(pid)

                if payment.status == "succeeded":
                    user_id = payments_pending[pid]

                    cursor.execute("SELECT expire, referred_by FROM users WHERE user_id=?", (user_id,))
                    row = cursor.fetchone()

                    if row and row[0] and row[0] != "0":
                        try:
                            expire = datetime.fromisoformat(row[0])
                            new_expire = max(expire, datetime.now()) + timedelta(days=30)
                        except:
                            new_expire = datetime.now() + timedelta(days=30)
                    else:
                        new_expire = datetime.now() + timedelta(days=30)

                    referred_by = row[1] if row else None

                    cursor.execute("""
                    UPDATE users 
                    SET expire=?, notified_2days=0, notified_expired=0 
                    WHERE user_id=?
                    """, (new_expire.isoformat(), user_id))

                    cursor.execute(
                        "INSERT INTO payments (user_id, amount, date, payment_id) VALUES (?, ?, ?, ?)",
                        (user_id, PRICE, datetime.now().isoformat(), pid)
                    )

                    conn.commit()

                    # Реферальное вознаграждение
                    if referred_by:
                        reward = add_ref_reward(referred_by, user_id, PRICE)
                        try:
                            await bot.send_message(
                                referred_by,
                                f"💰 Вы получили реферальное вознаграждение!\n\n"
                                f"Ваш реферал оплатил доступ.\n"
                                f"Начислено: +{reward}₽ ({REFERRAL_PERCENT}%)\n\n"
                                f"Проверить баланс: /start → Реферальная программа"
                            )
                        except:
                            pass

                    text, kb = get_proxies_message(new_expire)
                    await bot.send_message(user_id, text, reply_markup=kb)

                    del payments_pending[pid]

                elif payment.status in ("canceled", "expired"):
                    del payments_pending[pid]

            except Exception as e:
                print("Ошибка оплаты:", e)

        await asyncio.sleep(10)

# ===== УВЕДОМЛЕНИЯ =====
async def reminders():
    while True:
        try:
            cursor.execute("""
            SELECT user_id, expire, notified_2days, notified_expired 
            FROM users WHERE expire != '0' AND expire IS NOT NULL
            """)
            users = cursor.fetchall()
            now = datetime.now()

            for u in users:
                user_id, exp, n2, ne = u
                try:
                    expire = datetime.fromisoformat(exp)
                except:
                    continue

                # За 2 дня
                if 0 < (expire - now).days <= 2 and n2 == 0:
                    try:
                        kb = types.InlineKeyboardMarkup()
                        kb.add(types.InlineKeyboardButton(f"💳 Продлить ({PRICE}₽)", callback_data="buy"))
                        await bot.send_message(
                            user_id,
                            f"⚠️ Осталось меньше 2 дней доступа!\n\n"
                            f"Продли сейчас, чтобы не потерять доступ 👇",
                            reply_markup=kb
                        )
                        cursor.execute("UPDATE users SET notified_2days=1 WHERE user_id=?", (user_id,))
                        conn.commit()
                    except:
                        pass

                # Истёк
                if expire < now and ne == 0:
                    try:
                        kb = types.InlineKeyboardMarkup()
                        kb.add(types.InlineKeyboardButton(f"💳 Продлить ({PRICE}₽)", callback_data="buy"))
                        await bot.send_message(
                            user_id,
                            f"❌ Ваш доступ закончился!\n\n"
                            f"Продлите подписку, чтобы продолжить 👇",
                            reply_markup=kb
                        )
                        cursor.execute("UPDATE users SET notified_expired=1 WHERE user_id=?", (user_id,))
                        conn.commit()
                    except:
                        pass
        except Exception as e:
            print("Ошибка reminders:", e)

        await asyncio.sleep(3600)

# ===== ADMIN: ГЛАВНОЕ =====
@dp.message_handler(commands=['admin'])
async def admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("⚙️ Панель администратора", reply_markup=admin_kb())

# ===== ADMIN: ВСЕ ПОЛЬЗОВАТЕЛИ =====
@dp.callback_query_handler(lambda c: c.data == "all_users")
async def all_users(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT user_id, username, first_name, expire, join_date FROM users ORDER BY join_date DESC LIMIT 30")
    data = cursor.fetchall()

    now = datetime.now()
    text = f"👥 Все пользователи (последние {min(len(data),30)}):\n\n"
    for u in data:
        uid, username, first_name, expire, join_date = u
        name = f"@{username}" if username else (first_name or "Аноним")
        try:
            status = "✅" if expire and expire != '0' and datetime.fromisoformat(expire) > now else "❌"
        except:
            status = "❌"
        jdate = join_date[:10] if join_date else "—"
        text += f"{status} {uid} | {name} | {jdate}\n"

    await bot.send_message(callback.from_user.id, text)

# ===== ADMIN: АКТИВНЫЕ =====
@dp.callback_query_handler(lambda c: c.data == "active")
async def active(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    now = datetime.now().isoformat()
    cursor.execute("""
    SELECT user_id, username, first_name, expire FROM users 
    WHERE expire > ? AND expire != '0' ORDER BY expire ASC LIMIT 50
    """, (now,))
    data = cursor.fetchall()

    text = f"✅ Активные подписки: {len(data)}\n\n"
    for u in data:
        uid, username, first_name, expire = u
        name = f"@{username}" if username else (first_name or "Аноним")
        try:
            exp_str = datetime.fromisoformat(expire).strftime("%d.%m.%Y")
        except:
            exp_str = expire
        text += f"{uid} | {name} | до {exp_str}\n"

    await bot.send_message(callback.from_user.id, text or "Нет активных")

# ===== ADMIN: НЕАКТИВНЫЕ =====
@dp.callback_query_handler(lambda c: c.data == "expired")
async def expired_users(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    now = datetime.now().isoformat()
    cursor.execute("""
    SELECT user_id, username, first_name FROM users 
    WHERE expire <= ? OR expire = '0' ORDER BY user_id DESC LIMIT 50
    """, (now,))
    data = cursor.fetchall()

    text = f"❌ Неактивные: {len(data)}\n\n"
    for u in data:
        uid, username, first_name = u
        name = f"@{username}" if username else (first_name or "Аноним")
        text += f"{uid} | {name}\n"

    await bot.send_message(callback.from_user.id, text or "Нет неактивных")

# ===== ADMIN: СТАТИСТИКА =====
@dp.callback_query_handler(lambda c: c.data == "stats")
async def stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    now = datetime.now().isoformat()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE expire > ? AND expire != '0'", (now,))
    active_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM payments")
    p = cursor.fetchone()
    pays_total, money_total = p[0], p[1]

    # За сегодня
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM payments WHERE date LIKE ?", (f"{today}%",))
    p_today = cursor.fetchone()
    pays_today, money_today = p_today[0], p_today[1]

    # За 30 дней
    month_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM payments WHERE date > ?", (month_ago,))
    p_month = cursor.fetchone()
    pays_month, money_month = p_month[0], p_month[1]

    cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL")
    ref_users = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount),0) FROM referral_rewards")
    ref_rewards = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", (f"{today}%",))
    new_today = cursor.fetchone()[0]

    text = (
        f"📊 Статистика бота\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Активных подписок: {active_count}\n"
        f"🆕 Новых сегодня: {new_today}\n\n"
        f"💰 Оплаты сегодня: {pays_today} шт / {money_today}₽\n"
        f"📅 За 30 дней: {pays_month} шт / {money_month}₽\n"
        f"📈 Всего оплат: {pays_total} шт / {money_total}₽\n\n"
        f"👥 Пришли по рефералке: {ref_users}\n"
        f"💸 Выплачено рефералам: {ref_rewards}₽"
    )

    await bot.send_message(callback.from_user.id, text)

# ===== ADMIN: НАЙТИ ЮЗЕРА =====
@dp.callback_query_handler(lambda c: c.data == "find")
async def find_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await AdminStates.waiting_for_user_id.set()
    await bot.send_message(callback.from_user.id, "🔍 Введи ID или @username пользователя:")

@dp.message_handler(state=AdminStates.waiting_for_user_id)
async def find_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    await state.finish()
    query = message.text.strip().lstrip("@")

    if query.isdigit():
        cursor.execute("SELECT user_id, username, first_name, expire, join_date, referred_by FROM users WHERE user_id=?", (int(query),))
    else:
        cursor.execute("SELECT user_id, username, first_name, expire, join_date, referred_by FROM users WHERE username=?", (query,))

    u = cursor.fetchone()

    if not u:
        await message.answer("❌ Пользователь не найден")
        return

    uid, username, first_name, expire, join_date, referred_by = u
    name = f"@{username}" if username else (first_name or "Аноним")

    try:
        active = expire and expire != '0' and datetime.fromisoformat(expire) > datetime.now()
        exp_str = datetime.fromisoformat(expire).strftime("%d.%m.%Y") if expire and expire != '0' else "—"
    except:
        active, exp_str = False, "—"

    ref_count = count_referrals(uid)
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM payments WHERE user_id=?", (uid,))
    pay_info = cursor.fetchone()

    status = "✅ Активен" if active else "❌ Не активен"
    jdate = join_date[:10] if join_date else "—"

    text = (
        f"👤 Пользователь: {name}\n"
        f"ID: {uid}\n"
        f"Статус: {status}\n"
        f"Подписка до: {exp_str}\n"
        f"Дата регистрации: {jdate}\n"
        f"Кол-во оплат: {pay_info[0]} ({pay_info[1]}₽)\n"
        f"Рефералов: {ref_count}\n"
        f"Пришёл от: {referred_by or '—'}"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(f"🎁 Выдать 30 дней", callback_data=f"grant_days_{uid}"))

    await message.answer(text, reply_markup=kb)

# ===== ADMIN: ВЫДАТЬ ДОСТУП =====
@dp.callback_query_handler(lambda c: c.data == "grant")
async def grant_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await AdminStates.waiting_for_grant_user_id.set()
    await bot.send_message(callback.from_user.id, "🎁 Введи ID пользователя для выдачи 30 дней доступа:")

@dp.callback_query_handler(lambda c: c.data.startswith("grant_days_"))
async def grant_days_from_find(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    uid = int(callback.data.split("_")[-1])
    await _grant_access(uid, callback.from_user.id)

@dp.message_handler(state=AdminStates.waiting_for_grant_user_id)
async def grant_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.finish()

    if not message.text.isdigit():
        await message.answer("❌ Введи числовой ID")
        return

    uid = int(message.text)
    await _grant_access(uid, message.from_user.id)

async def _grant_access(uid, admin_id):
    cursor.execute("SELECT expire FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        await bot.send_message(admin_id, "❌ Пользователь не найден")
        return

    expire = row[0]
    try:
        if expire and expire != '0':
            base = max(datetime.fromisoformat(expire), datetime.now())
        else:
            base = datetime.now()
    except:
        base = datetime.now()

    new_expire = base + timedelta(days=30)
    cursor.execute("UPDATE users SET expire=?, notified_2days=0, notified_expired=0 WHERE user_id=?",
                   (new_expire.isoformat(), uid))
    conn.commit()

    try:
        text, kb = get_proxies_message(new_expire)
        await bot.send_message(uid, f"🎁 Администратор выдал вам 30 дней доступа!\n\n" + text, reply_markup=kb)
    except:
        pass

    await bot.send_message(admin_id, f"✅ Доступ выдан пользователю {uid} до {new_expire.strftime('%d.%m.%Y')}")

# ===== ADMIN: РАССЫЛКА =====
@dp.callback_query_handler(lambda c: c.data == "broadcast")
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await AdminStates.waiting_for_broadcast.set()
    await bot.send_message(callback.from_user.id, "📢 Введи текст рассылки (поддерживается HTML):")

@dp.message_handler(state=AdminStates.waiting_for_broadcast)
async def do_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.finish()

    cursor.execute("SELECT user_id FROM users")
    all_users_ids = cursor.fetchall()

    sent, failed = 0, 0
    for (uid,) in all_users_ids:
        try:
            await bot.send_message(uid, message.text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)  # антифлуд
        except:
            failed += 1

    await message.answer(f"📢 Рассылка завершена!\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")

# ===== ЗАПУСК =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_payments())
    loop.create_task(reminders())

    print("🚀 Бот запущен")
    executor.start_polling(dp, skip_updates=True)
