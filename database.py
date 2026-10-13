"""База данных (SQLite). Всё хранится по Telegram ID, у каждого пользователя свои данные."""
import copy
import json
import random
import sqlite3
import time

import config

_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        try:
            _conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
    return _conn


def now():
    return int(time.time())


def _cols(table):
    return {r["name"] for r in conn().execute(f"PRAGMA table_info({table})")}


def _add_col(table, name, ddl):
    if name not in _cols(table):
        conn().execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


# ---------------------------------------------------------------- настройки по умолчанию
DEFAULT_SETTINGS = {
    "notifications": {
        "global": True, "new_order": True, "new_message": True, "new_review": True,
        "order_confirmed": True, "used_commands": True, "lot_restored": True,
        "system_msg": True, "out_of_stock": True, "new_problem": True, "support_refund": True,
    },
    "sections": {},   # key -> включён ли раздел целиком
    "filters": {},    # key -> список фильтров
    "glob": {},       # key -> общие параметры раздела
    "switches": {
        "quick_replies": False, "profit_calc": True, "relist": False,
        "relist_expired": False, "anon_read": False,
    },
    "withdraw": {
        "enabled": False, "notify": True, "min": 1000, "max": 10000, "keep": 0,
        "max_rate": 0, "cooldown": 30, "rounding": False, "schedule": "",
        "method": "", "requisites": {},
    },
    "blacklist": [],
    "blacklist_silent": True,
    "chats": [],
}

NOTIF_LABELS = [
    ("new_order", "Новый заказ"), ("new_message", "Новое сообщение"),
    ("new_review", "Новый отзыв"), ("order_confirmed", "Заказ подтверждён"),
    ("used_commands", "Исп. команды"), ("lot_restored", "Лот восстановлен"),
    ("system_msg", "Системные сообщ."), ("out_of_stock", "Товар закончился"),
    ("new_problem", "Новая проблема"), ("support_refund", "Возврат поддержкой"),
]


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


