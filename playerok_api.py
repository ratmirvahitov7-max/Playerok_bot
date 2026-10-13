"""Работа с Playerok по токену аккаунта. Все запросы к сайту только здесь.

Библиотека: PlayerokAPI с PyPI (pip install PlayerokAPI). Ставится на сервер отдельно.
Если её нет, бот всё равно запускается, а при подключении пишет понятную ошибку.
"""
import asyncio
import logging
import re

log = logging.getLogger("playerok")

_UNUSED_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")


class PlayerokError(Exception):
    """Ошибка, которую можно показать пользователю."""


# Токен Playerok — это JWT: три части через точку, первая начинается с «eyJ».
_JWT = re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")


def looks_like_token(text):
    return bool(_JWT.match((text or "").strip()))


def _account(token):
    """Вход по токену: как в примере библиотеки, токен передаётся внутри cookies."""
    try:
        from playerokapi.account import Account
    except ImportError:
        raise PlayerokError("На сервере не установлена библиотека Playerok. Сообщи админу.")
    return Account(cookies=f"token={token}", user_agent=USER_AGENT).get()


def _name(acc):
    return str(getattr(acc, "username", None) or f"id {getattr(acc, 'id', '?')}")


def _balance(acc):
    try:
        return float(acc.profile.balance.available)
    except Exception:
        return None


async def check_token(token):
    """Проверяет токен. Возвращает имя аккаунта. При ошибке — PlayerokError."""
    token = (token or "").strip()
    if not looks_like_token(token):
        raise PlayerokError("Это не токен Playerok. Токен начинается с «eyJ» и состоит из трёх частей через точки. Кошелёк сюда не вставляй.")
    try:
        acc = await asyncio.to_thread(_account, token)
    except PlayerokError:
        raise
    except Exception as e:
        log.warning("токен не прошёл проверку: %s", e)
        raise PlayerokError("Токен не подошёл. Проверь, что скопировал его полностью, без пробелов.")
    return _name(acc)


async def fetch_stats(token, days):
    """Сводка по аккаунту. days=0 — за всё время.

    Пока возвращаем только то, что точно есть в библиотеке.
    Выручку и продажи добавим, когда найдём метод сделок в документации
    (playerokapi.readthedocs.io) и проверим его на твоём аккаунте.
    """
    try:
        acc = await asyncio.to_thread(_account, token)
    except PlayerokError:
        raise
    except Exception as e:
        log.warning("не удалось получить статистику: %s", e)
        raise PlayerokError("Не удалось получить данные с Playerok. Попробуй позже.")
    return {"name": _name(acc), "balance": _balance(acc),
            "revenue": None, "sales": None, "refunds": None, "days": days}
