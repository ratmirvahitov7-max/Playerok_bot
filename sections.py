"""Раздел «Настройки»: все меню и фильтры, как на видео, но с другими названиями и значками."""
import copy
import json
import re
import secrets

from aiogram.types import BufferedInputFile

import config
import database as db
from ui import B, Ctx, KB, W, dot, esc, short, reply, URL

MAX_FILTERS = 25

# ------------------------------------------------------------------ описание полей
def T(k, label, d=False):
    return {"k": k, "t": "toggle", "label": label, "d": d}


def X(k, label, d="", icon="✏️"):
    return {"k": k, "t": "text", "label": label, "d": d, "icon": icon}


def KW(k, label):
    return {"k": k, "t": "text", "label": label, "d": "", "icon": "🔑"}


def N(k, label, d=0, zero=None, unit="", row=None, max=100000):
    return {"k": k, "t": "int", "label": label, "d": d, "zero": zero, "unit": unit, "row": row, "max": max}


def C(k, label, options, d):
    return {"k": k, "t": "choice", "label": label, "options": options, "d": d}


SECTIONS = {}


def section(key, **meta):
    meta.setdefault("page", 1)
    meta.setdefault("premium", False)
    meta.setdefault("toggle", False)
    meta.setdefault("toggle_d", False)
    meta.setdefault("toggle_label", "Включено")
    meta.setdefault("item", "фильтр")
    meta.setdefault("plural", "Фильтров")
    meta.setdefault("globals", [])
    meta.setdefault("bulk", True)
    meta.setdefault("help", "")
    meta.setdefault("add_prompt", "🏷 Отправь название нового фильтра")
    meta.setdefault("stats", False)
    meta.setdefault("extras", [])
    SECTIONS[key] = meta


section(
    "restore", title="🔁 Автовосстановление", toggle=True, toggle_label="Автовосстановление",
    intro="Бот возвращает проданные лоты в продажу. Создай фильтры: какие товары восстанавливать.",
    globals=[T("scan", "Сканировать завершённые", True)],
    fields=[T("enabled", "Включить фильтр", True), KW("kw", "Ключевые слова в названии"),
            N("pmin", "Мин. цена", 0, "Нет", " ₽", row="p"), N("pmax", "Макс. цена", 0, "Нет", " ₽", row="p"),
            N("delay", "Задержка, мин", 0, "Нет")],
    help="Бот видит, что товар продан, и выставляет его снова.\n\n"
         "• Фильтр решает, какие лоты восстанавливать: по словам в названии и по цене.\n"
         "• Если подходящих фильтров несколько, берётся первый.\n"
         "• «Сканировать завершённые» — бот проверяет и уже завершённые заказы.",
)

section(
    "boost", title="⬆️ Автоподъём", premium=True, toggle=True, toggle_label="Автоподъём", stats=True,
    intro="Бот сам поднимает твои лоты в выдаче. Настрой фильтры: какие товары поднимать и когда.",
    globals=[N("max_per_day", "Общий лимит подъёмов в день", 0, "Нет"), N("cooldown", "Пауза между подъёмами, мин", 30, "Нет")],
    fields=[T("enabled", "Включить фильтр", False),
            C("mode", "Режим", [("interval", "по интервалу"), ("position", "по позиции"), ("hours", "по часам")], "interval"),
            N("interval", "Интервал, мин", 30, "Нет"), N("place", "Место в выдаче", 3, "Нет"),
            X("hours", "Часы подъёма (например 09:00, 18:00)", ""),
            N("per_day", "Лимит в день", 0, "Нет"),
            KW("kw", "Ключевые слова"), KW("kw_ex", "Слова-исключения"),
            N("pmin", "Мин. цена", 0, "Нет", " ₽", row="p"), N("pmax", "Макс. цена", 0, "Нет", " ₽", row="p"),
            N("budget", "Бюджет, ₽", 0, "Без лимита")],
    help="Подъём возвращает твой лот в верхнюю часть выдачи.\n\n"
         "<b>Когда поднимать</b>\n• По интервалу — каждые N минут.\n"
         "• По позиции — когда лот опустился ниже нужного места.\n"
         "• По часам — в заданное время, например 09:00 и 18:00.\n\n"
         "<b>Какие товары</b>\nКлючевые слова — поднимать только лоты с этими словами. Исключения — не трогать лоты с этими словами. "
         "Цена — диапазон, в который должен попасть лот.\n\n"
         "<b>Бюджет</b>\nКогда бюджет фильтра заканчивается, подъёмы останавливаются.\n\n"
         "Если подходящих фильтров несколько, берётся первый сверху.",
)

section(
    "reply", title="🤖 Автоответ на команды", toggle=True, toggle_d=True, toggle_label="Автоответ",
    item="команду", plural="Команд", add_prompt="⌨️ Отправь команду, например: !позвать",
    intro="Покупатель пишет команду в чат, а бот отвечает заготовленным текстом.",
    fields=[T("enabled", "Включено", True), X("text", "Текст ответа", "Команда принята. Продавец скоро ответит.", "💬"),
            X("notify_text", "Текст уведомления", "Покупатель {buyer} использовал команду.", "🔔"),
            T("notify", "Уведомление в Telegram", True), T("exact", "Точное совпадение", True),
            T("do_last", "Выполнять последний заказ", False), T("refund_last", "Возврат по последнему заказу", False),
            T("kw_filter", "Фильтр товаров по словам", False)],
    help="Бот реагирует на команду в чате с покупателем.\n\n"
         "• «Точное совпадение» — сработает только если сообщение полностью равно команде.\n"
         "• В тексте можно использовать {buyer} (ник покупателя), {shop_name} (магазин), {good_name} (товар).\n"
         "• Уведомление придёт тебе в Telegram, когда покупатель использует команду.",
)

