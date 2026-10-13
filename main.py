"""Точка входа. Профиль, платежи, подписка, магазины, статистика, админ-панель и сам запуск бота."""
import asyncio
import logging
import re

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiohttp import web

import config
import database as db
import sections
import ui
from ui import B, Ctx, KB, W, URL, dot, esc, fmt_date, reply, short, support_btn

log = logging.getLogger("bot")
router = Router()
_bot_username = None


async def bot_username(bot):
    global _bot_username
    if not _bot_username:
        _bot_username = (await bot.get_me()).username
    return _bot_username


async def notify_admins(bot, text, kb=None):
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            log.warning("не удалось написать админу %s: %s", admin_id, e)


# ====================================================================== /start и меню
def greeting(user):
    return (f"👋 Привет, <b>{esc(user['first_name'] or 'друг')}</b>!\n\n"
            f"🆔 Твой Telegram ID: <code>{user['user_id']}</code>\n"
            f"🔖 Твой номер в боте: <b>#{user['public_id']}</b>\n\n"
            f"Добро пожаловать в <b>{esc(config.BRAND)}</b>. Выбери раздел в меню ниже 👇")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    fu = message.from_user
    ref = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and re.fullmatch(r"r_\d{1,15}", parts[1].strip()):
        ref = int(parts[1].strip()[2:])
    user, new = db.ensure_user(fu.id, fu.username, fu.first_name, ref_by=ref)
    try:
        await message.delete()
    except Exception:
        pass
    await message.answer(greeting(user), reply_markup=ui.main_menu(fu.id), parse_mode="HTML")
    if new and user["ref_by"]:
        try:
            await message.bot.send_message(user["ref_by"], "👥 По твоей партнёрской ссылке зарегистрировался новый пользователь!")
        except Exception:
            pass


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer("Главное меню 👇", reply_markup=ui.main_menu(message.from_user.id))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=ui.main_menu(message.from_user.id))


@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Твой Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


@router.message(Command("testorder"))
async def cmd_testorder(message: Message):
    if not db.is_admin(message.from_user.id):
        return
    order_id = "1f1c582d"
    text = ("🟢 <b>Новый заказ!</b> (демо)\n\n👤 Покупатель: Покупатель123\n💰 Сумма: 990 ₽\n"
            f"🆔 ID: {order_id}")
    kb = KB([URL("📦 Заказ", f"https://playerok.com/orders/{order_id}"), B("💸 Возврат", "ord:demo"), B("✅ Выполнил", "ord:demo")])
    await reply(message, text, kb)


@router.message(Command("dev_configure"))
async def cmd_dev_configure(message: Message):
    """Только для админа: пометить плагин как «настроенный» (пока нет связи с мини-приложением)."""
    if not db.is_admin(message.from_user.id):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Пример: /dev_configure dump")
        return
    db.set_plugin(message.from_user.id, parts[1], configured=True)
    await message.answer(f"Плагин {esc(parts[1])} помечен как настроенный.", parse_mode="HTML")


# ====================================================================== профиль
def profile_text(uid):
    u = db.get_user(uid)
    prem = db.is_premium(uid)
    until = db.premium_until(uid)
    lines = ["🙋 <b>Мой профиль</b>", "",
             f"🆔 Твой ID: <code>{uid}</code>",
             f"🔖 Номер в боте: <b>#{u['public_id']}</b>"]
    if prem and db.is_admin(uid) and not until:
        lines.append("💎 Подписка: Есть (админ)")
    elif prem:
        lines += ["💎 Подписка: Есть", f"⏳ Заканчивается: {fmt_date(until)}"]
    else:
        lines.append("💎 Подписка: Отсутствует")
    lines += ["", "💰 <b>Статистика</b>",
              f"Баланс: {float(u['balance'] or 0):.2f} RUB",
              f"Всего пополнений: {db.total_paid(uid):.1f} RUB",
              f"Подключено магазинов: {len(db.list_accounts(uid))} / {db.account_limit(uid)}"]
    return "\n".join(lines)


def profile_kb():
    return KB(
        [B("💳 Пополнить", "p:topup"), B("💎 Подписка", "p:sub")],
        [B("🤝 Партнёрка", "p:ref")],
        [B("🔁 Перевод баланса", "p:tr")],
        [B("🧾 Мои счета", "p:inv"), B("📣 Мои посты", "p:posts")],
        [B("🎁 Промокод", "p:promo")],
    )


