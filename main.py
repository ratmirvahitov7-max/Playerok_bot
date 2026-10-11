import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, WebAppInfo
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
    "token": None,
    "vip_status": False # Флаг наличия премиум подписки
}
promocodes_db = {} 
SUBSCRIPTION_PRICE = 499 

class BotStates(StatesGroup):
    waiting_for_token = State()
    waiting_for_promo_name = State()
    waiting_for_promo_discount = State()
    waiting_for_promo_activation = State()
    waiting_for_reply = State() # Состояние для функции "Ответ" на заказ

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

def settings_page(page: int):
    buttons = []
    if page == 1:
        buttons = [
            [InlineKeyboardButton(text="🔄 Сбросить настройки", callback_data="stub")],
            [InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu_notifications")],
            [InlineKeyboardButton(text="♻️ Авто-восстановление", callback_data="stub")],
            [InlineKeyboardButton(text="🔒 Авто-поднятие", callback_data="locked_feature")],
            [InlineKeyboardButton(text="💬 Автоответчик", callback_data="stub")],
            [InlineKeyboardButton(text="🤖 Авто-выдача", callback_data="menu_autodelivery")],
            [InlineKeyboardButton(text="🧩 Плагины", callback_data="stub")],
            [InlineKeyboardButton(text="⚙️ Переключатели", callback_data="stub")],
            [InlineKeyboardButton(text="🔒 Подтверждение заказов", callback_data="locked_feature")],
            [InlineKeyboardButton(text="📝 Заготовки ответов", callback_data="menu_templates")],
            [InlineKeyboardButton(text="⛔️ Черный список", callback_data="stub")]
        ]
    elif page == 2:
        buttons = [
            [InlineKeyboardButton(text="🔒 Авто-вывод", callback_data="locked_feature")],
            [InlineKeyboardButton(text="👋 Приветственное", callback_data="stub")],
            [InlineKeyboardButton(text="✅ Авто-выполнение", callback_data="stub")],
            [InlineKeyboardButton(text="🔒 Мониторинг отзывов", callback_data="locked_feature")],
            [InlineKeyboardButton(text="↩️ Ответ на возврат", callback_data="stub")],
            [InlineKeyboardButton(text="⚠️ Авто-ответ на проблему", callback_data="stub")],
            [InlineKeyboardButton(text="🔒 Напоминание о подтверждении", callback_data="locked_feature")],
            [InlineKeyboardButton(text="🔒 Напоминание об отзыве", callback_data="locked_feature")],
            [InlineKeyboardButton(text="🔗 Привязанные чаты", callback_data="stub")],
            [InlineKeyboardButton(text="🖼 Фотографии", callback_data="stub")]
        ]
    elif page == 3:
        buttons = [
            [InlineKeyboardButton(text="📥 Импорт настроек", callback_data="stub")],
            [InlineKeyboardButton(text="📤 Экспорт настроек", callback_data="stub")]
        ]

    prev_page = 3 if page == 1 else page - 1
    next_page = 1 if page == 3 else page + 1
    
    buttons.append([
        InlineKeyboardButton(text="⬅️", callback_data=f"set_page_{prev_page}"),
        InlineKeyboardButton(text=f"{page} / 3", callback_data="ignore"),
        InlineKeyboardButton(text="➡️", callback_data=f"set_page_{next_page}")
    ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="close_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Клавиатура для нового заказа (3x3)
def order_keyboard(order_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 Заказ", url=f"https://playerok.com/orders/{order_id}"),
                InlineKeyboardButton(text="💬 Чат", url=f"https://playerok.com/chat/{order_id}"),
                InlineKeyboardButton(text="🛒 Товар", url=f"https://playerok.com/items/{order_id}")
            ],
            [
                InlineKeyboardButton(text="💸 Возврат", callback_data=f"order_refund_{order_id}"),
                InlineKeyboardButton(text="✅ Выполнил", callback_data=f"order_complete_{order_id}"),
                InlineKeyboardButton(text="➕ Больше", callback_data=f"order_more_{order_id}")
            ],
            [
                InlineKeyboardButton(text="📋 Заготовки", callback_data=f"order_templates_{order_id}"),
                InlineKeyboardButton(text="🕰 История", callback_data=f"order_history_{order_id}"),
                InlineKeyboardButton(text="✍️ Ответ", callback_data=f"order_reply_{order_id}")
            ]
        ]
    )

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

# --- ТЕСТОВОЕ СОБЫТИЕ НОВОГО ЗАКАЗА ---
# Так как реального API Playerok тут нет, сделаем команду для имитации заказа
@dp.message(F.text == "/testorder")
async def test_order(message: Message):
    if not settings_state["account_connected"]:
        await message.answer("Сначала подключите аккаунт в '📦 Мои аккаунты'")
        return
        
    order_id = "1f1c582d"
    text = (
        f"🟢 (SellGemina) <b>Новый заказ!</b> Товар: LOVABLE PRO\n\n"
        f"👤 Покупатель: HukuTuYc\n"
        f"💰 Сумма: 990 ₽\n"
        f"🆔 ID: {order_id}"
    )
    await message.answer(text, reply_markup=order_keyboard(order_id), parse_mode="HTML")

@dp.message(F.text.contains("Настройки"))
async def settings_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("⚙️ <b>Настройки аккаунта:</b>", reply_markup=settings_page(1), parse_mode="HTML")

@dp.message(F.text.contains("Профиль"))
async def profile_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    vip_text = "Присутствует ✅" if settings_state["vip_status"] else "Отсутствует ❌"
    text = (f"👤 <b>Мой профиль</b>\n\n🆔 Ваш ID: <code>{message.from_user.id}</code>\n💎 Подписка: {vip_text}\n\n"
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
        text = "📦 <b>Всего аккаунтов: 1</b>\n\n🟢 <b>SellGemina</b> | 1649.6 ₽ | ⭐️ 206✨\n\n<i>(Отображаются демонстрационные данные)</i>"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Удалить аккаунт", callback_data="stub")]])
    else:
        text = "📦 <b>Всего аккаунтов: 0</b>\n\nНет подключенных аккаунтов."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="bind_account")]])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text.contains("Статистика"))
