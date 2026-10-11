import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, WebAppInfo
from aiohttp import web
from database import init_db, add_user

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ADMIN_ID = 8158413794  

settings_state = {
    "delivery": False,
    "bump": False,
    "account_connected": False 
}

# --- Главная Reply клавиатура (как на видео внизу экрана) ---
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📦 Мои аккаунты"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🌐 Мои прокси")],
            [KeyboardButton(text="💬 Чаты"), KeyboardButton(text="🛒 Заказы")],
            [KeyboardButton(text="🏷 Товары"), KeyboardButton(text="💳 Транзакции")]
        ],
        resize_keyboard=True
    )

# --- Инлайн меню для команды /start (как на самом первом кадре) ---
def start_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Наш чат", url="https://t.me/your_chat"), InlineKeyboardButton(text="📢 Канал", url="https://t.me/your_channel")],
            [InlineKeyboardButton(text="💚 700+ Отзывов LZT", url="https://lolz.live/")],
            [InlineKeyboardButton(text="🎁 Бесплатная подписка", callback_data="free_sub")],
            [InlineKeyboardButton(text="💡 Функционал", callback_data="func"), InlineKeyboardButton(text="🎮 Инлайн-мод", callback_data="inline_mod")],
            [InlineKeyboardButton(text="⚡️ Боты, софт для FunPay.com", url="https://funpay.com")],
            [InlineKeyboardButton(text="⭐ Авто-выдача Telegram Stars", callback_data="auto_stars")],
            [InlineKeyboardButton(text="📊 Авто-SMM", callback_data="auto_smm"), InlineKeyboardButton(text="👾 Авто-Робуксы", callback_data="auto_robux")],
            [InlineKeyboardButton(text="🧩 Плагины и дополнения", callback_data="plugins_menu")]
        ]
    )

# --- Инлайн меню настроек (Плагины, переключатели и т.д.) ---
def settings_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🤖 Авто-выдача", callback_data="settings_delivery")],
            [InlineKeyboardButton(text="🧩 Плагины", callback_data="settings_plugins")],
            [InlineKeyboardButton(text="⚙️ Переключатели", callback_data="settings_switches")],
            [InlineKeyboardButton(text="🔒 Подтверждение заказов", callback_data="settings_confirm")],
            [InlineKeyboardButton(text="📝 Заготовки ответов", callback_data="settings_templates")],
            [InlineKeyboardButton(text="⛔️ Черный список", callback_data="settings_blacklist")],
            [InlineKeyboardButton(text="⬅️ 1/3 ➡️", callback_data="settings_page_1")], # Заглушка для пагинации
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
        ]
    )

# --- Меню профиля ---
def profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Пополнить", callback_data="add_balance"), InlineKeyboardButton(text="💎 Подписка", callback_data="buy_sub")],
            [InlineKeyboardButton(text="👥 Реферальная система", callback_data="ref_system")],
            [InlineKeyboardButton(text="💸 Перевести баланс", callback_data="transfer_balance")],
            [InlineKeyboardButton(text="🧾 Мои инвойсы", callback_data="my_invoices"), InlineKeyboardButton(text="📝 Мои посты", callback_data="my_posts")],
            [InlineKeyboardButton(text="▶️ Активировать промокод", callback_data="activate_promo")]
        ]
    )


@dp.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    add_user(message.from_user.id, message.from_user.username or "none", message.from_user.first_name)
    
    text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "🤖 Это первый многофункциональный бот для авто-продаж и упрощения работы с playerok.com\n\n"
        "💚 Имеем более 700 отзывов и депозит 100.000₽\n\n"
        "🔥 Сейчас действуют скидки, успевайте приобрести, пока не стало поздно!"
    )
    # Отправляем главное меню вниз и инлайн-меню в чат
    await message.answer(text, reply_markup=main_keyboard())
    await message.answer("👇 Выберите нужное действие:", reply_markup=start_inline_keyboard())

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"🆔 Ваш ID: <code>{message.from_user.id}</code>\n"
        f"💎 Подписка: Отсутствует\n\n"
        f"📊 <b>Статистика</b> 🔽\n"
        f"➖ Баланс: 0 RUB\n"
        f"➖ Всего пополнений: 0 RUB\n"
        f"➖ Подключено аккаунтов: {1 if settings_state['account_connected'] else 0} / 1"
    )
    await message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")

@dp.message(F.text == "⚙️ Настройки")
async def settings_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ <b>Настройки аккаунта:</b>\nВыберите нужный раздел:", reply_markup=settings_inline_keyboard(), parse_mode="HTML")

@dp.message(F.text == "📦 Мои аккаунты")
async def accounts_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = "📦 <b>Всего аккаунтов: 1</b>\n\n🟢 <b>Playerok (ТвойНик)</b> | 1649.6 ₽ | ⭐️ 206" if settings_state["account_connected"] else "📦 <b>Всего аккаунтов: 0</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="bind_account")],
        [InlineKeyboardButton(text="📱 Анализирую продажи...", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🌐 Мои прокси")
async def proxies_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = "🔑 <b>Для работы с прокси используй меню ниже</b>\n\nКол-во твоих прокси: 0 шт."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_proxy"), InlineKeyboardButton(text="🌐 Купить", url="https://proxy6.net/?ref=ТВОЙ_АЙДИ")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# Заглушки для остальных кнопок главного меню
@dp.message(F.text.in_(["📊 Статистика", "💬 Чаты", "🛒 Заказы", "🏷 Товары", "💳 Транзакции"]))
async def placeholder_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 Раздел в разработке. Будет открывать WebApp или выводить список.")

# --- Обработка нажатий Инлайн-кнопок ---
@dp.callback_query()
async def all_callbacks(callback: CallbackQuery):
    if callback.data == "bind_account":
        settings_state["account_connected"] = True
        await callback.answer("Аккаунт подключен!", show_alert=True)
    elif callback.data == "ref_system":
        # Кнопка рефералки из профиля
        await callback.message.answer(f"🔗 Твоя реферальная ссылка:\n<code>https://t.me/{(await bot.me()).username}?start={ADMIN_ID}</code>\n\nПриглашай друзей и получай процент от их покупок!", parse_mode="HTML")
        await callback.answer()
    else:
        # Для всех остальных кнопок пока просто уведомление
        await callback.answer("Скоро добавим функционал!", show_alert=False)

# --- Фейковый веб-сервер ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def main():
    init_db()
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