async def h_profile(message: Message):
    await reply(message, profile_text(message.from_user.id), profile_kb())


# ====================================================================== пополнение и счета
STATUS_ICON = {"paid": "✅", "pending": "⏳", "review": "⏳", "rejected": "❌", "expired": "❌"}
STATUS_TEXT = {"paid": "оплачен", "pending": "ждём оплату", "review": "на проверке", "rejected": "отклонён", "expired": "время вышло"}


def invoice_text(inv):
    st = db.invoice_status(inv)
    m = config.PAY_METHODS.get(inv["method"], {})
    lines = [f"🧾 <b>Счёт #{inv['id']}</b>", "",
             f"Способ: {esc(m.get('label', inv['method']))}",
             f"Зачислим: <b>{inv['rub']:.0f} ₽</b>",
             f"Сумма к оплате: <code>{esc(inv['pay_amount'])}</code> {esc(inv['coin'])}",
             f"Адрес: <code>{esc(inv['address'])}</code>", "",
             f"Статус: {STATUS_ICON.get(st, '')} {STATUS_TEXT.get(st, st)}"]
    if st == "pending":
        left = max(0, inv["expires"] - db.now()) // 60
        lines += ["", "⚠️ Отправь <b>ровно</b> эту сумму, включая дробную часть.", f"⏳ Счёт действует ещё {left} мин."]
    return "\n".join(lines)


def invoice_kb(inv):
    st = db.invoice_status(inv)
    rows = []
    if st == "pending":
        rows.append([B("✅ Я оплатил", f"p:paid:{inv['id']}")])
        rows.append([B("🔄 Обновить статус", f"p:i:{inv['id']}")])
    elif st in ("expired", "rejected", "review"):
        rows.append([support_btn("💬 Написать в поддержку")])
    rows.append([B("← К счетам", "p:inv")])
    return KB(*rows)


async def credit_invoice(bot, inv):
    """Зачисляет деньги по счёту (один раз), начисляет партнёрский бонус."""
    if inv["status"] == "paid":
        return False
    db.set_invoice_status(inv["id"], "paid")
    db.change_balance(inv["user_id"], inv["rub"], "topup", f"Счёт #{inv['id']}")
    u = db.get_user(inv["user_id"])
    if u and u["ref_by"]:
        bonus = round(inv["rub"] * config.REF_PERCENT / 100, 2)
        db.add_ref_bonus(u["ref_by"], bonus, f"{config.REF_PERCENT}% от пополнения #{u['public_id']}")
        try:
            await bot.send_message(u["ref_by"], f"🤝 Партнёрский бонус: +{bonus:.2f} ₽", parse_mode="HTML")
        except Exception:
            pass
    try:
        await bot.send_message(inv["user_id"], f"✅ Баланс пополнен на <b>{inv['rub']:.0f} ₽</b>.", parse_mode="HTML")
    except Exception:
        pass
    return True


async def make_invoice(ctx, rub, method_id):
    m = config.PAY_METHODS[method_id]
    addr = db.get_cfg("addr_" + method_id, "")
    if not addr:
        await ctx.ack("Этот способ пока недоступен. Напиши в поддержку.", True)
        return
    if m["fiat"]:
        pay = db.unique_amount(method_id, float(rub), 2)
    else:
        rate = float(db.get_cfg("rate_usdt", config.DEFAULT_USDT_RATE))
        pay = db.unique_amount(method_id, rub / rate, 3)
    inv_id = db.create_invoice(ctx.uid, rub, method_id, m["coin"], pay, addr, config.INVOICE_TTL_MIN)
    inv = db.get_invoice(inv_id)
    await ctx.edit(invoice_text(inv), invoice_kb(inv))


# ====================================================================== подписка
PLAN_FEATURES = ("• Автоподъём лотов\n• Автовосстановление товаров\n• Автодоставка товаров из списка\n• Мультимагазин\n"
                 "• Уведомления\n• Автовыплата\n• Автоответы и команды\n• Ответ на подтверждение заказа и на проблему\n"
                 "• Чёрный список\n• Подробная статистика в мини-приложении")


def plan_price(uid, idx):
    days, price, name = config.PLANS[idx]
    u = db.get_user(uid)
    disc = int(u["promo_discount"] or 0)
    final = int(round(price * (100 - disc) / 100)) if disc else price
    return days, price, final, name, disc


