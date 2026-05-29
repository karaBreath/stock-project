"""
Central configuration for the Stock Analysis app.

ทุกค่า config รวมไว้ที่นี่ที่เดียว แก้ไขง่าย และอ่านค่าจาก environment variable ได้
เพื่อความปลอดภัย (เช่น token ต่าง ๆ ไม่ต้อง hardcode)
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # --- Flask ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))

    # --- Database ---
    DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "data" / "stock_app.db"))

    # --- Cache (วินาที) ---
    QUOTE_CACHE_TTL = int(os.environ.get("QUOTE_CACHE_TTL", "120"))      # ราคา realtime
    HISTORY_CACHE_TTL = int(os.environ.get("HISTORY_CACHE_TTL", "900"))  # กราฟย้อนหลัง
    NEWS_CACHE_TTL = int(os.environ.get("NEWS_CACHE_TTL", "600"))        # ข่าว
    MACRO_CACHE_TTL = int(os.environ.get("MACRO_CACHE_TTL", "1800"))     # มหภาค
    FUNDAMENTAL_CACHE_TTL = int(os.environ.get("FUNDAMENTAL_CACHE_TTL", "3600"))

    # --- LINE Notify / Messaging ---
    # LINE Notify ถูกปิดบริการแล้ว จึงรองรับ LINE Messaging API (push) แทน
    LINE_CHANNEL_TOKEN = os.environ.get("LINE_CHANNEL_TOKEN", "")
    LINE_USER_ID = os.environ.get("LINE_USER_ID", "")
    # เผื่อใครยังมี LINE Notify token เดิม ใช้ได้
    LINE_NOTIFY_TOKEN = os.environ.get("LINE_NOTIFY_TOKEN", "")

    # --- AI Advisory ---
    # ถ้าใส่ API key จะใช้ LLM จริง, ถ้าไม่ใส่จะใช้ rule-based engine ในเครื่อง
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    # --- ค่าตั้งต้น watchlist หุ้นที่ใช้แสดงตัวอย่าง ---
    DEFAULT_TH_TICKERS = [
        "PTT.BK", "AOT.BK", "CPALL.BK", "KBANK.BK", "SCB.BK",
        "ADVANC.BK", "DELTA.BK", "GULF.BK", "BDMS.BK", "SCC.BK",
    ]
    DEFAULT_US_TICKERS = [
        "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
        "TSLA", "META", "JPM", "XOM", "KO",
    ]

    # ตัวแทนข้อมูลมหภาค (ใช้สัญลักษณ์ของ Yahoo Finance)
    MACRO_SYMBOLS = {
        "gold": ("GC=F", "ทองคำ (USD/oz)"),
        "oil": ("CL=F", "น้ำมันดิบ WTI (USD)"),
        "usdthb": ("THB=X", "ดอลลาร์/บาท"),
        "us10y": ("^TNX", "บอนด์สหรัฐ 10 ปี (%)"),
        "sp500": ("^GSPC", "S&P 500"),
        "set": ("^SET.BK", "SET Index"),
        "dxy": ("DX-Y.NYB", "ดัชนีดอลลาร์ (DXY)"),
        "btc": ("BTC-USD", "Bitcoin"),
    }
