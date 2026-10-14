"""Настройки бота. Всё важное можно менять здесь или через переменные окружения (на Render: Environment)."""
import os


def _ids(raw):
    out = set()
    for part in str(raw).replace(" ", "").split(","):
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


# --- Обязательное ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Telegram ID админов через запятую. По умолчанию твой ID из старого main.py.
ADMIN_IDS = _ids(os.getenv("ADMIN_IDS", "8158413794"))

# --- Хранилище ---
DB_PATH = os.getenv("DB_PATH", "bot_database.db")

# --- Мини-приложение (ссылка https://..., без слэша на конце) ---
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")

# --- Инструкция, как получить токен (ссылка на Telegraph) ---
TOKEN_GUIDE_URL = os.getenv("TOKEN_GUIDE_URL", "")

# --- Прокси: ссылка на покупку (сюда вставь свою реферальную) ---
PROXY_SHOP_URL = os.getenv("PROXY_SHOP_URL", "")

# --- Оформление ---
BRAND = os.getenv("BRAND", "Playerok Helper")
PORT = int(os.getenv("PORT", "8080"))

# --- Подписка: (дней, цена в рублях, название) ---
PLANS = [
    (7, 279, "7 дней"),
    (30, 650, "30 дней"),
    (180, 1890, "6 месяцев"),
]
ACCOUNT_LIMIT_FREE = 1
ACCOUNT_LIMIT_PREMIUM = 5

# --- Пополнение ---
TOPUP_MIN = 10
TOPUP_MAX = 15000
INVOICE_TTL_MIN = 30
DEFAULT_USDT_RATE = 90.0  # рублей за 1 USDT (меняется в админ-панели)

# --- Партнёрка ---
REF_PERCENT = 20

# Способы пополнения. Адреса задаются в админ-панели бота (Реквизиты оплаты).
PAY_METHODS = {
    "usdt_trc20": {"label": "USDT (TRC20)", "coin": "USDT", "fiat": False},
    "usdt_bep20": {"label": "USDT (BEP20)", "coin": "USDT", "fiat": False},
    "card": {"label": "Карта / СБП", "coin": "₽", "fiat": True},
}
