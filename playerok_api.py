"""Работа с Playerok по токену аккаунта. Все запросы к сайту только здесь.

Библиотека: alleexxeeyy/PlayerokAPI (модуль playerokapi), ставится на сервер отдельно.
Вход: Account(cookies="token=...", user_agent=..., proxy=...).get()
"""
import asyncio
import inspect
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("playerok")

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")


class PlayerokError(Exception):
    """Ошибка, которую можно показать пользователю."""


_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
_JWT_FIND = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


def extract_token(text):
    m = _JWT_FIND.search(text or "")
    return m.group(0) if m else None


def looks_like_token(text):
    return bool(_JWT.match((text or "").strip()))


async def _call(fn, *args, **kwargs):
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return await asyncio.to_thread(fn, *args, **kwargs)


def _open(token, proxy=None):
    try:
        from playerokapi.account import Account
    except ImportError:
        raise PlayerokError("На сервере не установлена библиотека Playerok. Сообщи админу.")
    kwargs = {"cookies": f"token={token}", "user_agent": USER_AGENT}
    if proxy:
        kwargs["proxy"] = proxy.strip()
    return Account(**kwargs)


def _explain(e):
    """Переводит техническую ошибку в понятную фразу для пользователя."""
    text = f"{type(e).__name__}: {e}"
    if "BotCheck" in text or "ddg" in text.lower():
        return ("Playerok просит подтвердить, что вход делает не бот. Для этого нужна ещё одна cookie "
                "(__ddg5_), снятая с того же IP, что и прокси.")
    if "407" in text or "Proxy" in text or "proxy" in text.lower():
        return "Прокси не пускает: неверный логин или пароль, либо он закончился. Вставь новый в разделе «🛰 Прокси»."
    if "401" in text or "Unauthorized" in text or "Unauthenticated" in text.lower():
        return "Playerok не принял токен. Он устарел: возьми новый из свежей сессии."
    if "403" in text:
        return "Playerok закрыл доступ с этого адреса. Попробуй другой прокси."
    if "500" in text:
        return "Playerok отвечает ошибкой на этот запрос. Попробуй позже."
    return "Не удалось получить данные с Playerok. Попробуй позже."


def _name(acc):
    return str(getattr(acc, "username", None) or f"id {getattr(acc, 'id', '?')}")


def _balance(acc):
    try:
        return float(acc.profile.balance.available)
    except Exception:
        return None


async def check_token(token, proxy=None):
    token = (token or "").strip()
    if not looks_like_token(token):
        raise PlayerokError("Это не токен Playerok. Токен начинается с «eyJ» и состоит из трёх частей через точки.")
    try:
        acc = _open(token, proxy)
        acc = await _call(acc.get)
        return _name(acc)
    except PlayerokError:
        raise
    except Exception as e:
        log.warning("токен не прошёл проверку: %s", e)
        raise PlayerokError(_explain(e))


async def fetch_stats(token, days, max_pages=40, proxy=None):
    """Статистика по сделкам. days=0 — за всё время.

    Продажи: сделки направления OUT со статусом PAID, SENT, CONFIRMED или CONFIRMED_AUTOMATICALLY.
    Возвраты: сделки направления OUT со статусом ROLLED_BACK.
    """
    from playerokapi.enums import ItemDealDirections, ItemDealStatuses

    sold = {ItemDealStatuses.PAID, ItemDealStatuses.SENT, ItemDealStatuses.CONFIRMED,
            ItemDealStatuses.CONFIRMED_AUTOMATICALLY}
    since = None
    if days:
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        acc = _open(token, proxy)
        acc = await _call(acc.get)
        name = _name(acc)
        balance = _balance(acc)

        sales = refunds = 0
        revenue = fees = refund_sum = 0.0
        cursor = None
        for _ in range(max_pages):
            page = await _call(acc.get_deals, direction=ItemDealDirections.OUT, count=24, after_cursor=cursor)
            for d in page.deals:
                created = getattr(d, "created_at", None)
                if isinstance(created, str):
                    try:
                        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    except ValueError:
                        created = None
                if created is not None and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if since and (created is None or created < since):
                    continue
                tr = getattr(d, "transaction", None)
                value = float(getattr(tr, "value", 0) or 0) if tr else 0.0
                fee = float(getattr(tr, "fee", 0) or 0) if tr else 0.0
                if d.status in sold:
                    sales += 1
                    revenue += value
                    fees += fee
                elif d.status == ItemDealStatuses.ROLLED_BACK:
                    refunds += 1
                    refund_sum += value
            if not page.page_info.has_next_page:
                break
            cursor = page.page_info.end_cursor

        return {"name": name, "balance": balance, "days": days,
                "sales": sales, "refunds": refunds,
                "revenue": revenue, "fees": fees, "net": revenue - fees,
                "refund_sum": refund_sum}
    except PlayerokError:
        raise
    except Exception as e:
        log.warning("не удалось получить статистику: %s", e)
        raise PlayerokError(_explain(e))
    finally:
        pass