def sub_kb(uid):
    rows = [[B("💰 Пополнить баланс", "p:topup")]]
    for i, (_d, price, name) in enumerate(config.PLANS):
        _d, _p, final, name, disc = plan_price(uid, i)
        label = f"{name} | {final}₽" + (f" (−{disc}%)" if disc else "")
        rows.append([B(label, f"p:buy:{i}")])
    rows.append([B("← Назад", "p:prof")])
    return KB(*rows)


# ====================================================================== магазины
def shops_view(uid):
    acc = db.list_accounts(uid)
    lim = db.account_limit(uid)
    if acc:
        lines = [f"🏪 <b>Всего магазинов: {len(acc)} / {lim}</b>", ""]
        lines += [f"🟢 <b>{esc(a['name'])}</b>" for a in acc]
    else:
        lines = ["🏪 <b>Всего магазинов: 0</b>", "", "Пока нет подключённых магазинов."]
    rows = [[B("➕ Добавить магазин", "a:add")]]
    for a in acc:
        rows.append([B(f"🗑 Удалить «{short(a['name'], 25)}»", f"a:del:{a['id']}")])
    return "\n".join(lines), KB(*rows)


async def h_shops(message: Message):
    text, kb = shops_view(message.from_user.id)
    await reply(message, text, kb)


async def h_stats(message: Message):
    uid = message.from_user.id
    if not db.list_accounts(uid):
        await reply(message, "⚠️ <b>Доступ закрыт</b>\n\nСначала подключи магазин, чтобы смотреть статистику.",
                    KB([B("🔌 Подключить магазин", "a:add")]))
        return
    text = ("📈 <b>Статистика</b>\n\n📅 <b>За сегодня:</b>\n💸 Заработано: 0 ₽\n🛒 Успешных сделок: 0\n\n"
            "<i>Подробная аналитика — в мини-приложении.</i>")
    await reply(message, text, KB([W("📱 Открыть подробную статистику", tab="stats")]))


async def h_soon(message: Message):
    await reply(message, "🛠 Этот раздел скоро появится.")


async def h_settings(message: Message):
    uid = message.from_user.id
    await reply(message, sections.settings_header(uid), sections.settings_kb(uid, 1))


async def h_payments(message: Message):
    uid = message.from_user.id
    rows = db.list_ledger(uid, 10)
    names = {"topup": "Пополнение", "sub": "Подписка", "transfer_out": "Перевод", "transfer_in": "Получен перевод",
             "ref": "Партнёрка", "ref_out": "Вывод партнёрки"}
    if rows:
        lines = ["💱 <b>Последние операции</b>", ""]
        for r in rows:
            lines.append(f"{fmt_date(r['created'])} · {names.get(r['kind'], r['kind'])}: <b>{r['amount']:+.2f} ₽</b>")
    else:
        lines = ["💱 <b>Платежи</b>", "", "Операций пока нет."]
    await reply(message, "\n".join(lines), KB([B("💳 Пополнить", "p:topup"), B("🧾 Мои счета", "p:inv")]))


# ====================================================================== админ-панель
def admin_text():
    users, prem = db.count_users()
    return (f"👑 <b>Админ-панель</b>\n\n👥 Пользователей: <b>{users}</b>\n💎 С подпиской: <b>{prem}</b>\n"
            f"🧾 Счетов на проверке: <b>{db.count_review()}</b>")


def admin_kb(uid):
    as_user = db.admin_view_as_user(uid)
    return KB(
        [B("🎁 Выдать подписку", "adm:grant"), B("🚫 Забрать подписку", "adm:revoke")],
        [B(f"🧾 Счета на проверку ({db.count_review()})", "adm:rev")],
        [B("🎟 Промокоды", "adm:promos"), B("💳 Реквизиты оплаты", "adm:cfg")],
        [B("👥 Пользователи", "adm:users")],
        [B(f"🙈 Режим пользователя: {'ВКЛ' if as_user else 'ВЫКЛ'}", "adm:view")],
    )


async def h_admin(message: Message):
    uid = message.from_user.id
    if not db.is_admin(uid):
        return
    await reply(message, admin_text(), admin_kb(uid))