section(
    "delivery", title="🎁 Автодоставка", toggle=True, toggle_d=True, toggle_label="Автодоставка",
    item="товар", plural="Товаров", add_prompt="📦 Отправь название товара",
    intro="Выбери товар для настройки или добавь новый. Бот сам отправит покупателю товар после оплаты.",
    globals=[T("reply_on", "Ответы на заказ", True), T("notify", "Уведомления при выдаче", True),
             N("delay", "Задержка выдачи, мин", 15, "Нет")],
    fields=[T("enabled", "Автодоставка", True), X("items", "Товары (по одному в строке)", "", "📦"),
            X("order_reply", "Ответ на заказ", "Спасибо за покупку! Ваш товар:\n{product}", "💬")],
    extras=[("📤 Экспорт всех товаров", "export")],
    help="Бот отправляет покупателю следующий товар из списка сразу после оплаты.\n\n"
         "• Каждый товар — отдельная строка в списке.\n• Когда список заканчивается, доставка останавливается и приходит уведомление.\n"
         "• В ответе на заказ используй {product} — туда подставится товар.\n• Задержка выдачи — через сколько минут отправлять товар.",
)

section(
    "confirm_reply", title="✅ Ответ на подтверждение заказа", premium=True,
    intro="Сообщение покупателю после того, как он подтвердил получение заказа.",
    fields=[T("enabled", "Включить фильтр", True), X("text", "Текст сообщения", "Спасибо за подтверждение! Оставьте, пожалуйста, отзыв.", "💬")],
    help="Бот напишет покупателю, когда тот нажмёт «Подтвердить получение».",
)

section(
    "templates", title="📝 Заготовки ответов", item="шаблон", plural="Всего шаблонов", bulk=False,
    add_prompt="📝 Отправь название шаблона",
    intro="Быстрые ответы покупателям. Нажми на шаблон, чтобы изменить текст.",
    fields=[X("text", "Текст шаблона", "", "💬")],
    help="Сохраняй частые ответы и отправляй их покупателям одним нажатием.",
)

section(
    "welcome", page=2, title="👋 Приветственное сообщение", toggle=True, toggle_label="Приветствие",
    intro="Это сообщение получит каждый новый покупатель, с которым у тебя ещё не было диалога.",
    fields=[T("enabled", "Включить фильтр", True), X("text", "Текст приветствия", "Здравствуйте! Спасибо, что написали. Скоро отвечу.", "💬"),
            N("delay", "Задержка, сек", 0, "Нет")],
    help="Приветствие отправляется один раз каждому новому собеседнику. Если подходящих фильтров несколько, берётся первый.",
)

section(
    "autocomplete", page=2, title="✔️ Автовыполнение заказов", toggle=True, toggle_label="Автовыполнение",
    intro="Бот сам отмечает заказ выполненным сразу после оплаты. Удобно для товаров с автодоставкой.",
    fields=[T("enabled", "Включить фильтр", True), KW("kw", "Ключевые слова в названии"),
            N("pmin", "Мин. цена", 0, "Нет", " ₽", row="p"), N("pmax", "Макс. цена", 0, "Нет", " ₽", row="p")],
    help="После оплаты бот нажимает «Я выполнил» за тебя. Подходит для товаров, которые выдаются автоматически.",
)

section(
    "reviews", page=2, title="⭐ Мониторинг отзывов", premium=True, toggle=True, toggle_label="Мониторинг отзывов",
    intro="Бот следит за новыми отзывами и отвечает на них.",
    fields=[T("enabled", "Включить фильтр", True), N("min_rating", "Мин. рейтинг", 1, "Нет", max=5),
            X("text", "Ответ на отзыв", "Спасибо за отзыв! Будем рады видеть вас снова.", "💬"),
            N("delay_reply", "Задержка ответа, мин", 0, "Нет"), N("delay_support", "Задержка в поддержку, ч", 1, "Нет")],
    help="Бот отвечает на отзывы с рейтингом не ниже заданного. Задержка ответа делает его похожим на живого человека.",
)

section(
    "refund_reply", page=2, title="↩️ Ответ на возврат", toggle=True, toggle_label="Ответ на возврат",
    intro="Сообщение покупателю, когда по заказу оформлен возврат.",
    fields=[T("enabled", "Включить фильтр", True), X("text", "Текст сообщения", "Возврат оформлен. Если нужна помощь — напишите.", "💬"),
            KW("kw", "Ключевые слова в названии")],
    help="Бот напишет покупателю после возврата средств. Если подходящих фильтров несколько, берётся первый.",
)

section(
    "problem_reply", page=2, title="🆘 Автоответ на проблему", toggle=True, toggle_label="Автоответ на проблему",
    intro="Что бот напишет покупателю, если он сообщил о проблеме с заказом.",
    fields=[T("enabled", "Включить фильтр", True), X("text", "Текст сообщения", "Вижу, у вас проблема. Опишите её и приложите доказательства.", "💬"),
            KW("kw", "Ключевые слова в названии"), T("auto_refund", "Автовозврат средств", False),
            T("to_blacklist", "Добавлять в чёрный список", False)],
    help="Когда покупатель открывает проблему, бот отвечает и, если включено, сам делает возврат.\n\n"
         "⚠️ Автовозврат срабатывает без тебя. Включай его осознанно.",
)

