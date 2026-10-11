import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from database import init_db, add_user

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ADMIN_ID = 8158413794  

settings_state = {
    "account_connected": False,
    "token": None
}
promocodes_db = {} 
SUBSCRIPTION_PRICE = 499 

class BotStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_promo_name = State()
    waiting_for_promo_discount = State()
    waiting_for_promo_activation = State()

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📦 Мои аккаунты"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🌐 Мои прокси"), KeyboardButton(text="👑 Админ-панель")],
            [KeyboardButton(text="💬 Чаты"), KeyboardButton(text="🛒 Заказы")],
            [KeyboardButton(text="🏷 Товары"), KeyboardButton(text="💳 Транзакции")]
        ],
        resize_keyboard=True
    )

def profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Пополнить", callback_data="stub"), InlineKeyboardButton(text="💎 Подписка", callback_data="stub")],
            [InlineKeyboardButton(text="💸 Перевести баланс", callback_data="stub")],
            [InlineKeyboardButton(text="🧾 Мои инвойсы", callback_data="stub"), InlineKeyboardButton(text="📝 Мои посты", callback_data="stub")],
            [InlineKeyboardButton(text="▶️ Активировать промокод", callback_data="activate_promo")]
        ]
    )

# --- Генератор страниц настроек (Все функции из видео) ---
def settings_page(page: int):
    buttons = []
    if page == 1:
        buttons = [
            [InlineKeyboardButton(text="🔄 Сбросить настройки", callback_data="stub")],
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="♻️ Авто-восстановление", callback_data="stub")],
            [InlineKeyboardButton(text="🚀 Авто-поднятие", callback_data="stub")],
            [InlineKeyboardButton(text="💬 Автоответчик", callback_data="stub")],
            [InlineKeyboardButton(text="🤖 Авто-выдача", callback_data="menu_autodelivery")],
            [InlineKeyboardButton(text="🧩 Плагины", callback_data="stub")],
            [InlineKeyboardButton(text="⚙️ Переключатели", callback_data="stub")]
        ]
    elif page == 2:
        buttons = [
            [InlineKeyboardButton(text="🔒 Подтверждение заказов", callback_data="stub")],
            [InlineKeyboardButton(text="📝 Заготовки ответов", callback_data="menu_templates")],
            [InlineKeyboardButton(text="⛔️ Черный список", callback_data="stub")],
            [InlineKeyboardButton(text="💸 Авто-вывод", callback_data="stub")],
            [InlineKeyboardButton(text="👋 Приветственное", callback_data="stub")],
            [InlineKeyboardButton(text="✅ Авто-выполнение", callback_data="stub")],
            [InlineKeyboardButton(text="👀 Мониторинг отзывов", callback_data="stub")],
            [InlineKeyboardButton(text="↩️ Ответ на возврат", callback_data="stub")]
        ]
    elif page == 3:
        buttons = [
            [InlineKeyboardButton(text="⚠️ Авто-ответ на проблему", callback_data="stub")],
            [InlineKeyboardButton(text="⏰ Напоминание о подтверждении", callback_data="stub")],
            [InlineKeyboardButton(text="⭐ Напоминание об отзыве", callback_data="stub")],
            [InlineKeyboardButton(text="🔗 Привязанные чаты", callback_data="stub")],
            [InlineKeyboardButton(text="🖼 Фотографии", callback_data="stub")],
            [InlineKeyboardButton(text="📥 Импорт настроек", callback_data="stub")],
            [InlineKeyboardButton(text="📤 Экспорт настроек", callback_data="stub")]
        ]

    # Логика круговой пагинации (1 -> 2 -> 3 -> 1)
    prev_page = 3 if page == 1 else page - 1
    next_page = 1 if page == 3 else page + 1
    
    # Тот самый ряд с тремя кнопками
    buttons.append([
        InlineKeyboardButton(text="⬅️", callback_data=f"set_page_{prev_page}"),
        InlineKeyboardButton(text=f"{page} / 3", callback_data="ignore"),
        InlineKeyboardButton(text="➡️", callback_data=f"set_page_{next_page}")
    ])
    # Отдельная кнопка назад
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="close_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def sub_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Покупка", callback_data="stub")],
        [InlineKeyboardButton(text="⭐️ Оставлен отзыв", callback_data="stub")],
        [InlineKeyboardButton(text="✅ Подтверждение получения", callback_data="stub")],
        [InlineKeyboardButton(text="⚠️ Сообщили о проблеме", callback_data="stub")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="set_page_1")]
    ])

def autodelivery_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Мой склад", callback_data="stub")],
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="stub")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="set_page_1")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="create_promo")]
    ])

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    add_user(message.from_user.id, message.from_user.username or "none", message.from_user.first_name)
    await message.answer("Главное меню открыто. Выберите нужный раздел внизу 👇", reply_markup=main_keyboard())

@dp.message(F.text.contains("Настройки"))
async def settings_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ <b>Настройки аккаунта:</b>", reply_markup=settings_page(1), parse_mode="HTML")