MENU_MAP = {
    ui.BTN_SETTINGS: h_settings, ui.BTN_STATS: h_stats, ui.BTN_SHOPS: h_shops, ui.BTN_PROFILE: h_profile,
    ui.BTN_PROXY: h_soon, ui.BTN_CHATS: h_soon, ui.BTN_ORDERS: h_soon, ui.BTN_GOODS: h_soon,
    ui.BTN_PAYMENTS: h_payments, ui.BTN_ADMIN: h_admin,
}

CFG_LABELS = {
    "addr_usdt_trc20": "Адрес USDT (TRC20)", "addr_usdt_bep20": "Адрес USDT (BEP20)", "addr_card": "Карта или телефон (СБП)",
    "rate_usdt": "Курс USDT в рублях", "support": "Ник поддержки (без @)",
}


# ====================================================================== нажатия кнопок
async def handle_main_callback(ctx: Ctx):
    data = ctx.cb.data or ""
    uid = ctx.uid
    p = data.split(":")
    head = p[0]
    bot = ctx.cb.message.bot if getattr(ctx.cb.message, "bot", None) else None

    if head == "ord":
        await ctx.ack("Это демонстрационный заказ.", True)
        return True

    # ---------------- профиль
    if head == "p":
        act = p[1]
        if act == "prof":
            await ctx.edit(profile_text(uid), profile_kb())
        elif act == "posts":
            await ctx.ack("Раздел скоро появится.", True)
        elif act == "topup":
            await ctx.state.set_state("in:topup")
            await ctx.send(f"💳 <b>Отправь сумму пополнения</b>\n\nДиапазон: {config.TOPUP_MIN} – {config.TOPUP_MAX} ₽",
                           KB([B("🚫 Отмена", "cancel")]))
        elif act == "m":
            await make_invoice(ctx, int(p[3]), p[2])
        elif act == "sub":
            text = ("👑 <b>Оформи подписку и пользуйся всеми возможностями бота!</b>\n\n"
                    "💡 <b>Что входит:</b>\n" + PLAN_FEATURES)
            await ctx.edit(text, sub_kb(uid))
        elif act == "buy":
            await buy_plan(ctx, int(p[2]))
        elif act == "ref":
            n, earned, bal = db.ref_stats(uid)
            uname = await bot_username(ctx.cb.message.bot)
            text = (f"🤝 <b>Партнёрская программа</b>\n\nПриглашай друзей и получай <b>{config.REF_PERCENT}%</b> с каждого их пополнения.\n\n"
                    f"🔗 Твоя ссылка:\nhttps://t.me/{uname}?start=r_{uid}\n\n"
                    f"👥 Приглашено: <b>{n}</b>\n💰 Заработано: <b>{earned:.2f} ₽</b>\n🏦 Доступно к переводу: <b>{bal:.2f} ₽</b>")
            await ctx.edit(text, KB([B("📜 История начислений", "p:refhist")], [B("🔁 Перевести на баланс", "p:refmove")], [B("← Назад", "p:prof")]))
        elif act == "refhist":
            rows = db.list_ledger(uid, 10, kinds=("ref", "ref_out"))
            text = "📜 <b>История начислений</b>\n\n" + ("\n".join(f"{fmt_date(r['created'])} · {r['amount']:+.2f} ₽" for r in rows) or "Пока пусто.")
            await ctx.edit(text, KB([B("← Назад", "p:ref")]))
        elif act == "refmove":
            moved = db.move_ref_to_balance(uid)
            if moved <= 0:
                await ctx.ack("На партнёрском балансе пока ничего нет.", True)
            else:
                await ctx.ack(f"✅ Переведено {moved:.2f} ₽ на основной баланс.", True)
                await ctx.edit(profile_text(uid), profile_kb())
        elif act == "tr":
            await ctx.state.set_state("in:tr_target")
            await ctx.send("🔁 Отправь @ник, ID или номер (#) пользователя, которому хочешь перевести баланс.", KB([B("🚫 Отмена", "cancel")]))
        elif act == "trok":
            to, amount = int(p[2]), float(p[3])
            if db.transfer(uid, to, amount):
                await ctx.ack("✅ Перевод выполнен.", True)
                await ctx.edit(f"✅ Переведено <b>{amount:.2f} ₽</b>.", KB([B("← В профиль", "p:prof")]))
                try:
                    await ctx.cb.message.bot.send_message(to, f"💸 Тебе перевели <b>{amount:.2f} ₽</b>.", parse_mode="HTML")
                except Exception:
                    pass
            else:
                await ctx.ack("Недостаточно средств.", True)
        elif act == "inv":
            invs = db.list_invoices(uid)
            rows = [[B(f"{STATUS_ICON.get(db.invoice_status(i), '')} #{i['id']} | {i['rub']:.0f}₽", f"p:i:{i['id']}")] for i in invs]
            rows.append([B("💳 Пополнить", "p:topup")])
            rows.append([B("← Назад", "p:prof")])
            await ctx.edit(f"🧾 <b>Твои счета</b>\n\nВсего: {len(invs)}", KB(*rows))
        elif act == "i":
            inv = db.get_invoice(int(p[2]))
            if not inv or inv["user_id"] != uid:
                await ctx.ack("Счёт не найден.", True)
            else:
                await ctx.edit(invoice_text(inv), invoice_kb(inv))
        elif act == "paid":
            inv = db.get_invoice(int(p[2]))
            if not inv or inv["user_id"] != uid:
                await ctx.ack("Счёт не найден.", True)
                return True
            st = db.invoice_status(inv)
            if st == "review":
                await ctx.ack("Платёж уже проверяется.", True)
            elif st != "pending":
                await ctx.ack("Счёт закрыт или просрочен. Если ты уже оплатил, напиши в поддержку.", True)
                await ctx.edit(invoice_text(inv), invoice_kb(inv))
            else:
                db.set_invoice_status(inv["id"], "review")
                await ctx.ack("✅ Заявка отправлена. Проверим платёж в ближайшее время.", True)
                inv = db.get_invoice(inv["id"])
                await ctx.edit(invoice_text(inv), invoice_kb(inv))
                u = db.get_user(uid)
                await notify_admins(ctx.cb.message.bot,
                                    f"🧾 <b>Новая оплата на проверку</b>\n\nСчёт #{inv['id']} · {inv['rub']:.0f} ₽\n"
                                    f"Сумма: <code>{esc(inv['pay_amount'])}</code> {esc(inv['coin'])}\n"
                                    f"Пользователь: {esc(u['first_name'])} (ID {uid}, #{u['public_id']})",
                                    KB([B("✅ Подтвердить", f"adm:ok:{inv['id']}"), B("❌ Отклонить", f"adm:no:{inv['id']}")]))
        elif act == "promo":
            await ctx.state.set_state("in:promo")
            await ctx.send("🎁 Введи промокод:", KB([B("🚫 Отмена", "cancel")]))
        else:
            return False
        return True

    # ---------------- магазины
    if head == "a":
        act = p[1]
        if act == "add":
            if len(db.list_accounts(uid)) >= db.account_limit(uid):
                await ctx.ack("Лимит магазинов исчерпан. Оформи подписку, чтобы подключить больше.", True)
                return True
            await ctx.state.set_state("in:token")
            await ctx.send("🔑 Отправь токен аккаунта Playerok. Сообщение с токеном бот сразу удалит.", KB([B("🚫 Отмена", "cancel")]))
        elif act == "del":
            await ctx.edit("🗑 Удалить магазин?", KB([B("✅ Да", f"a:delc:{p[2]}"), B("❌ Нет", "a:list")]))
        elif act == "delc":
            db.delete_account(uid, int(p[2]))
            text, kb = shops_view(uid)
            await ctx.edit(text, kb)
        elif act == "list":
            text, kb = shops_view(uid)
            await ctx.edit(text, kb)
        else:
            return False
        return True

    # ---------------- админ
    if head == "adm":
        if not db.is_admin(uid):
            await ctx.ack("Нет доступа.", True)
            return True
        act = p[1]
        if act == "home":
            await ctx.edit(admin_text(), admin_kb(uid))
        elif act in ("grant", "revoke"):
            await ctx.state.set_state("in:adm_grant")
            await ctx.state.update_data(mode=act)
            hint = "ID (или @ник, или номер #) и количество дней через пробел, например:\n<code>123456789 30</code>" if act == "grant" else "ID, @ник или номер (#) пользователя."
            await ctx.send(("🎁 Выдать" if act == "grant" else "🚫 Забрать") + " подписку.\n\nОтправь " + hint, KB([B("🚫 Отмена", "cancel")]))
        elif act == "rev":
            invs = db.invoices_for_review()
            if not invs:
                await ctx.edit("🧾 Счетов на проверку нет.", KB([B("← Назад", "adm:home")]))
            else:
                rows = [[B(f"{'🟡' if i['status'] == 'review' else '⏳'} #{i['id']} · {i['rub']:.0f}₽ · ID {i['user_id']}", f"adm:inv:{i['id']}")] for i in invs]
                rows.append([B("← Назад", "adm:home")])
                await ctx.edit("🧾 <b>Счета на проверку</b>\n\n🟡 — человек нажал «Я оплатил»\n⏳ — ещё ждём", KB(*rows))
        elif act == "inv":
            inv = db.get_invoice(int(p[2]))
            if not inv:
                await ctx.ack("Счёт не найден.", True)
            else:
                await ctx.edit(invoice_text(inv) + f"\n\nПользователь: ID {inv['user_id']}",
                               KB([B("✅ Подтвердить", f"adm:ok:{inv['id']}"), B("❌ Отклонить", f"adm:no:{inv['id']}")], [B("← Назад", "adm:rev")]))
        elif act == "ok":
            inv = db.get_invoice(int(p[2]))
            if not inv:
                await ctx.ack("Счёт не найден.", True)
            elif await credit_invoice(ctx.cb.message.bot, inv):
                await ctx.ack("✅ Зачислено.", True)
                await ctx.edit(f"✅ Счёт #{inv['id']} подтверждён, {inv['rub']:.0f} ₽ зачислено.", KB([B("← К админ-панели", "adm:home")]))
            else:
                await ctx.ack("Этот счёт уже зачислен.", True)
        elif act == "no":
            inv = db.get_invoice(int(p[2]))
            if inv and inv["status"] != "paid":
                db.set_invoice_status(inv["id"], "rejected")
                try:
                    await ctx.cb.message.bot.send_message(inv["user_id"], f"❌ Платёж по счёту #{inv['id']} не подтверждён. Напиши в поддержку.", parse_mode="HTML")
                except Exception:
                    pass
                await ctx.edit(f"❌ Счёт #{inv['id']} отклонён.", KB([B("← К админ-панели", "adm:home")]))
            else:
                await ctx.ack("Нельзя отклонить.", True)
        elif act == "promos":
            promos = db.list_promos()
            rows = [[B(f"🗑 {pr['code']} · −{pr['discount']}%", f"adm:pdel:{pr['code']}")] for pr in promos]
            rows.append([B("➕ Создать промокод", "adm:pnew")])
            rows.append([B("← Назад", "adm:home")])
            await ctx.edit(f"🎟 <b>Промокоды</b>\n\nВсего: {len(promos)}. Нажми на промокод, чтобы удалить.", KB(*rows))
        elif act == "pnew":
            await ctx.state.set_state("in:adm_promo")
            await ctx.send("🎟 Отправь промокод и скидку в процентах через пробел, например:\n<code>START 20</code>", KB([B("🚫 Отмена", "cancel")]))
        elif act == "pdel":
            db.delete_promo(p[2])
            await ctx.ack("Удалено.")
            promos = db.list_promos()
            rows = [[B(f"🗑 {pr['code']} · −{pr['discount']}%", f"adm:pdel:{pr['code']}")] for pr in promos]
            rows.append([B("➕ Создать промокод", "adm:pnew")])
            rows.append([B("← Назад", "adm:home")])
            await ctx.edit(f"🎟 <b>Промокоды</b>\n\nВсего: {len(promos)}.", KB(*rows))
        elif act == "cfg" and len(p) == 2:
            lines = ["💳 <b>Реквизиты оплаты</b>", ""]
            rows = []
            for k, lab in CFG_LABELS.items():
                val = db.get_cfg(k, str(config.DEFAULT_USDT_RATE) if k == "rate_usdt" else "")
                lines.append(f"• {lab}: " + (f"<code>{esc(short(val, 50))}</code>" if val else "не задано"))
                rows.append([B(f"✏️ {lab}", f"adm:cfg:{k}")])
            rows.append([B("← Назад", "adm:home")])
            await ctx.edit("\n".join(lines), KB(*rows))
        elif act == "cfg":
            key = p[2]
            if key not in CFG_LABELS:
                return False
            await ctx.state.set_state("in:adm_cfg")
            await ctx.state.update_data(key=key)
            await ctx.send(f"✏️ <b>{CFG_LABELS[key]}</b>\n\nОтправь новое значение. Чтобы очистить, отправь «-».", KB([B("🚫 Отмена", "cancel")]))
        elif act == "users":
            lines = ["👥 <b>Последние пользователи</b>", ""]
            for u in db.recent_users(10):
                prem = "💎" if (u["premium_until"] or 0) > db.now() else "—"
                nick = f"@{u['username']}" if u["username"] else "без ника"
                lines.append(f"#{u['public_id']} · {esc(u['first_name'])} · {esc(nick)} · <code>{u['user_id']}</code> · {prem}")
            await ctx.edit("\n".join(lines), KB([B("← Назад", "adm:home")]))
        elif act == "view":
            db.set_admin_as_user(uid, not db.admin_view_as_user(uid))
            await ctx.edit(admin_text(), admin_kb(uid))
        else:
            return False
        return True

    return False