async def stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID: return
    
    if not settings_state["account_connected"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔌 Подключить аккаунт Playerok", callback_data="bind_account")]])
        await message.answer("⚠️ <b>Доступ закрыт</b>\n\nДля просмотра статистики необходимо сначала подключить аккаунт Playerok.", reply_markup=kb, parse_mode="HTML")
    else:
        text = (
            "📊 <b>Статистика работы бота</b>\n\n"
            "📈 <b>За сегодня:</b>\n"
            "💸 Заработано: 0 ₽\n"
            "🛒 Успешных сделок: 0 шт.\n\n"
            "<i>(Расширенная аналитика доступна в WebApp)</i>"
        )
        # Замени URL ниже на ссылку твоего GitHub Pages
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть WebApp Статистику", web_app=WebAppInfo(url="https://ratmirvahitov7-max.github.io/webapp-ui/"))]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text.in_(["🌐 Мои прокси", "💬 Чаты", "🛒 Заказы", "🏷 Товары", "💳 Транзакции"]))
async def placeholders(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Раздел в разработке.")

@dp.callback_query()
async def callback_router(callback: CallbackQuery, state: FSMContext):
    data = callback.data
    
    # --- ЛОГИКА НАСТРОЕК ---
    if data.startswith("set_page_"):
        page_num = int(data.split("_")[2])
        await callback.message.edit_text("⚙️ <b>Настройки аккаунта:</b>", reply_markup=settings_page(page_num), parse_mode="HTML")
    elif data == "ignore":
        await callback.answer()
    elif data == "close_menu":
        await callback.message.delete()
        await callback.answer()
        
    elif data == "locked_feature":
        if not settings_state["vip_status"]:
            await callback.answer("🔒 Эта функция доступна только с подпиской!\n\nОформи подписку, чтобы разблокировать все возможности бота.", show_alert=True)
        else:
            await callback.answer("✅ Доступ разрешен (настройки функции)", show_alert=False)

    elif data == "menu_notifications":
        await callback.message.edit_text("🔔 <b>Настройка уведомлений:</b>\nВыберите тип:", reply_markup=sub_menu_keyboard(), parse_mode="HTML")
    elif data == "menu_templates":
        await callback.message.edit_text("📝 <b>Заготовки ответов:</b>\nДля какой ситуации настроить автоответ?", reply_markup=sub_menu_keyboard(), parse_mode="HTML")
    elif data == "menu_autodelivery":
        await callback.message.edit_text("🤖 <b>Авто-выдача:</b>\nУправление товарами для выдачи:", reply_markup=autodelivery_keyboard(), parse_mode="HTML")
    
    # --- ЛОГИКА НОВОГО ЗАКАЗА ---
    elif data.startswith("order_refund_"):
        await callback.answer("⏳ Отправляем запрос на возврат...", show_alert=False)
        # Тут будет реальный API запрос
    elif data.startswith("order_complete_"):
        await callback.answer("✅ Отправляем запрос на подтверждение выполнения...", show_alert=False)
        # Тут будет реальный API запрос
    elif data.startswith("order_reply_"):
        order_id = data.split("_")[2]
        await state.update_data(current_order_id=order_id)
        await state.set_state(BotStates.waiting_for_reply)
        await callback.message.answer("✍️ Отправьте сообщение, и оно будет автоматически отправлено покупателю:")
        await callback.answer()
    elif data.startswith("order_more_") or data.startswith("order_templates_") or data.startswith("order_history_"):
        await callback.answer("Функция в разработке", show_alert=False)
    
    # --- ОСТАЛЬНОЕ ---
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

# Обработчик текста для ответа покупателю
@dp.message(BotStates.waiting_for_reply)
async def process_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("current_order_id")
    # Тут должен быть API-запрос на отправку сообщения покупателю
    await message.answer(f"✅ Сообщение успешно отправлено покупателю по заказу <b>{order_id}</b>!", parse_mode="HTML")
    await state.clear()

@dp.message(BotStates.waiting_for_token)
async def process_token(message: Message, state: FSMContext):
    settings_state["account_connected"] = True
    settings_state["token"] = message.text 
    await message.answer("✅ <b>Токен принят!</b>\n\nТеперь вы можете протестировать появление заказа. Отправьте команду /testorder", parse_mode="HTML")
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
