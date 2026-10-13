"""Общие мелочи для кнопок и сообщений."""
import html
from urllib.parse import urlencode

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo,
)

import config
import database as db

# Названия кнопок главного меню
BTN_SETTINGS = "🛠 Настройки"
BTN_STATS = "📈 Статистика"
BTN_SHOPS = "🏪 Мои магазины"
BTN_PROFILE = "🙋 Профиль"
BTN_PROXY = "🛰 Прокси"
BTN_CHATS = "💭 Чаты"
BTN_ORDERS = "🧾 Заказы"
BTN_GOODS = "🏷 Товары"
BTN_PAYMENTS = "💱 Платежи"
BTN_ADMIN = "👑 Админ-панель"


def esc(x):
    return html.escape(str(x if x is not None else ""))


def short(x, n=300):
    x = str(x if x is not None else "")
    return x if len(x) <= n else x[: n - 1] + "…"


def dot(flag):
    return "🟢" if flag else "🔴"


def B(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


def URL(text, url):
    return InlineKeyboardButton(text=text, url=url)


def webapp_url(**params):
    if not config.WEBAPP_URL:
        return None
    q = urlencode(params)
    return config.WEBAPP_URL + ("?" + q if q else "")


def W(text, **params):
    """Кнопка открытия мини-приложения (None, если ссылка не задана)."""
    url = webapp_url(**params)
    if not url:
        return None
    return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))


def KB(*rows):
    clean = []
    for r in rows:
        r = [b for b in r if b is not None]
        if r:
            clean.append(r)
    return InlineKeyboardMarkup(inline_keyboard=clean)


def support_btn(text="💬 Поддержка"):
    nick = db.get_cfg("support", "").lstrip("@")
    return URL(text, f"https://t.me/{nick}") if nick else None


def main_menu(uid):
    rows = [
        [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_STATS)],
        [KeyboardButton(text=BTN_SHOPS), KeyboardButton(text=BTN_PROFILE)],
        [KeyboardButton(text=BTN_PROXY)],
        [KeyboardButton(text=BTN_CHATS), KeyboardButton(text=BTN_ORDERS)],
        [KeyboardButton(text=BTN_GOODS), KeyboardButton(text=BTN_PAYMENTS)],
    ]
    if db.is_admin(uid):
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def fmt_date(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y - %H:%M")


async def reply(message, text, kb=None):
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


class Ctx:
    """Обёртка вокруг нажатия кнопки: ответ на нажатие отправляется ровно один раз."""

    def __init__(self, cb, state):
        self.cb = cb
        self.state = state
        self.uid = cb.from_user.id
        self.acked = False

    async def ack(self, text=None, alert=False):
        if not self.acked:
            self.acked = True
            try:
                await self.cb.answer(text, show_alert=alert)
            except Exception:
                pass

    async def edit(self, text, kb=None):
        try:
            await self.cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                return
            await self.cb.message.answer(text, reply_markup=kb, parse_mode="HTML")

    async def send(self, text, kb=None):
        await self.cb.message.answer(text, reply_markup=kb, parse_mode="HTML")

    async def delete(self):
        try:
            await self.cb.message.delete()
        except Exception:
            pass
