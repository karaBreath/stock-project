"""
News service — ดึงข่าวหุ้นจาก Google News RSS + Yahoo Finance
และทำ keyword-based sentiment (บวก/ลบ/กลาง) ให้แต่ละหัวข้อข่าว
"""
import urllib.parse
import datetime as dt

from config import Config
from database import cache_get, cache_set

try:
    import feedparser
    _FP_OK = True
except Exception:
    feedparser = None
    _FP_OK = False

try:
    import yfinance as yf
    _YF_OK = True
except Exception:
    yf = None
    _YF_OK = False


POSITIVE_WORDS = [
    "beat", "beats", "surge", "soar", "rally", "record", "upgrade", "growth",
    "profit", "gain", "rise", "jump", "strong", "bullish", "outperform", "buy",
    "กำไร", "พุ่ง", "บวก", "เพิ่ม", "โต", "แนะนำซื้อ", "ทำสถิติ", "แข็งแกร่ง",
]
NEGATIVE_WORDS = [
    "miss", "plunge", "drop", "fall", "crash", "downgrade", "loss", "weak",
    "bearish", "cut", "lawsuit", "fraud", "decline", "slump", "sell", "warning",
    "ขาดทุน", "ร่วง", "ลบ", "ลด", "หด", "เตือน", "ฟ้อง", "อ่อนแอ", "แนะนำขาย",
]


def _score_text(text: str) -> int:
    t = (text or "").lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    return pos - neg


def _label(score: int) -> str:
    if score > 0:
        return "positive"
    if score < 0:
        return "negative"
    return "neutral"


# Google News locale — (hl, gl, ceid)
LOCALE_TH = ("th", "TH", "TH:th")
LOCALE_EN = ("en-US", "US", "US:en")


def _locales_for(ticker: str, lang: str = "auto"):
    """
    เลือกภาษาข่าวให้เหมาะกับสิ่งที่ถือ
      - หุ้นไทย (.BK) -> ข่าวไทย + ข่าวอังกฤษ (หุ้นไทยก็โดนข่าวโลกกระทบ)
      - หุ้น/กองทุนสหรัฐ และอื่น ๆ -> ข่าวอังกฤษ (ทั่วโลก)
      - ไม่ระบุ ticker -> เอาทั้งสองภาษา
    บังคับได้ด้วย lang='th' | 'en' | 'both'
    """
    if lang == "th":
        return [LOCALE_TH]
    if lang == "en":
        return [LOCALE_EN]
    if lang == "both":
        return [LOCALE_TH, LOCALE_EN]

    t = (ticker or "").upper()
    if t.endswith(".BK"):
        return [LOCALE_TH, LOCALE_EN]
    if t:
        return [LOCALE_EN]          # AAPL, SPY, VOO, QQQ ... -> ข่าวอังกฤษ
    return [LOCALE_TH, LOCALE_EN]


def get_news(query: str = "", ticker: str = "", limit: int = 20, lang: str = "auto") -> dict:
    key_q = query or ticker or "หุ้น stock market"
    locales = _locales_for(ticker, lang)
    cache_key = f"news:{key_q}:{limit}:{'+'.join(l[2] for l in locales)}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    items = []
    seen = set()

    # ---- 1) Google News RSS (ดึงตามภาษาที่เหมาะกับหุ้นตัวนั้น) ----
    if _FP_OK:
        per_locale = max(1, limit // len(locales))
        for hl, gl, ceid in locales:
            try:
                q = urllib.parse.quote(key_q)
                url = (f"https://news.google.com/rss/search?q={q}"
                       f"&hl={hl}&gl={gl}&ceid={urllib.parse.quote(ceid)}")
                feed = feedparser.parse(url)
                for e in feed.entries[:per_locale]:
                    title = e.get("title", "")
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    src = e.get("source")
                    items.append({
                        "title": title,
                        "link": e.get("link"),
                        "source": (src or {}).get("title") if isinstance(src, dict) else "Google News",
                        "published": e.get("published", ""),
                        "lang": hl,
                        "sentiment": _label(_score_text(title)),
                    })
            except Exception:
                continue

    # ---- 2) Yahoo Finance news (ถ้าระบุ ticker) ----
    if ticker and _YF_OK and len(items) < limit:
        try:
            yn = yf.Ticker(ticker).news or []
            for n in yn[: limit - len(items)]:
                content = n.get("content", n)
                title = content.get("title") or n.get("title", "")
                link = (content.get("canonicalUrl", {}) or {}).get("url") or n.get("link")
                items.append({
                    "title": title,
                    "link": link,
                    "source": (content.get("provider", {}) or {}).get("displayName", "Yahoo Finance"),
                    "published": content.get("pubDate", ""),
                    "lang": "en-US",
                    "sentiment": _label(_score_text(title)),
                })
        except Exception:
            pass

    if not items:
        items = [{
            "title": "ยังดึงข่าวไม่ได้ — ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต หรือยังไม่ได้ติดตั้ง feedparser",
            "link": "#", "source": "system", "published": "", "sentiment": "neutral",
        }]

    pos = sum(1 for i in items if i["sentiment"] == "positive")
    neg = sum(1 for i in items if i["sentiment"] == "negative")
    result = {
        "query": key_q,
        "items": items[:limit],
        "locales": [l[2] for l in locales],
        "summary": {"positive": pos, "negative": neg, "neutral": len(items) - pos - neg},
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    cache_set(cache_key, result, Config.NEWS_CACHE_TTL)
    return result
