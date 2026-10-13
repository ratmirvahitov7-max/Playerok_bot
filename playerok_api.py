"""Работа с Playerok по токену аккаунта. Все запросы к сайту только здесь.

Библиотека: PlayerokAPI (pip install PlayerokAPI), автор th1ks.
Версия 0.2.0: Account(token=...), методы get_me, get_balance, aclose.
"""
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


def _new_account(token):
    try:
        from PlayerokAPI import Account
    except ImportError:
        raise PlayerokError("На сервере не установлена библиотека Playerok. Сообщи админу.")
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


async def check_token(token):
    """Проверяет токен. Возвращает имя аккаунта. При ошибке — PlayerokError."""
    token = (token or "").strip()
    if not looks_like_token(token):
        raise PlayerokError("Это не токен Playerok. Токен начинается с «eyJ» и состоит из трёх частей через точки. Кошелёк сюда не вставляй.")
    acc = _new_account(token)
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


async def fetch_stats(token, days):
    """Сводка по аккаунту. Пока только баланс. Продажи добавим отдельно."""
    acc = _new_account(token)
    try:
        me = await _maybe_await(acc.get_me())
        balance = None
        try:
            balance = _balance_value(await _maybe_await(acc.get_balance()))
        except Exception as e:
            log.warning("баланс не получен: %s", e)
        return {"name": _name(me), "balance": balance,
                "revenue": None, "sales": None, "refunds": None, "days": days}
    except Exception as e:
        log.warning("не удалось получить статистику: %s", e)
        raise PlayerokError("Не удалось получить данные с Playerok. Попробуй позже.")
    finally:
        await _close(acc)