section(
    "confirm_reminder", page=2, title="⏰ Напоминание о подтверждении", premium=True, toggle=True, toggle_label="Напоминание о подтверждении",
    intro="Бот напомнит покупателю подтвердить заказ, если он этого не сделал.",
    fields=[T("enabled", "Включить фильтр", True), N("after", "Напомнить через, ч", 3, "Нет"),
            X("text", "Текст напоминания", "Пожалуйста, подтвердите получение заказа.", "💬")],
    help="Если покупатель не подтвердил заказ за указанное время, бот отправит напоминание.",
)

section(
    "review_reminder", page=2, title="🌟 Напоминание об отзыве", premium=True, toggle=True, toggle_label="Напоминание об отзыве",
    intro="Бот напомнит покупателю оставить отзыв.",
    fields=[T("enabled", "Включить фильтр", True), N("after", "Напомнить через, ч", 24, "Нет"),
            X("text", "Текст напоминания", "Будем благодарны за отзыв о заказе!", "💬")],
    help="Если покупатель подтвердил заказ, но не оставил отзыв, бот отправит напоминание.",
)

# ------------------------------------------------------------------ страницы меню настроек
PAGES = {
    1: [("m:reset", "♻️ Сбросить настройки", False), ("m:notif", "🔔 Уведомления", False),
        ("s:restore", None, False), ("s:boost", None, False), ("s:reply", None, False), ("s:delivery", None, False),
        ("m:plug", "🧩 Плагины", False), ("m:sw", "🎛 Переключатели", False), ("s:confirm_reply", None, False),
        ("s:templates", None, False), ("m:bl", "⛔ Чёрный список", False)],
    2: [("m:wd", "💸 Автовыплата", True), ("s:welcome", None, False), ("s:autocomplete", None, False),
        ("s:reviews", None, False), ("s:refund_reply", None, False), ("s:problem_reply", None, False),
        ("s:confirm_reminder", None, False), ("s:review_reminder", None, False),
        ("m:ch", "🔗 Привязанные чаты", False), ("m:ph", "🖼 Фотографии", False)],
    3: [("m:imp", "📥 Импорт настроек", False), ("m:exp", "📤 Экспорт настроек", False)],
}
PAGE_COUNT = 3

PLUGINS = [
    ("dump", "📉", "Автодемпер", "Ставит цену твоих лотов на 1 ₽ ниже конкурентов, но только внутри диапазона, который ты задашь."),
    ("kosell", "🔑", "Аренда KoSell", "Автоаренда аккаунтов из каталога по ключу KoSell."),
    ("steam", "🎮", "Аренда Steam", "Выдача Steam-аккаунтов в аренду, код Guard по команде и смена пароля."),
    ("stars", "⭐", "Звёзды Telegram", "Автоматическая продажа звёзд Telegram."),
]

SW_LABELS = [
    ("quick_replies", "Быстрые ответы в чате"), ("profit_calc", "Калькулятор прибыли"),
    ("relist", "Автоперевыставление товаров"), ("relist_expired", "Автоперевыставление истёкших"),
    ("anon_read", "Анонимное чтение"),
]

LOCK_TEXT = "🔒 Эта функция доступна с подпиской.\n\nОформи её: Профиль → Подписка."


# ------------------------------------------------------------------ вспомогательное
def _find(s, key, fid):
    for f in s["filters"].get(key, []):
        if f["id"] == fid:
            return f
    return None


def _fd(meta, field):
    for fd in meta["fields"]:
        if fd["k"] == field:
            return fd
    return None


def _gd(meta, field):
    for fd in meta["globals"]:
        if fd["k"] == field:
            return fd
    return None


def fval(f, fd):
    return f.get(fd["k"], fd["d"])


def gval(s, key, fd):
    return s["glob"].get(key, {}).get(fd["k"], fd["d"])


def sect_on(s, key):
    meta = SECTIONS[key]
    return s["sections"].get(key, meta["toggle_d"])


def display(fd, v):
    t = fd["t"]
    if t == "toggle":
        return "Вкл" if v else "Выкл"
    if t == "int":
        if not v and fd.get("zero"):
            return fd["zero"]
        return f"{v}{fd.get('unit', '')}"
    if t == "choice":
        for val, lab in fd["options"]:
            if val == v:
                return lab
        return str(v)
    return f"<code>{esc(short(v, 300))}</code>" if v else "—"


def field_label(fd, v):
    t = fd["t"]
    if t == "toggle":
        return f"{dot(v)} {fd['label']}"
    if t == "int":
        return f"{fd['label']}: {display(fd, v)}"
    if t == "choice":
        return f"🔀 {fd['label']}: {display(fd, v)}"
    return f"{fd.get('icon', '✏️')} {fd['label']}"


def _premium_ok(uid, meta):
    return (not meta["premium"]) or db.is_premium(uid)


# ------------------------------------------------------------------ главная страница настроек
def settings_header(uid):
    acc = db.list_accounts(uid)
    name = esc(acc[0]["name"]) if acc else "не подключён"
    return f"🛠 <b>Настройки аккаунта:</b> {name}\n\nВыбери нужный раздел:"


