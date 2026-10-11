import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import web
from database import init_db, add_user

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ADMIN_ID = 8158413794  

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои аккаунты")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👑 Админ-панель")]
        ],
        resize_keyboard=True
    )

# --- Инлайн-клавиатура для настроек ---
def settings_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Авто-выдача: Выкл", callback_data="toggle_delivery")],
            [InlineKeyboardButton(text="🚀 Авто-поднятие: Выкл", callback_data="toggle_bump")],
            [InlineKeyboardButton(text="🔌 Привязать аккаунт Playerok", callback_data="bind_account")]
        ]
    )

@dp.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    add_user(message.from_user.id, message.from_user.username or "none", message.from_user.first_name)
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Добро пожаловать в панель управления.",
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"🆔 Ваш ID: <code>{message.from_user.id}</code>\n"
        f"💎 Подписка: Отсутствует\n"
        f"💰 Баланс: 0 RUB\n"
        f"📦 Всего пополнений: 0 RUB\n"
        f"🔌 Подключено аккаунтов: 0 / 1"
    )
    await message.answer(text, parse_mode="HTML")

# --- Обработчик кнопки Настройки ---
@dp.message(F.text == "⚙️ Настройки")
async def settings_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "⚙️ <b>Настройки автоматизации:</b>\n\n"
        "Выберите нужный раздел для настройки бота.",
        reply_markup=settings_keyboard(),
        parse_mode="HTML"
    )

# --- Обработчик нажатий на инлайн-кнопки (пока заглушка) ---
@dp.callback_query(F.data.in_(["toggle_delivery", "toggle_bump", "bind_account"]))
async def callbacks_handler(callback: CallbackQuery):
    await callback.answer("🛠 Функция в разработке. Скоро добавим!", show_alert=True)

# --- Фейковый веб-сервер для бесплатного Render ---
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
