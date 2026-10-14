"""Работа с Playerok по токену аккаунта. Все запросы к сайту только здесь.

Библиотека: PlayerokAPI (pip install PlayerokAPI), автор th1ks.
Версия 0.2.0: Account(token=...), методы get_me, get_balance, aclose.
"""
import asyncio
import inspect
import logging
import re

log = logging.getLogger("playerok")


class PlayerokError(Exception):
    """Ошибка, которую можно показать пользователю."""


# Токен Playerok — это JWT: три части через точку, первая начинается с «eyJ».
_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")


def looks_like_token(text):
    return bool((text or "").strip() and _JWT.match((text or "").strip()))


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _new_account(token, proxy=None):
    try:
        from PlayerokAPI import Account
    except ImportError:
        raise PlayerokError("На сервере не установлена библиотека Playerok. Сообщи админу.")
    if proxy:
        return Account(token=token, proxy=proxy)
    return Account(token=token)


async def _close(acc):
    try:
        await _maybe_await(acc.aclose())
    except Exception:
        pass


def _name(me):
    for field in ("username", "name", "login"):
        val = getattr(me, field, None)
        if val:
            return str(val)
    if isinstance(me, dict):
        for field in ("username", "name"):
            if me.get(field):
                return str(me[field])
    return "аккаунт"


def _balance_value(bal):
    if isinstance(bal, (int, float)):
        return float(bal)
    for field in ("available", "value", "balance"):
        val = getattr(bal, field, None)
        if isinstance(val, (int, float)):
            return float(val)
    return None


async def check_token(token, proxy=None):
    """Проверяет токен. Возвращает имя аккаунта. При ошибке — PlayerokError."""
    token = (token or "").strip()
    if not looks_like_token(token):
        raise PlayerokError("Это не токен Playerok. Токен начинается с «eyJ» и состоит из трёх частей через точки. Кошелёк сюда не вставляй.")
    acc = _new_account(token, proxy)
    try:
        me = await _maybe_await(acc.get_me())
        return _name(me)
    except PlayerokError:
        raise
    except Exception as e:
        log.warning("токен не прошёл проверку: %s", e)
        raise PlayerokError("Токен не подошёл. Проверь, что скопировал его полностью, без пробелов.")
    finally:
        await _close(acc)


def _parse_date(value):
    """created_at может прийти строкой или datetime. Возвращает datetime с часовым поясом или None."""
    from datetime import datetime, timezone
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def _call(fn, *args, **kwargs):
    """Вызывает метод библиотеки: если он асинхронный — ждём, иначе выполняем в отдельном потоке."""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return await asyncio.to_thread(fn, *args, **kwargs)


async def fetch_stats(token, days, max_pages=40, proxy=None):
    """Статистика по сделкам. days=0 — за всё время.

    Продажи: сделки направления OUT со статусом PAID, SENT или CONFIRMED.
    Возвраты: сделки направления OUT со статусом ROLLED_BACK.
    Выручка: сумма транзакций продаж. Чистая сумма: выручка минус комиссия.
    """
    from datetime import datetime, timedelta, timezone
    from PlayerokAPI import ItemDealDirection, ItemDealStatus

    sold_statuses = {ItemDealStatus.PAID, ItemDealStatus.SENT, ItemDealStatus.CONFIRMED}
    since = None if not days else datetime.now(timezone.utc) - timedelta(days=days)

    acc = _new_account(token, proxy)
    try:
        me = await _call(acc.get_me)
        name = _name(me)
        balance = None
        try:
            balance = _balance_value(await _call(acc.get_balance))
        except Exception as e:
            log.warning("баланс не получен: %s", e)

        sales = refunds = 0
        revenue = fees = refund_sum = 0.0
        cursor = None
        for _ in range(max_pages):
            page = await _call(acc.deals.search, first=50, after=cursor)
            for d in page.items:
                if getattr(d, "direction", None) != ItemDealDirection.OUT:
                    continue
                created = _parse_date(getattr(d, "created_at", None))
                if since and (created is None or created < since):
                    continue
                tr = getattr(d, "transaction", None)
                value = float(getattr(tr, "value", 0) or 0) if tr else 0.0
                fee = float(getattr(tr, "fee", 0) or 0) if tr else 0.0
                if d.status in sold_statuses:
                    sales += 1
                    revenue += value
                    fees += fee
                elif d.status == ItemDealStatus.ROLLED_BACK:
                    refunds += 1
                    refund_sum += value
            if not page.has_next_page:
                break
            cursor = page.end_cursor

        return {"name": name, "balance": balance, "days": days,
                "sales": sales, "refunds": refunds,
                "revenue": revenue, "fees": fees, "net": revenue - fees,
                "refund_sum": refund_sum}
    except PlayerokError:
        raise
    except Exception as e:
        log.warning("не удалось получить статистику: %s", e)
        raise PlayerokError("Не удалось получить данные с Playerok. Попробуй позже.")
    finally:
        await _close(acc)