def settings_kb(uid, page):
    prem = db.is_premium(uid)
    rows = []
    for data, label, locked in PAGES[page]:
        if label is None:
            meta = SECTIONS[data.split(":")[1]]
            label = meta["title"]
            locked = meta["premium"]
        if locked and not prem:
            label = "🔒 " + label.split(" ", 1)[-1] if label[:1] not in "🔒" else label
        rows.append([B(label, data)])
    prev_p = PAGE_COUNT if page == 1 else page - 1
    next_p = 1 if page == PAGE_COUNT else page + 1
    rows.append([B("⬅️", f"set:{prev_p}"), B(f"{page} / {PAGE_COUNT}", "noop"), B("➡️", f"set:{next_p}")])
    rows.append([B("← Назад", "close")])
    return KB(*rows)


# ------------------------------------------------------------------ раздел с фильтрами
def section_text(s, key):
    meta = SECTIONS[key]
    flts = s["filters"].get(key, [])
    has_enabled = _fd(meta, "enabled") is not None
    lines = [f"<b>{meta['title']}</b>", "", meta["intro"], ""]
    count = f"{meta['plural']}: <b>{len(flts)}</b>"
    if has_enabled:
        active = sum(1 for f in flts if f.get("enabled", True if _fd(meta, "enabled")["d"] else False))
        count += f"  ·  Активных: <b>{active}</b>"
    lines.append(count)
    if meta["toggle"]:
        lines.append(f"Раздел: {'🟢 включён' if sect_on(s, key) else '🔴 выключен'}")
    if meta["stats"]:
        lines += ["", "<b>Статистика</b>", "Всего: 0 подъёмов на 0 ₽", "Сегодня: 0 ₽ · Неделя: 0 ₽ · Месяц: 0 ₽"]
    return "\n".join(lines)


def section_kb(s, key):
    meta = SECTIONS[key]
    rows = []
    if meta["toggle"]:
        on = sect_on(s, key)
        rows.append([B(f"{dot(on)} {meta['toggle_label']} {'ВКЛ' if on else 'ВЫКЛ'}", f"sx:{key}:toggle")])
    for f in s["filters"].get(key, []):
        en = f.get("enabled", _fd(meta, "enabled")["d"]) if _fd(meta, "enabled") else True
        mark = dot(en) + " " if _fd(meta, "enabled") else "📄 "
        rows.append([B(mark + short(f["name"], 30), f"f:{key}:{f['id']}")])
    rows.append([B(f"➕ Добавить {meta['item']}", f"sx:{key}:add")])
    if meta["bulk"] and _fd(meta, "enabled"):
        rows.append([B("✅ Вкл. все", f"sx:{key}:on"), B("❌ Выкл. все", f"sx:{key}:off")])
    for fd in meta["globals"]:
        v = gval(s, key, fd)
        if fd["t"] == "toggle":
            rows.append([B(f"{dot(v)} {fd['label']}", f"g:{key}:{fd['k']}")])
        else:
            rows.append([B(f"⚙️ {fd['label']}: {display(fd, v)}", f"ge:{key}:{fd['k']}")])
    for label, act in meta["extras"]:
        rows.append([B(label, f"sx:{key}:{act}")])
    if meta["help"]:
        rows.append([B("📖 Помощь", f"sx:{key}:help")])
    rows.append([B("← Назад", f"set:{meta['page']}")])
    return KB(*rows)


def filter_text(meta, f):
    lines = [f"⚙️ <b>Настройки: «{esc(f['name'])}»</b>", ""]
    for fd in meta["fields"]:
        if fd["t"] == "toggle":
            continue
        lines.append(f"• {fd['label']}: {display(fd, fval(f, fd))}")
    return "\n".join(lines)


def filter_kb(key, meta, f):
    rows, cur, row = [], None, []
    for fd in meta["fields"]:
        v = fval(f, fd)
        kind = "ft" if fd["t"] in ("toggle", "choice") else "fe"
        btn = B(field_label(fd, v), f"{kind}:{key}:{f['id']}:{fd['k']}")
        if fd.get("row") and fd["row"] == cur:
            row.append(btn)
        else:
            if row:
                rows.append(row)
            row, cur = [btn], fd.get("row")
    if row:
        rows.append(row)
    rows.append([B("✏️ Название", f"fn:{key}:{f['id']}"), B("🗑 Удалить", f"fd:{key}:{f['id']}")])
    rows.append([B("← Назад", f"s:{key}")])
    return KB(*rows)


def _cancel_kb():
    return KB([B("🚫 Отмена", "cancel")])


async def _show_section(ctx, key):
    s = db.get_settings(ctx.uid)
    await ctx.edit(section_text(s, key), section_kb(s, key))


async def _show_filter(ctx, key, fid, new_message=False):
    s = db.get_settings(ctx.uid)
    f = _find(s, key, fid)
    meta = SECTIONS[key]
    if not f:
        await _show_section(ctx, key)
        return
    text, kb = filter_text(meta, f), filter_kb(key, meta, f)
    if new_message:
        await ctx.send(text, kb)
    else:
        await ctx.edit(text, kb)


# ------------------------------------------------------------------ другие меню
def notif_text():
    return "🔔 <b>Настройки уведомлений</b>\n\nВыбери, о чём бот будет писать тебе в Telegram."


