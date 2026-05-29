"""
SQLite database layer.

ใช้ sqlite3 ของ Python ตรง ๆ (ไม่ต้องลง ORM) เพื่อความเบาและติดตั้งง่ายบน Windows
มีฟังก์ชัน helper สำหรับ query และสร้างตารางตอนเริ่มแอป
"""
import sqlite3
import json
import time
from pathlib import Path
from contextlib import contextmanager

from config import Config


def _ensure_parent(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    """คืน connection พร้อม row factory แบบ dict และปิดให้อัตโนมัติ"""
    _ensure_parent(Config.DB_PATH)
    conn = sqlite3.connect(Config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def query(sql, params=(), one=False):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def init_db():
    """สร้างตารางทั้งหมดถ้ายังไม่มี"""
    with get_conn() as conn:
        conn.executescript(
            """
            -- พอร์ตการลงทุน (หุ้นที่ถือ)
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                shares REAL NOT NULL,
                buy_price REAL NOT NULL,
                buy_date TEXT,
                note TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            -- รายการเฝ้าดู
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            -- การแจ้งเตือนราคา/สัญญาณ
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                condition TEXT NOT NULL,      -- 'above' | 'below' | 'rsi_above' | 'rsi_below'
                target REAL NOT NULL,
                note TEXT,
                active INTEGER DEFAULT 1,
                triggered_at REAL,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            -- cache ข้อมูลภายนอก (quote, history, news, ฯลฯ)
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                expires_at REAL NOT NULL
            );

            -- log การวิเคราะห์/แนะนำของ AI (ไว้ตรวจย้อนหลัง)
            CREATE TABLE IF NOT EXISTS advisory_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                answer TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            """
        )


# ----- cache helpers (เก็บใน SQLite ทำให้ข้ามการรีสตาร์ทได้) -----
def cache_get(key):
    row = query("SELECT payload, expires_at FROM cache WHERE key = ?", (key,), one=True)
    if not row:
        return None
    if row["expires_at"] < time.time():
        execute("DELETE FROM cache WHERE key = ?", (key,))
        return None
    try:
        return json.loads(row["payload"])
    except (ValueError, TypeError):
        return None


def cache_set(key, value, ttl):
    payload = json.dumps(value, default=str)
    execute(
        "INSERT INTO cache(key, payload, expires_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at",
        (key, payload, time.time() + ttl),
    )
