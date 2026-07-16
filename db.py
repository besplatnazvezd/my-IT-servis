import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "data/casino.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance_nm INTEGER DEFAULT 1000,
            balance_nmx INTEGER DEFAULT 0,
            daily_claimed TEXT,
            ref_code TEXT UNIQUE,
            ref_by INTEGER,
            total_donated INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referrer_id INTEGER,
            referred_id INTEGER PRIMARY KEY,
            bonus_given INTEGER DEFAULT 0,
            date TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            user_id INTEGER,
            achievement_name TEXT,
            unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, achievement_name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            details TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "last_name": row[3],
            "balance_nm": row[4],
            "balance_nmx": row[5],
            "daily_claimed": row[6],
            "ref_code": row[7],
            "ref_by": row[8],
            "total_donated": row[9],
            "total_won": row[10],
            "games_played": row[11],
            "created_at": row[12]
        }
    return None

def create_user(user_id, username, first_name, last_name, ref_code=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # generate unique ref code
    if ref_code is None:
        ref_code = str(user_id) + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))
    cur.execute("""
        INSERT INTO users (user_id, username, first_name, last_name, ref_code)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, first_name, last_name, ref_code))
    conn.commit()
    conn.close()
    return get_user(user_id)

def update_balance(user_id, currency, amount):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if currency == "nm":
        cur.execute("UPDATE users SET balance_nm = balance_nm + ? WHERE user_id = ?", (amount, user_id))
    elif currency == "nmx":
        cur.execute("UPDATE users SET balance_nmx = balance_nmx + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_balance(user_id):
    user = get_user(user_id)
    if user:
        return user["balance_nm"], user["balance_nmx"]
    return 0, 0

def set_daily_claimed(user_id, date_str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET daily_claimed = ? WHERE user_id = ?", (date_str, user_id))
    conn.commit()
    conn.close()

def add_referral(referrer_id, referred_id, bonus_nm=500):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id, bonus_given) VALUES (?, ?, ?)",
                (referrer_id, referred_id, bonus_nm))
    # если реферал уже есть, не добавляем бонус повторно
    if cur.rowcount > 0:
        # начисляем бонус рефереру
        update_balance(referrer_id, "nm", bonus_nm)
        cur.execute("UPDATE referrals SET bonus_given = ? WHERE referred_id = ?", (bonus_nm, referred_id))
        conn.commit()
    conn.close()

def add_achievement(user_id, ach_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO achievements (user_id, achievement_name) VALUES (?, ?)", (user_id, ach_name))
    conn.commit()
    conn.close()
    return cur.rowcount > 0

def get_achievements(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT achievement_name FROM achievements WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, balance_nm, balance_nmx FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows

def add_admin_log(admin_id, action, target_id=None, details=""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)",
                (admin_id, action, target_id, details))
    conn.commit()
    conn.close()

# инициализация при импорте
init_db()
