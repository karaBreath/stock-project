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
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    HOST = "0.0.0.0"
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
    # กองทุน/ETF ยอดนิยม (ใช้ได้เหมือนหุ้นทุกฟีเจอร์ — ราคา กราฟ เทคนิคัล เครื่องเรียนรู้)
    DEFAULT_FUND_TICKERS = [
        "SPY",  # S&P 500
        "QQQ",  # Nasdaq 100
        "VOO",  # Vanguard S&P 500
        "VTI",  # หุ้นสหรัฐทั้งตลาด
        "VT",   # หุ้นทั่วโลก
        "VWO",  # ตลาดเกิดใหม่
        "GLD",  # ทองคำ
        "TLT",  # พันธบัตรสหรัฐระยะยาว
    ]

    # --- สะพานเชื่อมระบบเทรด MT5 ที่บ้าน (volume-edge) ---
    # ตั้ง 2 ค่านี้แล้วเมนู "พอร์ต MT5" จะดึงไม้จริง/สัญญาณ/สถิติมาแสดง
    # ไม่ตั้ง = ปิดฟีเจอร์เงียบ ๆ · ดึงเฉพาะคำสั่งอ่าน สั่งซื้อขายข้ามระบบไม่ได้
    VE_BASE_URL = os.environ.get("VE_BASE_URL", "").strip()
    VE_AUTH_KEY = os.environ.get("VE_AUTH_KEY", "").strip()

    # --- GDELT (ข่าวทั่วโลก 65 ภาษา · ฟรี ไม่ต้องใช้ API key) ---
    GDELT_BASE = os.environ.get("GDELT_BASE", "https://api.gdeltproject.org/api/v2")
    GDELT_TIMEOUT = int(os.environ.get("GDELT_TIMEOUT", "35"))
    # ใช้ตอนที่ผู้ใช้นั่งรอหน้าเว็บอยู่ — ยอมได้ข้อมูลไม่ครบ ดีกว่าให้รอนาน
    GDELT_TIMEOUT_FAST = int(os.environ.get("GDELT_TIMEOUT_FAST", "10"))
    # จุดบนลูกโลก: ตั้งยาวกว่ารอบเก็บข้อมูลเบื้องหลัง เพื่อให้ cache อุ่นเสมอ
    GDELT_CACHE_TTL = int(os.environ.get("GDELT_CACHE_TTL", "5400"))
    GDELT_TIMELINE_CACHE_TTL = int(os.environ.get("GDELT_TIMELINE_CACHE_TTL", "3600"))
    GDELT_MAX_POINTS = int(os.environ.get("GDELT_MAX_POINTS", "350"))

    # ธีมข่าวโลกที่ใช้เป็น "สัญญาณ" ป้อนเข้าเครื่องเรียนรู้
    # key -> (ชื่อไทย, GDELT query, สีบนลูกโลก)
    WORLD_THEMES = {
        "conflict": ("สงคราม/ความขัดแย้ง",
                     '(war OR conflict OR airstrike OR invasion OR ceasefire)', "#ff4d6d"),
        "energy":   ("พลังงาน/น้ำมัน",
                     '(oil price OR crude oil OR OPEC OR natural gas OR refinery)', "#ffa94d"),
        "inflation": ("เงินเฟ้อ/ดอกเบี้ย",
                      '(inflation OR interest rate OR central bank OR "Federal Reserve")', "#ffd43b"),
        "trade":    ("การค้า/ภาษี",
                     '(tariff OR trade war OR export ban OR sanctions OR supply chain)', "#74c0fc"),
        "tech":     ("เทคโนโลยี/ชิป",
                     '(semiconductor OR "artificial intelligence" OR chip export OR data center)', "#b197fc"),
        "market":   ("ตลาดหุ้นโลก",
                     '(stock market OR equities OR "bear market" OR "bull market" OR selloff)', "#63e6be"),
        "disaster": ("ภัยพิบัติ/โรคระบาด",
                     '(earthquake OR flood OR hurricane OR outbreak OR pandemic)', "#e599f7"),
        "earnings": ("ผลประกอบการ",
                     '(earnings beat OR earnings miss OR quarterly results OR guidance cut '
                     'OR profit warning)', "#ff922b"),
        "thailand": ("ข่าวไทย",
                     '("Thailand economy" OR "Thai baht" OR "Thai stocks" OR Bangkok)', "#4dd4ff"),
    }

    # คำค้นสำหรับลูกโลก — วัดจริงแล้ว GDELT ArtList รับได้เฉพาะรูปแบบนี้:
    #   คำเดียว + maxrecords=50   -> ผ่าน 4/5 ครั้ง
    #   คำค้นที่มี OR หลายคำ       -> โดนปฏิเสธ 0/6 ครั้ง (ไม่มีทางสำเร็จ)
    #   maxrecords 5/100/250/ไม่ระบุ -> โดนปฏิเสธทุกครั้ง
    # จึงยิงทีละคำ วนไปเรื่อย ๆ แล้วสะสมข่าวไว้ในคลังร่วม (ดู gdelt.world_snapshot)
    WORLD_FETCH_WORDS = tuple(w.strip() for w in os.environ.get(
        "WORLD_FETCH_WORDS",
        "economy,market,inflation,energy,war,chip,tariff,earthquake,Thailand,"
        "earnings,oil,flood"
    ).split(",") if w.strip())
    # คำที่ยิงไปหมายถึงธีมไหน — ใช้เป็นตัวช่วยเมื่อพาดหัวไม่มีคำที่แยกธีมได้
    # (วัดจริง: ข่าว 149 ชิ้นแยกธีมจากพาดหัวได้แค่ 24 ชิ้น อีก 125 ชิ้นถูกทิ้ง
    #  ทั้งที่เรารู้อยู่แล้วว่าไปค้นมาด้วยคำอะไร — ข้อมูลนี้ใช้ได้และซื่อสัตย์)
    WORLD_WORD_THEME = {
        "economy": "market", "market": "market", "inflation": "inflation",
        "energy": "energy", "oil": "energy", "war": "conflict",
        "chip": "tech", "tariff": "trade", "earthquake": "disaster",
        "flood": "disaster", "thailand": "thailand", "earnings": "earnings",
    }
    WORLD_MAXRECORDS = int(os.environ.get("WORLD_MAXRECORDS", "50"))
    WORLD_POOL_HOURS = int(os.environ.get("WORLD_POOL_HOURS", "36"))   # อายุข่าวในคลัง
    WORLD_POOL_MAX = int(os.environ.get("WORLD_POOL_MAX", "600"))      # เก็บสูงสุดกี่ข่าว

    # คำที่ใช้แยกธีมจากพาดหัวข่าว (ตัวเล็กทั้งหมด · ตรงกับ query ของแต่ละธีม)
    WORLD_THEME_KEYWORDS = {
        "conflict": ("war", "conflict", "airstrike", "invasion", "ceasefire",
                     "military", "troops", "missile", "strike", "attack"),
        "energy":   ("oil", "crude", "opec", "natural gas", "refinery",
                     "petrol", "gasoline", "barrel", "pipeline"),
        "inflation": ("inflation", "interest rate", "central bank", "federal reserve",
                      "cpi", "rate cut", "rate hike", "monetary"),
        "trade":    ("tariff", "trade war", "export ban", "sanction", "supply chain",
                     "import", "export", "customs"),
        "tech":     ("semiconductor", "artificial intelligence", " ai ", "chip",
                     "data center", "nvidia", "software", "cloud"),
        "market":   ("stock market", "equities", "bear market", "bull market",
                     "selloff", "shares", "index", "wall street", "nasdaq", "s&p"),
        "disaster": ("earthquake", "flood", "hurricane", "outbreak", "pandemic",
                     "typhoon", "wildfire", "drought", "virus"),
        "earnings": ("earnings", "quarterly results", "guidance", "profit warning",
                     "revenue", "forecast cut", "beats estimates"),
        "thailand": ("thailand", "thai ", "baht", "bangkok", "set index"),
    }

    # --- Learning engine (เก็บข้อมูลสะสม → หาความสัมพันธ์ข่าว ↔ ราคา) ---
    LEARN_AUTO = os.environ.get("LEARN_AUTO", "1") == "1"          # เก็บ snapshot อัตโนมัติ
    LEARN_INTERVAL = int(os.environ.get("LEARN_INTERVAL", "3600"))  # ทุกกี่วินาที
    # GDELT ให้ต่อ 1 คำขอได้สูงสุด ~90 วัน (ยาวกว่านี้ตอบ 429 "query too large")
    # แต่แอปแบ่งยิงทีละช่วงแล้วเก็บสะสมเอง จึงเรียนรู้จากช่วงที่ยาวกว่านั้นได้
    LEARN_WINDOW_DAYS = int(os.environ.get("LEARN_WINDOW_DAYS", "365"))
    # ความยาวที่ตัวเก็บข้อมูลเบื้องหลังจะทยอยดึงย้อนหลังมาเก็บไว้
    LEARN_BACKFILL_DAYS = int(os.environ.get("LEARN_BACKFILL_DAYS", "540"))
    LEARN_MIN_SAMPLES = int(os.environ.get("LEARN_MIN_SAMPLES", "30"))  # n ขั้นต่ำถึงจะเชื่อ
    LEARN_LAGS = [0, 1, 2, 3, 5]   # feature วันนี้ → ผลตอบแทนอีกกี่วัน

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
        # --- ตัวชี้วัดสำคัญสำหรับหุ้น/กองทุนสหรัฐ ---
        "vix": ("^VIX", "VIX ดัชนีความกลัว"),
        "nasdaq": ("^IXIC", "Nasdaq Composite"),
        "semis": ("SOXX", "ดัชนีเซมิคอนดักเตอร์"),
        "us2y": ("^FVX", "บอนด์สหรัฐ 5 ปี (%)"),
    }

    # ตัวชี้วัดที่แสดงเด่นในหน้าแรก แยกตามตลาดที่ดู
    MACRO_FOCUS = {
        "th": ["set", "usdthb", "gold", "oil", "us10y", "sp500"],
        "us": ["sp500", "nasdaq", "vix", "us10y", "dxy", "semis"],
    }