def notif_kb(s):
    n = s["notifications"]
    rows = [[B(f"{dot(n['global'])} Отправлять уведомления", "nt:global")]]
    if n["global"]:
        items = db.NOTIF_LABELS
        for i in range(0, len(items), 2):
            rows.append([B(f"{dot(n[k])} {lab}", f"nt:{k}") for k, lab in items[i:i + 2]])
    rows.append([B("← Назад", "set:1")])
    return KB(*rows)


def sw_kb(s):
    rows = [[B(f"{dot(s['switches'][k])} {lab}", f"sw:{k}")] for k, lab in SW_LABELS]
    rows.append([B("← Назад", "set:1")])
    return KB(*rows)


def _method_label(mid):
    return config.PAY_METHODS.get(mid, {}).get("label", "Нет")


def wd_text(s):
    w = s["withdraw"]
    req = w["requisites"].get(w["method"]) if w["method"] else None
    rate = db.get_cfg("rate_usdt", config.DEFAULT_USDT_RATE)
    return ("💸 <b>Меню настроек автовыплаты</b>\n\n"
            f"• Реквизиты: {('<code>' + esc(short(req, 60)) + '</code>') if req else 'Отсутствуют'}\n"
            f"• Метод: {_method_label(w['method'])}\n"
            f"• Курс USDT: {esc(rate)}\n\n"
            "<i>Бот запомнит эти правила. Сами выплаты заработают после подключения магазина.</i>")


def wd_kb(s):
    w = s["withdraw"]
    return KB(
        [B(f"{dot(w['enabled'])} Автовыплата", "wd:enabled")],
        [B(f"{dot(w['notify'])} Уведомления", "wd:notify")],
        [B(f"Мин: {w['min']} ₽", "wde:min"), B(f"Макс: {w['max']} ₽", "wde:max")],
        [B(f"Оставлять на балансе: {str(w['keep']) + ' ₽' if w['keep'] else 'Нет'}", "wde:keep")],
        [B(f"Макс. курс USDT: {w['max_rate'] if w['max_rate'] else 'Нет'}", "wde:max_rate")],
        [B(f"Кулдаун: {w['cooldown']}с", "wde:cooldown"), B(f"Округление: {'Да' if w['rounding'] else 'Нет'}", "wd:rounding")],
        [B(f"Расписание: {short(w['schedule'], 20) if w['schedule'] else 'Нет'}", "wde:schedule")],
        [B("✏️ Изменить реквизиты", "wdm")],
        [B("← Назад", "set:2")],
    )


def plug_kb(uid):
    prem = db.is_premium(uid)
    rows = []
    for pid, icon, title, _ in PLUGINS:
        lock = "" if prem else "🔒 "
        en, _c = db.get_plugin(uid, pid)
        rows.append([B(f"{lock}{icon} {title} {dot(en) if prem else ''}".strip(), f"pl:{pid}")])
    rows.append([B("← Назад", "set:1")])
    return KB(*rows)


def _plugin(pid):
    for p in PLUGINS:
        if p[0] == pid:
            return p
    return None


def bl_kb(s):
    rows = [[B("⛔ Забанить", "bl:add")]]
    for i, nick in enumerate(s["blacklist"][:20]):
        rows.append([B(f"🗑 {short(nick, 30)}", f"bl:del:{i}")])
    rows.append([B(f"{dot(s['blacklist_silent'])} Не отвечать забаненным", "bl:silent")])
    rows.append([B("← Назад", "set:1")])
    return KB(*rows)


def ch_kb(s):
    rows = [[B("➕ Привязать чат", "ch:add")]]
    for i, cid in enumerate(s["chats"][:20]):
        rows.append([B(f"🗑 {short(cid, 30)}", f"ch:del:{i}")])
    rows.append([B("← Назад", "set:2")])
    return KB(*rows)