async def buy_plan(ctx, idx):
    uid = ctx.uid
    if not 0 <= idx < len(config.PLANS):
        await ctx.ack("Тариф не найден.", True)
        return
    days, _price, final, name, disc = plan_price(uid, idx)
    if db.get_balance(uid) < final:
        await ctx.ack(f"Недостаточно средств. Нужно {final} ₽, на балансе {db.get_balance(uid):.0f} ₽.", True)
        return
    db.change_balance(uid, -final, "sub", f"Подписка {name}")
    db.add_premium_days(uid, days)
    if disc:
        db.clear_user_promo(uid)
    await ctx.ack()
    await ctx.edit(f"🥳 <b>Подписка приобретена!</b>\n\nПериод: {name}\nМагазинов: до {config.ACCOUNT_LIMIT_PREMIUM}\nСписано: {final} ₽",
                   KB([B("➕ Добавить магазин", "a:add")], [B("🙋 Открыть профиль", "p:prof")]))


# ====================================================================== ввод текста (шаги диалога)
async def handle_input(message: Message, state: FSMContext, st: str):
    uid = message.from_user.id
    text = (message.text or "").strip()

    async def done(delete=True):
        await state.clear()
        if delete:
            try:
                await message.delete()
            except Exception:
                pass

    if st == "in:topup":
        if not re.fullmatch(r"\d{1,6}([.,]\d{1,2})?", text):
            await reply(message, "Нужно число, например 299.")
            return True
        rub = int(round(float(text.replace(",", "."))))
        if not config.TOPUP_MIN <= rub <= config.TOPUP_MAX:
            await reply(message, f"Сумма должна быть от {config.TOPUP_MIN} до {config.TOPUP_MAX} ₽.")
            return True
        await state.clear()
        rows = [[B(v["label"], f"p:m:{k}:{rub}")] for k, v in config.PAY_METHODS.items()]
        rows.append([B("← Назад", "p:prof")])
        await reply(message, f"💳 <b>Выбери способ пополнения</b>\n\nСумма: {rub} ₽", KB(*rows))
        return True

    if st == "in:promo":
        pr = db.get_promo(text)
        await done()
        if pr:
            db.set_user_promo(uid, pr["code"], pr["discount"])
            await reply(message, f"✅ Промокод применён: скидка <b>{pr['discount']}%</b> на следующую подписку.")
        else:
            await reply(message, "❌ Такого промокода нет.")
        return True

    if st == "in:token":
        await done()
        if len(text) < 10 or len(text) > 2000:
            await reply(message, "❌ Это не похоже на токен.")
            return True
        if len(db.list_accounts(uid)) >= db.account_limit(uid):
            await reply(message, "Лимит магазинов исчерпан.")
            return True
        n = len(db.list_accounts(uid)) + 1
        db.add_account(uid, f"Магазин {n}", text)
        await reply(message, "✅ <b>Магазин подключён.</b> Токен сохранён, сообщение с ним удалено.", KB([B("🏪 Мои магазины", "a:list")]))
        return True

    if st == "in:tr_target":
        target = db.find_user(text)
        if not target or target["user_id"] == uid:
            await reply(message, "Пользователь не найден. Он должен хотя бы раз запустить бота. Попробуй ещё раз.")
            return True
        await state.set_state("in:tr_amount")
        await state.update_data(to=target["user_id"])
        await reply(message, f"Сколько перевести пользователю <b>#{target['public_id']}</b>? Твой баланс: {db.get_balance(uid):.2f} ₽")
        return True

    if st == "in:tr_amount":
        data = await state.get_data()
        if not re.fullmatch(r"\d{1,7}([.,]\d{1,2})?", text):
            await reply(message, "Нужно число.")
            return True
        amount = float(text.replace(",", "."))
        if amount <= 0 or amount > db.get_balance(uid):
            await reply(message, "Недостаточно средств или неверная сумма.")
            return True
        await state.clear()
        await reply(message, f"Перевести <b>{amount:.2f} ₽</b> пользователю <code>{data['to']}</code>?",
                    KB([B("✅ Да", f"p:trok:{data['to']}:{amount}"), B("❌ Отмена", "cancel")]))
        return True

    # ---- админ
    if st in ("in:adm_grant", "in:adm_promo", "in:adm_cfg"):
        if not db.is_admin(uid):
            await state.clear()
            return True
        data = await state.get_data()
        if st == "in:adm_grant":
            parts = text.split()
            target = db.find_user(parts[0]) if parts else None
            if not target:
                await reply(message, "Пользователь не найден. Он должен хотя бы раз запустить бота. Попробуй ещё раз.")
                return True
            if data["mode"] == "grant":
                days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
                db.add_premium_days(target["user_id"], days)
                await done()
                await reply(message, f"✅ Подписка на {days} дн. выдана пользователю #{target['public_id']}.")
                try:
                    await message.bot.send_message(target["user_id"], f"🎁 Тебе выдана подписка на {days} дн.", parse_mode="HTML")
                except Exception:
                    pass
            else:
                db.revoke_premium(target["user_id"])
                await done()
                await reply(message, f"🚫 Подписка у пользователя #{target['public_id']} снята.")
            return True
        if st == "in:adm_promo":
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 100:
                await reply(message, "Формат: КОД СКИДКА, например START 20")
                return True
            db.create_promo(parts[0], int(parts[1]))
            await done()
            await reply(message, f"✅ Промокод <b>{esc(parts[0].upper())}</b> на {int(parts[1])}% создан.")
            return True
        if st == "in:adm_cfg":
            key = data["key"]
            val = "" if text == "-" else text.strip()
            if key == "support":
                val = val.lstrip("@")
            if key == "rate_usdt" and val and not re.fullmatch(r"\d+(\.\d+)?", val):
                await reply(message, "Нужно число, например 92.5")
                return True
            db.set_cfg(key, val)
            await done()
            await reply(message, "✅ Сохранено.", KB([B("💳 Реквизиты оплаты", "adm:cfg")]))
            return True
    return False