# ---------------------------------------------------------------- создание таблиц
def init_db():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance REAL DEFAULT 0.0,
        token TEXT DEFAULT NULL,
        is_admin INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS settings (user_id INTEGER PRIMARY KEY, data TEXT);
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, token TEXT, created INTEGER
    );
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, rub REAL, method TEXT, coin TEXT,
        pay_amount TEXT, address TEXT, status TEXT, created INTEGER, expires INTEGER
    );
    CREATE TABLE IF NOT EXISTS ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, amount REAL, note TEXT, created INTEGER
    );
    CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, discount INTEGER, created INTEGER);
    CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS plugin_state (
        user_id INTEGER, plugin TEXT, enabled INTEGER DEFAULT 0, configured INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, plugin)
    );
    """)
    # дополняем старую таблицу users (если она была создана прошлой версией)
    _add_col("users", "public_id", "INTEGER")
    _add_col("users", "premium_until", "INTEGER DEFAULT 0")
    _add_col("users", "ref_by", "INTEGER")
    _add_col("users", "ref_balance", "REAL DEFAULT 0")
    _add_col("users", "promo_code", "TEXT")
    _add_col("users", "promo_discount", "INTEGER DEFAULT 0")
    _add_col("users", "created", "INTEGER DEFAULT 0")
    _add_col("users", "banned", "INTEGER DEFAULT 0")
    _add_col("users", "admin_as_user", "INTEGER DEFAULT 0")
    for r in c.execute("SELECT user_id FROM users WHERE public_id IS NULL").fetchall():
        c.execute("UPDATE users SET public_id=? WHERE user_id=?", (_next_public_id(), r["user_id"]))
    c.commit()


def _next_public_id():
    row = conn().execute("SELECT MAX(public_id) AS m FROM users").fetchone()
    return max(row["m"] or 1000, 1000) + 1


# ---------------------------------------------------------------- пользователи
def get_user(uid):
    return conn().execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def ensure_user(uid, username, first_name, ref_by=None):
    """Возвращает (пользователь, новый_ли). Новому выдаётся уникальный номер."""
    c = conn()
    row = get_user(uid)
    if row:
        c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                  (username or "", first_name or "", uid))
        c.commit()
        return get_user(uid), False
    if ref_by and (ref_by == uid or not get_user(ref_by)):
        ref_by = None
    c.execute(
        "INSERT INTO users (user_id, username, first_name, public_id, ref_by, created) VALUES (?,?,?,?,?,?)",
        (uid, username or "", first_name or "", _next_public_id(), ref_by, now()),
    )
    c.commit()
    return get_user(uid), True


def find_user(token):
    """Ищет по @нику, Telegram ID или номеру в боте (до 6 цифр)."""
    t = str(token).strip()
    if t.startswith("@"):
        return conn().execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (t[1:],)).fetchone()
    if t.startswith("#"):
        t = t[1:]
    if t.isdigit():
        if len(t) <= 6:
            return conn().execute("SELECT * FROM users WHERE public_id=?", (int(t),)).fetchone()
        return get_user(int(t))
    return conn().execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (t,)).fetchone()


def is_admin(uid):
    return uid in config.ADMIN_IDS


def admin_view_as_user(uid):
    u = get_user(uid)
    return bool(u and u["admin_as_user"])


def set_admin_as_user(uid, flag):
    conn().execute("UPDATE users SET admin_as_user=? WHERE user_id=?", (1 if flag else 0, uid))
    conn().commit()


def is_premium(uid):
    if is_admin(uid) and not admin_view_as_user(uid):
        return True
    u = get_user(uid)
    return bool(u and (u["premium_until"] or 0) > now())


def premium_until(uid):
    u = get_user(uid)
    return (u["premium_until"] or 0) if u else 0


def add_premium_days(uid, days):
    u = get_user(uid)
    base = max(now(), (u["premium_until"] or 0))
    until = base + int(days) * 86400
    conn().execute("UPDATE users SET premium_until=? WHERE user_id=?", (until, uid))
    conn().commit()
    return until


def revoke_premium(uid):
    conn().execute("UPDATE users SET premium_until=0 WHERE user_id=?", (uid,))
    conn().commit()


def set_banned(uid, flag):
    conn().execute("UPDATE users SET banned=? WHERE user_id=?", (1 if flag else 0, uid))
    conn().commit()


def count_users():
    r = conn().execute("SELECT COUNT(*) AS n FROM users").fetchone()
    p = conn().execute("SELECT COUNT(*) AS n FROM users WHERE premium_until>?", (now(),)).fetchone()
    return r["n"], p["n"]


def recent_users(limit=10):
    return conn().execute("SELECT * FROM users ORDER BY created DESC, user_id DESC LIMIT ?", (limit,)).fetchall()


# ---------------------------------------------------------------- баланс и история
def add_ledger(uid, kind, amount, note=""):
    conn().execute("INSERT INTO ledger (user_id, kind, amount, note, created) VALUES (?,?,?,?,?)",
                   (uid, kind, amount, note, now()))
    conn().commit()


def change_balance(uid, delta, kind, note=""):
    conn().execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (delta, uid))
    conn().commit()
    add_ledger(uid, kind, delta, note)


def get_balance(uid):
    u = get_user(uid)
    return float(u["balance"] or 0) if u else 0.0


def transfer(from_uid, to_uid, amount):
    if amount <= 0 or get_balance(from_uid) < amount:
        return False
    change_balance(from_uid, -amount, "transfer_out", f"→ {to_uid}")
    change_balance(to_uid, amount, "transfer_in", f"← {from_uid}")
    return True


def list_ledger(uid, limit=10, kinds=None):
    rows = conn().execute("SELECT * FROM ledger WHERE user_id=? ORDER BY id DESC LIMIT 100", (uid,)).fetchall()
    if kinds:
        rows = [r for r in rows if r["kind"] in kinds]
    return rows[:limit]


# ---------------------------------------------------------------- партнёрка
def ref_stats(uid):
    n = conn().execute("SELECT COUNT(*) AS n FROM users WHERE ref_by=?", (uid,)).fetchone()["n"]
    e = conn().execute("SELECT COALESCE(SUM(amount),0) AS s FROM ledger WHERE user_id=? AND kind='ref'", (uid,)).fetchone()["s"]
    u = get_user(uid)
    return n, float(e), float(u["ref_balance"] or 0)


def add_ref_bonus(uid, amount, note=""):
    conn().execute("UPDATE users SET ref_balance = ref_balance + ? WHERE user_id=?", (amount, uid))
    conn().commit()
    add_ledger(uid, "ref", amount, note)


def move_ref_to_balance(uid):
    u = get_user(uid)
    amount = float(u["ref_balance"] or 0)
    if amount <= 0:
        return 0.0
    conn().execute("UPDATE users SET ref_balance=0 WHERE user_id=?", (uid,))
    conn().commit()
    change_balance(uid, amount, "ref_out", "Партнёрский баланс → основной")
    return amount


# ---------------------------------------------------------------- настройки пользователя
def get_settings(uid):
    row = conn().execute("SELECT data FROM settings WHERE user_id=?", (uid,)).fetchone()
    data = {}
    if row and row["data"]:
        try:
            data = json.loads(row["data"])
        except Exception:
            data = {}
    return _merge(copy.deepcopy(DEFAULT_SETTINGS), data)


def save_settings(uid, s):
    conn().execute("INSERT INTO settings (user_id, data) VALUES (?, ?) "
                   "ON CONFLICT(user_id) DO UPDATE SET data=excluded.data",
                   (uid, json.dumps(s, ensure_ascii=False)))
    conn().commit()


def reset_settings(uid):
    save_settings(uid, copy.deepcopy(DEFAULT_SETTINGS))


# ---------------------------------------------------------------- магазины (аккаунты Playerok)
def add_account(uid, name, token):
    cur = conn().execute("INSERT INTO accounts (user_id, name, token, created) VALUES (?,?,?,?)",
                         (uid, name, token, now()))
    conn().commit()
    return cur.lastrowid


def get_account_token(uid, acc_id):
    r = conn().execute("SELECT token FROM accounts WHERE id=? AND user_id=?", (acc_id, uid)).fetchone()
    return r["token"] if r else None


def list_accounts(uid):
    return conn().execute("SELECT id, name, created FROM accounts WHERE user_id=? ORDER BY id", (uid,)).fetchall()


def delete_account(uid, acc_id):
    conn().execute("DELETE FROM accounts WHERE id=? AND user_id=?", (acc_id, uid))
    conn().commit()


def account_limit(uid):
    return config.ACCOUNT_LIMIT_PREMIUM if is_premium(uid) else config.ACCOUNT_LIMIT_FREE


# ---------------------------------------------------------------- счета на пополнение
def pending_amounts(method):
    rows = conn().execute("SELECT pay_amount FROM invoices WHERE method=? AND status IN ('pending','review')",
                          (method,)).fetchall()
    return {r["pay_amount"] for r in rows}


def create_invoice(uid, rub, method, coin, pay_amount, address, ttl_min):
    t = now()
    cur = conn().execute(
        "INSERT INTO invoices (user_id, rub, method, coin, pay_amount, address, status, created, expires) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, rub, method, coin, pay_amount, address, "pending", t, t + ttl_min * 60))
    conn().commit()
    return cur.lastrowid


def get_invoice(inv_id):
    return conn().execute("SELECT * FROM invoices WHERE id=?", (inv_id,)).fetchone()


def invoice_status(inv):
    if inv["status"] == "pending" and inv["expires"] < now():
        return "expired"
    return inv["status"]


def set_invoice_status(inv_id, status):
    conn().execute("UPDATE invoices SET status=? WHERE id=?", (status, inv_id))
    conn().commit()


def list_invoices(uid, limit=8):
    return conn().execute("SELECT * FROM invoices WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()


def invoices_for_review(limit=15):
    return conn().execute(
        "SELECT * FROM invoices WHERE status IN ('review','pending') ORDER BY (status='review') DESC, id DESC LIMIT ?",
        (limit,)).fetchall()


def total_paid(uid):
    r = conn().execute("SELECT COALESCE(SUM(rub),0) AS s FROM invoices WHERE user_id=? AND status='paid'", (uid,)).fetchone()
    return float(r["s"])


def count_review():
    return conn().execute("SELECT COUNT(*) AS n FROM invoices WHERE status='review'").fetchone()["n"]


# ---------------------------------------------------------------- промокоды
def create_promo(code, discount):
    conn().execute("INSERT OR REPLACE INTO promos (code, discount, created) VALUES (?,?,?)",
                   (code.upper(), int(discount), now()))
    conn().commit()


def get_promo(code):
    return conn().execute("SELECT * FROM promos WHERE code=?", (code.upper(),)).fetchone()


def list_promos():
    return conn().execute("SELECT * FROM promos ORDER BY created DESC").fetchall()


def delete_promo(code):
    conn().execute("DELETE FROM promos WHERE code=?", (code.upper(),))
    conn().commit()


def set_user_promo(uid, code, discount):
    conn().execute("UPDATE users SET promo_code=?, promo_discount=? WHERE user_id=?", (code, discount, uid))
    conn().commit()


def clear_user_promo(uid):
    set_user_promo(uid, None, 0)


# ---------------------------------------------------------------- настройки приложения (реквизиты и т.д.)
def get_cfg(key, default=""):
    r = conn().execute("SELECT value FROM app_config WHERE key=?", (key,)).fetchone()
    return r["value"] if r and r["value"] is not None else default


def set_cfg(key, value):
    conn().execute("INSERT INTO app_config (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn().commit()


# ---------------------------------------------------------------- плагины
def get_plugin(uid, plugin):
    r = conn().execute("SELECT enabled, configured FROM plugin_state WHERE user_id=? AND plugin=?",
                       (uid, plugin)).fetchone()
    return (bool(r["enabled"]), bool(r["configured"])) if r else (False, False)


def set_plugin(uid, plugin, enabled=None, configured=None):
    cur_e, cur_c = get_plugin(uid, plugin)
    e = cur_e if enabled is None else enabled
    c = cur_c if configured is None else configured
    conn().execute(
        "INSERT INTO plugin_state (user_id, plugin, enabled, configured) VALUES (?,?,?,?) "
        "ON CONFLICT(user_id, plugin) DO UPDATE SET enabled=excluded.enabled, configured=excluded.configured",
        (uid, plugin, int(e), int(c)))
    conn().commit()


def unique_amount(method, base, decimals):
    """Сумма с «хвостом», чтобы отличать платежи разных людей."""
    taken = pending_amounts(method)
    for _ in range(200):
        if decimals >= 3:
            tail = random.randint(1, 99) / 1000.0
        else:
            tail = random.randint(1, 99) / 100.0
        s = f"{round(base, 2) + tail:.{decimals}f}"
        if s not in taken:
            return s
    return f"{base:.{decimals}f}"