# ------------------------------------------------------------------ обработка нажатий
async def handle_callback(ctx: Ctx):
    """Возвращает True, если нажатие обработано здесь."""
    data = ctx.cb.data or ""
    uid = ctx.uid
    p = data.split(":")
    head = p[0]

    if data == "noop":
        await ctx.ack()
        return True
    if data == "close":
        await ctx.ack()
        await ctx.delete()
        return True
    if data == "cancel":
        await ctx.state.clear()
        await ctx.ack()
        await ctx.delete()
        return True

    if head == "set":
        page = int(p[1])
        await ctx.edit(settings_header(uid), settings_kb(uid, page))
        return True

    # --- раздел с фильтрами
    if head == "s":
        key = p[1]
        meta = SECTIONS.get(key)
        if not meta:
            return False
        if not _premium_ok(uid, meta):
            await ctx.ack(LOCK_TEXT, True)
            return True
        await _show_section(ctx, key)
        return True

    if head == "sx":
        key, act = p[1], p[2]
        meta = SECTIONS[key]
        if not _premium_ok(uid, meta):
            await ctx.ack(LOCK_TEXT, True)
            return True
        s = db.get_settings(uid)
        if act == "toggle":
            s["sections"][key] = not sect_on(s, key)
            db.save_settings(uid, s)
            await _show_section(ctx, key)
        elif act in ("on", "off"):
            for f in s["filters"].get(key, []):
                f["enabled"] = (act == "on")
            db.save_settings(uid, s)
            await _show_section(ctx, key)
        elif act == "add":
            if len(s["filters"].get(key, [])) >= MAX_FILTERS:
                await ctx.ack(f"Максимум {MAX_FILTERS} штук в одном разделе.", True)
                return True
            await ctx.state.set_state("in:fadd")
            await ctx.state.update_data(key=key)
            await ctx.send(meta["add_prompt"], _cancel_kb())
        elif act == "help":
            await ctx.edit(f"<b>{meta['title']} — справка</b>\n\n{meta['help']}", KB([B("← Назад", f"s:{key}")]))
        elif act == "export":
            lines = []
            for f in s["filters"].get(key, []):
                lines.append(f"=== {f['name']} ===\n{f.get('items', '')}\n")
            body = "\n".join(lines) or "Товаров пока нет."
            await ctx.cb.message.answer_document(BufferedInputFile(body.encode("utf-8"), filename="products.txt"))
        return True

    if head == "f":
        await _show_filter(ctx, p[1], p[2])
        return True

    if head == "ft":
        key, fid, field = p[1], p[2], p[3]
        meta = SECTIONS[key]
        s = db.get_settings(uid)
        f, fd = _find(s, key, fid), _fd(meta, field)
        if f and fd:
            cur = fval(f, fd)
            if fd["t"] == "toggle":
                f[field] = not cur
            else:
                vals = [v for v, _l in fd["options"]]
                f[field] = vals[(vals.index(cur) + 1) % len(vals)] if cur in vals else vals[0]
            db.save_settings(uid, s)
        await _show_filter(ctx, key, fid)
        return True

    if head == "fe":
        key, fid, field = p[1], p[2], p[3]
        meta = SECTIONS[key]
        fd = _fd(meta, field)
        await ctx.state.set_state("in:fedit")
        await ctx.state.update_data(key=key, fid=fid, field=field)
        if fd["t"] == "int":
            hint = "Отправь число." + (f" 0 — {fd['zero'].lower()}." if fd.get("zero") else "")
        elif fd["k"] in ("kw", "kw_ex"):
            hint = "Отправь слова через запятую. Чтобы очистить, отправь «-»."
        else:
            hint = "Отправь новый текст. Чтобы очистить, отправь «-»."
        await ctx.send(f"{fd.get('icon', '✏️')} <b>{esc(fd['label'])}</b>\n\n{hint}", _cancel_kb())
        return True

    if head == "fn":
        await ctx.state.set_state("in:fren")
        await ctx.state.update_data(key=p[1], fid=p[2])
        await ctx.send("✏️ Отправь новое название.", _cancel_kb())
        return True

    if head == "fd":
        key, fid = p[1], p[2]
        s = db.get_settings(uid)
        f = _find(s, key, fid)
        name = esc(f["name"]) if f else ""
        await ctx.edit(f"🗑 Удалить «{name}»?", KB([B("✅ Да, удалить", f"fdc:{key}:{fid}"), B("❌ Нет", f"f:{key}:{fid}")]))
        return True

    if head == "fdc":
        key, fid = p[1], p[2]
        s = db.get_settings(uid)
        s["filters"][key] = [f for f in s["filters"].get(key, []) if f["id"] != fid]
        db.save_settings(uid, s)
        await _show_section(ctx, key)
        return True

    if head == "g":
        key, field = p[1], p[2]
        meta = SECTIONS[key]
        s = db.get_settings(uid)
        fd = _gd(meta, field)
        cur = gval(s, key, fd)
        s["glob"].setdefault(key, {})[field] = not cur
        db.save_settings(uid, s)
        await _show_section(ctx, key)
        return True

    if head == "ge":
        key, field = p[1], p[2]
        fd = _gd(SECTIONS[key], field)
        await ctx.state.set_state("in:gedit")
        await ctx.state.update_data(key=key, field=field)
        await ctx.send(f"⚙️ <b>{esc(fd['label'])}</b>\n\nОтправь число." + (f" 0 — {fd['zero'].lower()}." if fd.get("zero") else ""), _cancel_kb())
        return True

    # --- уведомления и переключатели
    if head == "nt":
        s = db.get_settings(uid)
        s["notifications"][p[1]] = not s["notifications"][p[1]]
        db.save_settings(uid, s)
        await ctx.edit(notif_text(), notif_kb(s))
        return True

    if head == "sw":
        s = db.get_settings(uid)
        s["switches"][p[1]] = not s["switches"][p[1]]
        db.save_settings(uid, s)
        await ctx.edit("🎛 <b>Переключатели</b>\n\nБыстрые включатели отдельных функций.", sw_kb(s))
        return True

    # --- автовыплата
    if head == "wd":
        s = db.get_settings(uid)
        if not db.is_premium(uid):
            await ctx.ack(LOCK_TEXT, True)
            return True
        s["withdraw"][p[1]] = not s["withdraw"][p[1]]
        db.save_settings(uid, s)
        await ctx.edit(wd_text(s), wd_kb(s))
        return True

    if head == "wde":
        if not db.is_premium(uid):
            await ctx.ack(LOCK_TEXT, True)
            return True
        field = p[1]
        labels = {"min": "Минимальная сумма вывода, ₽", "max": "Максимальная сумма вывода, ₽", "keep": "Сколько оставлять на балансе, ₽",
                  "max_rate": "Максимальный курс USDT (0 — без ограничения)", "cooldown": "Пауза между выплатами, сек",
                  "schedule": "Расписание, например 10:00-22:00 (или «-», чтобы убрать)"}
        await ctx.state.set_state("in:wd")
        await ctx.state.update_data(field=field)
        await ctx.send(f"💸 <b>{labels[field]}</b>\n\nОтправь значение.", _cancel_kb())
        return True

    if head == "wdm" and len(p) == 1:
        rows = [[B(v["label"], f"wdm:{k}")] for k, v in config.PAY_METHODS.items()]
        rows.append([B("← Назад", "m:wd")])
        await ctx.edit("✏️ <b>Выбери метод выплаты</b>", KB(*rows))
        return True

    if head == "wdm":
        await ctx.state.set_state("in:wdreq")
        await ctx.state.update_data(method=p[1])
        await ctx.send(f"✏️ Отправь реквизиты для метода «{_method_label(p[1])}».", _cancel_kb())
        return True

    # --- плагины
    if head == "pl":
        pid = p[1]
        pl = _plugin(pid)
        if not pl:
            return False
        if not db.is_premium(uid):
            await ctx.ack(LOCK_TEXT, True)
            return True
        await _show_plugin(ctx, pid)
        return True

    if head == "plt":
        pid = p[1]
        pl = _plugin(pid)
        en, conf = db.get_plugin(uid, pid)
        if en:
            db.set_plugin(uid, pid, enabled=False)
            await _show_plugin(ctx, pid)
            return True
        if not conf:
            await ctx.ack("Сначала зайди в мини-приложение и выбери товары.", True)
            await ctx.send(f"📱 Зайди в мини-приложение и настрой, на какие товары включить «{pl[2]}».\n\nПотом вернись сюда и нажми «Включить».",
                           KB([W("📱 Открыть мини-приложение", plugin=pid)]))
            return True
        db.set_plugin(uid, pid, enabled=True)
        await _show_plugin(ctx, pid)
        return True

    # --- чёрный список и чаты
    if head == "bl":
        s = db.get_settings(uid)
        if p[1] == "add":
            await ctx.state.set_state("in:bl")
            await ctx.send("⛔ Отправь ник пользователя или ссылку на его профиль.", _cancel_kb())
            return True
        if p[1] == "del":
            i = int(p[2])
            if 0 <= i < len(s["blacklist"]):
                s["blacklist"].pop(i)
        elif p[1] == "silent":
            s["blacklist_silent"] = not s["blacklist_silent"]
        db.save_settings(uid, s)
        await ctx.edit(_bl_text(s), bl_kb(s))
        return True

    if head == "ch":
        s = db.get_settings(uid)
        if p[1] == "add":
            await ctx.state.set_state("in:ch")
            await ctx.send("🔗 Отправь ID чата (бот и ты должны быть в нём админами).", _cancel_kb())
            return True
        if p[1] == "del":
            i = int(p[2])
            if 0 <= i < len(s["chats"]):
                s["chats"].pop(i)
        db.save_settings(uid, s)
        await ctx.edit(_ch_text(s), ch_kb(s))
        return True

    # --- меню верхнего уровня
    if head == "m":
        menu = p[1]
        s = db.get_settings(uid)
        if menu == "notif":
            await ctx.edit(notif_text(), notif_kb(s))
        elif menu == "sw":
            await ctx.edit("🎛 <b>Переключатели</b>\n\nБыстрые включатели отдельных функций.", sw_kb(s))
        elif menu == "wd":
            if not db.is_premium(uid):
                await ctx.ack(LOCK_TEXT, True)
                return True
            await ctx.edit(wd_text(s), wd_kb(s))
        elif menu == "plug":
            await ctx.edit("🧩 <b>Плагины</b>\n\nДополнительные функции. Каждую нужно один раз настроить в мини-приложении.", plug_kb(uid))
        elif menu == "bl":
            await ctx.edit(_bl_text(s), bl_kb(s))
        elif menu == "ch":
            await ctx.edit(_ch_text(s), ch_kb(s))
        elif menu == "ph":
            await ctx.ack("Раздел скоро появится.", True)
            return True
        elif menu == "reset":
            await ctx.edit("⚠️ <b>Сброс настроек</b>\n\nВсе настройки вернутся к начальным. Подтверждаешь?",
                           KB([B("✅ Да, сбросить", "reset_ok"), B("❌ Отмена", "set:1")]))
        elif menu == "exp":
            body = json.dumps(s, ensure_ascii=False, indent=2)
            await ctx.cb.message.answer_document(BufferedInputFile(body.encode("utf-8"), filename="settings.json"))
        elif menu == "imp":
            await ctx.state.set_state("in:import")
            await ctx.send("📥 Отправь файл settings.json, который ты раньше экспортировал.", _cancel_kb())
        else:
            return False
        return True

    if data == "reset_ok":
        db.reset_settings(uid)
        await ctx.ack("✅ Настройки сброшены", True)
        await ctx.edit(settings_header(uid), settings_kb(uid, 1))
        return True

    return False