@dp.message(F.text.contains("Профиль"))
async def profile_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    text = (f"👤 <b>Мой профиль</b>\n\n🆔 Ваш ID: <code>{message.from_user.id}</code>\n💎 Подписка: Отсутствует\n\n"
            f"📊 <b>Статистика</b>\n➖ Баланс: 0 RUB\n➖ Подключено аккаунтов: {1 if settings_state['account_connected'] else 0} / 1")
    await message.answer(text, reply_markup=profile_keyboard(), parse_mode="HTML")

@dp.message(F.text.contains("Админ-панель"))
async def admin_panel_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("👑 <b>Админ-панель</b>\nУправление ботом:", reply_markup=admin_keyboard(), parse_mode="HTML")

@dp.message(F.text.contains("Мои аккаунты"))
async def accounts_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    if settings_state["account_connected"]:
        # Отображаем визуал из видео как заглушку, пока не готов реальный парсер
        text = "📦 <b>Всего аккаунтов: 1</b>\n\n🟢 <b>SellGemina</b> | 1649.6 ₽ | ⭐️ 206✨\n\n<i>(Отображаются демонстрационные данные. Реальный парсер в разработке)</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Удалить аккаунт", callback_data="stub")]])
    else:
        text = "📦 <b>Всего аккаунтов: 0</b>\n\nНет подключенных аккаунтов."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="bind_account")]])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text.in_(["📊 Статистика", "🌐 Мои прокси", "💬 Чаты", "🛒 Заказы", "🏷 Товары", "💳 Транзакции"]))
async def placeholders(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Раздел в разработке.")

@dp.callback_query()
async def callback_router(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    
    # Обработка переключения 3-х страниц настроек
    if data.startswith("set_page_"):
        page_num = int(data.split("_")[2])
        await callback.message.edit_text("⚙️ <b>Настройки аккаунта:</b>", reply_markup=settings_page(page_num), parse_mode="HTML")
    elif data == "ignore":
        await callback.answer()
    elif data == "close_menu":
        await callback.message.delete()
        await callback.answer()
    
    elif data == "menu_notifications":
        await callback.message.edit_text("🔔 <b>Настройка уведомлений:</b>\nВыберите тип:", reply_markup=sub_menu_keyboard(), parse_mode="HTML")
    elif data == "menu_templates":
        await callback.message.edit_text("📝 <b>Заготовки ответов:</b>\nДля какой ситуации настроить автоответ?", reply_markup=sub_menu_keyboard(), parse_mode="HTML")
    elif data == "menu_autodelivery":
        await callback.message.edit_text("🤖 <b>Авто-выдача:</b>\nУправление товарами для выдачи:", reply_markup=autodelivery_keyboard(), parse_mode="HTML")
    
    elif data == "bind_account":
        await callback.message.answer("🔑 Отправьте ваш Token (cookie) от аккаунта Playerok в чат:")
        await state.set_state(BotStates.waiting_for_token)
        await callback.answer()

    elif data == "create_promo":
        await callback.message.answer("Введите название для нового промокода (например: SALE20):")
        await state.set_state(BotStates.waiting_for_promo_name)
        await callback.answer()

    elif data == "activate_promo":
        await callback.message.answer("Введите промокод:")
        await state.set_state(BotStates.waiting_for_promo_activation)
        await callback.answer()

    elif data == "stub":
        await callback.answer("Функция в разработке", show_alert=False)

# FSM Состояния
@dp.message(BotStates.waiting_for_token)
async def process_token(message: Message, state: FSMContext):
    settings_state["account_connected"] = True
    settings_state["token"] = message.text 
    await message.answer("✅ <b>Токен принят!</b>\n\n⚠️ <i>Функция реального подключения к Playerok сейчас находится в доработке. Мы сохранили ваш токен и пока симулируем работу аккаунта.</i>\n\nЗайдите в '📦 Мои аккаунты', чтобы проверить.", parse_mode="HTML")
    await state.clear()

@dp.message(BotStates.waiting_for_promo_name)
async def process_promo_name(message: Message, state: FSMContext):
    await state.update_data(promo_name=message.text.upper())
    await message.answer("Отлично. Теперь введите процент скидки (только число):")
    await state.set_state(BotStates.waiting_for_promo_discount)

@dp.message(BotStates.waiting_for_promo_discount)
async def process_promo_discount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите только число (процент скидки).")
        return
    data = await state.get_data()
    promo_name = data['promo_name']
    discount = int(message.text)
    
    promocodes_db[promo_name] = discount 
    await message.answer(f"✅ Промокод <b>{promo_name}</b> на скидку <b>{discount}%</b> успешно создан!", parse_mode="HTML")
    await state.clear()

@dp.message(BotStates.waiting_for_promo_activation)
async def process_promo_activation(message: Message, state: FSMContext):
    promo = message.text.upper()
    if promo in promocodes_db:
        discount = promocodes_db[promo]
        new_price = int(SUBSCRIPTION_PRICE - (SUBSCRIPTION_PRICE * (discount / 100)))
        await message.answer(f"✅ Промокод найден! Скидка {discount}% применена.\n\nЦена подписки снижена с {SUBSCRIPTION_PRICE} ₽ до <b>{new_price} ₽</b>.", parse_mode="HTML")
    else:
        await message.answer("❌ Неверный или несуществующий промокод.")
    await state.clear()

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