# ====================================================================== главные обработчики
@router.message()
async def on_message(message: Message, state: FSMContext):
    fu = message.from_user
    if fu is None:
        return
    user, _ = db.ensure_user(fu.id, fu.username, fu.first_name)
    if user["banned"]:
        return
    text = (message.text or "").strip()
    if text in MENU_MAP:
        await state.clear()
        await MENU_MAP[text](message)
        return
    if text.startswith("/"):
        return
    st = await state.get_state()
    if st:
        if await sections.handle_input(message, state, st):
            return
        if await handle_input(message, state, st):
            return
        await state.clear()
    await message.answer("Выбери раздел в меню ниже 👇", reply_markup=ui.main_menu(fu.id))


@router.callback_query()
async def on_callback(cb: CallbackQuery, state: FSMContext):
    fu = cb.from_user
    user, _ = db.ensure_user(fu.id, fu.username, fu.first_name)
    if user["banned"]:
        await cb.answer()
        return
    ctx = Ctx(cb, state)
    try:
        handled = await sections.handle_callback(ctx)
        if not handled:
            handled = await handle_main_callback(ctx)
    except Exception:
        log.exception("ошибка в обработчике кнопки %s", cb.data)
        await ctx.ack("Что-то пошло не так. Попробуй ещё раз.", True)
        return
    if not handled:
        await ctx.ack("Функция в разработке")
    await ctx.ack()


# ====================================================================== запуск
async def handle_ping(request):
    return web.Response(text="Bot is running!")


async def main():
    logging.basicConfig(level=logging.INFO)
    if not config.BOT_TOKEN:
        raise SystemExit("Не задан BOT_TOKEN (переменная окружения).")
    db.init_db()
    global bot
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


bot = None

if __name__ == "__main__":
    asyncio.run(main())