def _bl_text(s):
    return f"⛔ <b>Чёрный список</b>\n\nВ списке: <b>{len(s['blacklist'])}</b>\nЗабаненным бот не отвечает и не выдаёт товары."


def _ch_text(s):
    return f"🔗 <b>Привязанные чаты</b>\n\nПривязано чатов: <b>{len(s['chats'])}</b>\nСюда бот будет присылать уведомления."


async def _show_plugin(ctx, pid):
    pl = _plugin(pid)
    en, conf = db.get_plugin(ctx.uid, pid)
    text = (f"{pl[1]} <b>{pl[2]}</b>\n\n{pl[3]}\n\n"
            f"Статус: {'🟢 включён' if en else '🔴 выключен'}\n"
            f"Настройка товаров: {'✅ готово' if conf else '⚠️ не настроено'}")
    rows = [[B(f"{'🔴 Выключить' if en else '🟢 Включить'} {pl[2].lower()}", f"plt:{pid}")],
            [W("📱 Настроить в мини-приложении", plugin=pid)],
            [B("← Назад", "m:plug")]]
    await ctx.edit(text, KB(*rows))


# ------------------------------------------------------------------ ввод текста (шаги диалога)
async def handle_input(message, state, st):
    """Обрабатывает ответ пользователя на вопрос бота. Возвращает True, если состояние наше."""
    uid = message.from_user.id
    text = (message.text or "").strip()
    data = await state.get_data()

    async def done():
        await state.clear()
        try:
            await message.delete()
        except Exception:
            pass

    if st == "in:import":
        doc = message.document
        if not doc:
            await reply(message, "Нужен файл settings.json.")
            return True
        if (doc.file_size or 0) > 200_000:
            await reply(message, "Файл слишком большой.")
            return True
        buf = await message.bot.download(doc)
        try:
            incoming = json.loads(buf.read().decode("utf-8"))
            assert isinstance(incoming, dict)
        except Exception:
            await reply(message, "❌ Не удалось прочитать файл.")
            return True
        s = db.get_settings(uid)
        for k in db.DEFAULT_SETTINGS:
            if k in incoming and type(incoming[k]) == type(db.DEFAULT_SETTINGS[k]):
                s[k] = incoming[k]
        db.save_settings(uid, s)
        await state.clear()
        await reply(message, "✅ Настройки импортированы.")
        return True

    if st not in ("in:fadd", "in:fren", "in:fedit", "in:gedit", "in:wd", "in:wdreq", "in:bl", "in:ch"):
        return False
    if not text:
        await reply(message, "Отправь текстом.")
        return True

    s = db.get_settings(uid)

    if st == "in:fadd":
        key = data["key"]
        meta = SECTIONS[key]
        name = text[:40].lower() if key == "reply" else text[:40]
        lst = s["filters"].setdefault(key, [])
        if len(lst) >= MAX_FILTERS:
            await done()
            await reply(message, f"Максимум {MAX_FILTERS} штук в одном разделе.")
            return True
        fid = secrets.token_hex(2)
        while any(f["id"] == fid for f in lst):
            fid = secrets.token_hex(2)
        lst.append({"id": fid, "name": name})
        db.save_settings(uid, s)
        await done()
        await reply(message, filter_text(meta, lst[-1]), filter_kb(key, meta, lst[-1]))
        return True

    if st == "in:fren":
        key, fid = data["key"], data["fid"]
        f = _find(s, key, fid)
        if f:
            f["name"] = text[:40]
            db.save_settings(uid, s)
        await done()
        if f:
            meta = SECTIONS[key]
            await reply(message, filter_text(meta, f), filter_kb(key, meta, f))
        return True

    if st == "in:fedit":
        key, fid, field = data["key"], data["fid"], data["field"]
        meta = SECTIONS[key]
        f, fd = _find(s, key, fid), _fd(meta, field)
        if not f or not fd:
            await done()
            return True
        if fd["t"] == "int":
            if not re.fullmatch(r"\d{1,9}", text) or int(text) > fd.get("max", 100000):
                await reply(message, f"Нужно целое число от 0 до {fd.get('max', 100000)}.")
                return True
            f[field] = int(text)
        else:
            f[field] = "" if text == "-" else text[:1000]
        db.save_settings(uid, s)
        await done()
        await reply(message, filter_text(meta, f), filter_kb(key, meta, f))
        return True

    if st == "in:gedit":
        key, field = data["key"], data["field"]
        if not re.fullmatch(r"\d{1,9}", text):
            await reply(message, "Нужно целое число.")
            return True
        s["glob"].setdefault(key, {})[field] = int(text)
        db.save_settings(uid, s)
        await done()
        await reply(message, section_text(s, key), section_kb(s, key))
        return True

    if st == "in:wd":
        field = data["field"]
        if field == "schedule":
            s["withdraw"]["schedule"] = "" if text == "-" else text[:40]
        else:
            if not re.fullmatch(r"\d{1,9}(\.\d+)?", text):
                await reply(message, "Нужно число.")
                return True
            val = float(text)
            s["withdraw"][field] = int(val) if field != "max_rate" else val
        db.save_settings(uid, s)
        await done()
        await reply(message, wd_text(s), wd_kb(s))
        return True

    if st == "in:wdreq":
        method = data["method"]
        s["withdraw"]["requisites"][method] = text[:200]
        s["withdraw"]["method"] = method
        db.save_settings(uid, s)
        await done()
        await reply(message, wd_text(s), wd_kb(s))
        return True

    if st == "in:bl":
        nick = text.replace("https://playerok.com/profile/", "").strip("/@ ")[:60]
        if nick and nick not in s["blacklist"] and len(s["blacklist"]) < 100:
            s["blacklist"].append(nick)
            db.save_settings(uid, s)
        await done()
        await reply(message, _bl_text(s), bl_kb(s))
        return True

    if st == "in:ch":
        if not re.fullmatch(r"-?\d{5,20}|@[A-Za-z0-9_]{4,32}", text):
            await reply(message, "Это не похоже на ID чата. Пример: -1001234567890")
            return True
        if text not in s["chats"] and len(s["chats"]) < 20:
            s["chats"].append(text)
            db.save_settings(uid, s)
        await done()
        await reply(message, _ch_text(s), ch_kb(s))
        return True

    return False
