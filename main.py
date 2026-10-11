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

# --- Главное меню ---
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои аккаунты")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👑 Админ-панель")]
        ],
        resize_keyboard=True
    )

# --- Инлайн меню настроек ---
def settings_keyboard():
    delivery_text = "Вкл" if settings_state["delivery"] else "Выкл"
    bump_text = "Вкл" if settings_state["bump"] else "Выкл"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔄 Авто-выдача: {delivery_text}", callback_data="toggle_delivery")],
            [InlineKeyboardButton(text=f"🚀 Авто-поднятие: {bump_text}", callback_data="toggle_bump")],
            [InlineKeyboardButton(text="🔌 Привязать аккаунт Playerok", callback_data="bind_account")]
        ]
    )

@dp.message(CommandStart())
async def start_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    add_user(message.from_user.id, message.from_user.username or "none", message.from_user.first_name)
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\nДобро пожаловать в панель управления.",
        reply_markup=main_keyboard()
    )

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"🆔 Ваш ID: <code>{message.from_user.id}</code>\n"
        f"💎 Подписка: Отсутствует\n"
        f"💰 Баланс: 0 RUB\n"
        f"📦 Всего пополнений: 0 RUB\n"
        f"🔌 Подключено аккаунтов: {1 if settings_state['account_connected'] else 0} / 1"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "⚙️ Настройки")
async def settings_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ <b>Настройки автоматизации:</b>\n\nВыберите нужный параметр:", reply_markup=settings_keyboard(), parse_mode="HTML")

# --- НОВОЕ: Мои аккаунты ---
@dp.message(F.text == "📦 Мои аккаунты")
async def accounts_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    if settings_state["account_connected"]:
        text = "📦 <b>Ваши аккаунты:</b>\n\n1. 🟢 <b>Playerok</b> (Активен)"
    else:
        text = "📦 <b>Ваши аккаунты:</b>\n\nНет подключенных аккаунтов."
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="bind_account")],
        [InlineKeyboardButton(text="📱 Управление в WebApp", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- НОВОЕ: Статистика ---
@dp.message(F.text == "📊 Статистика")
async def stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    text = (
        "📊 <b>Ваша статистика:</b>\n\n"
        "🔄 Выдано товаров: 0\n"
        "🚀 Выполнено поднятий: 0\n"
        "💰 Заработано: 0 RUB"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Расширенная статистика", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- НОВОЕ: Админ-панель ---
@dp.message(F.text == "👑 Админ-панель")
async def admin_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    text = "👑 <b>Дополнительные функции:</b>\n\nНастройки рефералов и прокси-серверов."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Реферальная программа", callback_data="referrals")],
        [InlineKeyboardButton(text="🌐 Настройка Прокси", callback_data="proxy_setup")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- Обработка нажатий кнопок ---
@dp.callback_query(F.data.in_(["toggle_delivery", "toggle_bump", "bind_account", "referrals", "proxy_setup"]))
async def callbacks_handler(callback: CallbackQuery):
    if callback.data == "toggle_delivery":
        if not settings_state["account_connected"]:
            await callback.answer("Сначала подключите аккаунт Playerok!", show_alert=True)
            return
        settings_state["delivery"] = not settings_state["delivery"]
        await callback.message.edit_reply_markup(reply_markup=settings_keyboard())
        webapp_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 Настроить товары", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))]])
        await callback.message.answer("Зайдите в мини-приложение, чтобы добавить текст и файлы для авто-выдачи.", reply_markup=webapp_btn)
        await callback.answer()
        
    elif callback.data == "toggle_bump":
        if not settings_state["account_connected"]:
            await callback.answer("Сначала подключите аккаунт Playerok!", show_alert=True)
            return
        settings_state["bump"] = not settings_state["bump"]
        await callback.message.edit_reply_markup(reply_markup=settings_keyboard())
        webapp_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 Выбрать товары", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))]])
        await callback.message.answer("Зайдите в мини-приложение и отметьте товары для авто-поднятия.", reply_markup=webapp_btn)
        await callback.answer()
        
    elif callback.data == "bind_account":
        settings_state["account_connected"] = True
        if "Ваши аккаунты" not in callback.message.text:
            await callback.message.edit_reply_markup(reply_markup=settings_keyboard())
        await callback.answer("Аккаунт успешно 'привязан'!", show_alert=True)
        
    elif callback.data == "referrals":
        await callback.message.answer(f"🔗 Ваша реферальная ссылка:\n<code>https://t.me/{(await bot.me()).username}?start={ADMIN_ID}</code>\n\nПриглашайте друзей и получайте бонусы!", parse_mode="HTML")
        await callback.answer()
        
    elif callback.data == "proxy_setup":
        webapp_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 Добавить прокси", web_app=WebAppInfo(url="https://core.telegram.org/bots/webapps"))]])
        await callback.message.answer("Зайдите в мини-приложение для добавления приватных прокси-серверов.", reply_markup=webapp_btn)
        await callback.answer()

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
