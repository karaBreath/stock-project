"""
Stock data service — ดึงราคา/งบ/ประวัติจาก Yahoo Finance ผ่าน yfinance

- รองรับหุ้นไทย (เติม .BK) และหุ้นสหรัฐ
- มี cache ใน SQLite ลด rate-limit ของ Yahoo
- ทุกฟังก์ชันคืนค่าเป็น dict/list ที่ jsonify ได้เลย และมี fallback เมื่อ network ล้ม
"""
import math
import datetime as dt

import pandas as pd

from config import Config
from database import cache_get, cache_set

try:
    import yfinance as yf
    _YF_OK = True
except Exception:  # pragma: no cover - ถ้ายังไม่ได้ลง yfinance
    yf = None
    _YF_OK = False


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------
def normalize_ticker(ticker: str) -> str:
    """ทำความสะอาด ticker; ตัวเลขล้วน (เช่น 7203) ถือว่าเป็นหุ้นไทย -> เติม .BK"""
    t = (ticker or "").strip().upper()
    if not t:
        return t
    # ถ้าเป็นรหัสหุ้นไทยที่พิมพ์มาเฉย ๆ และไม่มี suffix ให้ผู้ใช้เติม .BK เอง
    return t


def _safe(v):
    """แปลงค่า NaN/inf เป็น None เพื่อให้ jsonify ได้"""
    if v is None:
        return None
    if isinstance(v, (int,)):
        return v
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return v


def is_thai(ticker: str) -> bool:
    return ticker.upper().endswith(".BK")


# ---------------------------------------------------------------------------
# quote (ราคา + ข้อมูลย่อ)
# ---------------------------------------------------------------------------
def get_quote(ticker: str) -> dict:
    ticker = normalize_ticker(ticker)
    cache_key = f"quote:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    result = {
        "ticker": ticker,
        "currency": "THB" if is_thai(ticker) else "USD",
        "ok": False,
    }

    if not _YF_OK:
        result["error"] = "ยังไม่ได้ติดตั้ง yfinance (pip install -r requirements.txt)"
        return result

    try:
        tk = yf.Ticker(ticker)
        info = {}
        try:
            info = tk.info or {}
        except Exception:
            info = {}

        # ใช้ fast_info เป็นแหล่งราคาหลัก (เร็วกว่าและเสถียรกว่า)
        price = prev = None
        try:
            fi = tk.fast_info
            price = fi.get("last_price") if hasattr(fi, "get") else getattr(fi, "last_price", None)
            prev = fi.get("previous_close") if hasattr(fi, "get") else getattr(fi, "previous_close", None)
        except Exception:
            pass

        if price is None:
            price = info.get("currentPrice") or info.get("regularMarketPrice")
        if prev is None:
            prev = info.get("previousClose") or info.get("regularMarketPreviousClose")

        price = _safe(price)
        prev = _safe(prev)
        change = (price - prev) if (price is not None and prev is not None) else None
        change_pct = (change / prev * 100) if (change is not None and prev) else None

        result.update({
            "ok": price is not None,
            "name": info.get("shortName") or info.get("longName") or ticker,
            "price": price,
            "previous_close": prev,
            "change": _safe(change),
            "change_pct": _safe(change_pct),
            "currency": info.get("currency") or result["currency"],
            "market_cap": _safe(info.get("marketCap")),
            "pe": _safe(info.get("trailingPE")),
            "forward_pe": _safe(info.get("forwardPE")),
            "pb": _safe(info.get("priceToBook")),
            "eps": _safe(info.get("trailingEps")),
            "dividend_yield": _safe(info.get("dividendYield")),
            "roe": _safe(info.get("returnOnEquity")),
            "debt_to_equity": _safe(info.get("debtToEquity")),
            "profit_margin": _safe(info.get("profitMargins")),
            "revenue_growth": _safe(info.get("revenueGrowth")),
            "beta": _safe(info.get("beta")),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "fifty_two_high": _safe(info.get("fiftyTwoWeekHigh")),
            "fifty_two_low": _safe(info.get("fiftyTwoWeekLow")),
            "volume": _safe(info.get("volume") or info.get("regularMarketVolume")),
            "avg_volume": _safe(info.get("averageVolume")),
            "target_mean": _safe(info.get("targetMeanPrice")),
            "recommendation": info.get("recommendationKey"),
        })
    except Exception as e:  # network / parse error
        result["error"] = str(e)

    # แผนสำรอง: Yahoo ชอบบล็อก endpoint แบบ quote จาก IP ของ cloud เป็นพัก ๆ
    # แต่ endpoint แบบ history (กราฟ) มักยังใช้ได้ -> เอาราคาปิด 2 วันล่าสุดมาแทน
    # (ได้ราคา/การเปลี่ยนแปลง แต่ไม่มีข้อมูลงบการเงิน จนกว่า quote จะกลับมา)
    if not result.get("ok"):
        try:
            h = get_history(ticker, period="5d")
            closes = [c["close"] for c in h.get("candles", []) if c.get("close") is not None]
            if closes:
                price = float(closes[-1])
                prev = float(closes[-2]) if len(closes) >= 2 else None
                change = (price - prev) if prev is not None else None
                result.update({
                    "ok": True,
                    "name": result.get("name") or ticker,
                    "price": _safe(price),
                    "previous_close": _safe(prev),
                    "change": _safe(change),
                    "change_pct": _safe(change / prev * 100) if (change is not None and prev) else None,
                    "source": "history-fallback",
                })
                result.pop("error", None)
        except Exception:
            pass

    if result.get("ok"):
        # ราคาจาก fallback แม่นเรื่องแนวโน้มแต่ช้ากว่า realtime -> cache สั้นลง
        ttl = Config.QUOTE_CACHE_TTL if result.get("source") != "history-fallback" else 60
        cache_set(cache_key, result, ttl)
    return result


def get_quotes(tickers) -> list:
    """ดึงหลายตัวพร้อมกัน (ใช้ใน dashboard / screener)"""
    return [get_quote(t) for t in tickers]


# ---------------------------------------------------------------------------
# history (ราคาย้อนหลังสำหรับกราฟ/เทคนิคัล/backtest)
# ---------------------------------------------------------------------------
def get_history(ticker: str, period: str = "1y", interval: str = "1d") -> dict:
    ticker = normalize_ticker(ticker)
    cache_key = f"hist:{ticker}:{period}:{interval}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"ticker": ticker, "candles": [], "ok": False}
    if not _YF_OK:
        out["error"] = "ยังไม่ได้ติดตั้ง yfinance"
        return out

    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            out["error"] = "ไม่พบข้อมูลราคาย้อนหลัง"
            return out
        df = df.reset_index()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        is_intraday = interval not in ("1d", "5d", "1wk", "1mo", "3mo")
        candles = []
        for _, row in df.iterrows():
            d = row[date_col]
            ds = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            # LWC time: Unix timestamp (int) for intraday, "YYYY-MM-DD" for daily+
            if is_intraday:
                try:
                    t = int(d.timestamp())
                except Exception:
                    t = ds
            else:
                t = ds
            candles.append({
                "date": ds,
                "time": t,
                "open": _safe(row.get("Open")),
                "high": _safe(row.get("High")),
                "low": _safe(row.get("Low")),
                "close": _safe(row.get("Close")),
                "volume": _safe(row.get("Volume")),
            })
        out["candles"] = candles
        out["ok"] = True
    except Exception as e:
        out["error"] = str(e)

    if out.get("ok"):
        cache_set(cache_key, out, Config.HISTORY_CACHE_TTL)
    return out


def history_to_series(history: dict):
    """ดึง list ของ close price + dates จากผล get_history"""
    closes = [c["close"] for c in history.get("candles", []) if c["close"] is not None]
    dates = [c["date"] for c in history.get("candles", []) if c["close"] is not None]
    return dates, closes


# ---------------------------------------------------------------------------
# financials (งบการเงินย้อนหลังสำหรับ fundamental)
# ---------------------------------------------------------------------------
def get_financials(ticker: str) -> dict:
    ticker = normalize_ticker(ticker)
    cache_key = f"fin:{ticker}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"ticker": ticker, "ok": False, "years": [], "income": {}, "balance": {}, "cashflow": {}}
    if not _YF_OK:
        out["error"] = "ยังไม่ได้ติดตั้ง yfinance"
        return out

    def df_to_dict(df):
        """แปลงงบ (index=รายการ, columns=ปี) -> {รายการ: [ค่าต่อปี]} เรียงปีเก่า->ใหม่"""
        res = {}
        years = []
        if df is None or getattr(df, "empty", True):
            return years, res
        try:
            cols = list(df.columns)
            cols_sorted = sorted(cols)  # timestamps เรียงจากเก่าไปใหม่
            years = [c.year if hasattr(c, "year") else str(c) for c in cols_sorted]
            for item in df.index:
                vals = [_safe(df.loc[item, c]) for c in cols_sorted]
                res[str(item)] = vals
        except Exception:
            pass
        return years, res

    try:
        tk = yf.Ticker(ticker)
        years_i, income = df_to_dict(getattr(tk, "financials", None))
        years_b, balance = df_to_dict(getattr(tk, "balance_sheet", None))
        years_c, cashflow = df_to_dict(getattr(tk, "cashflow", None))
        out["years"] = years_i or years_b or years_c
        out["income"] = income
        out["balance"] = balance
        out["cashflow"] = cashflow
        out["ok"] = bool(out["years"])
    except Exception as e:
        out["error"] = str(e)

    if out.get("ok"):
        cache_set(cache_key, out, Config.FUNDAMENTAL_CACHE_TTL)
    return out


def search_symbols(q: str) -> list:
    """ค้นหาชื่อหุ้น (ใช้ yfinance search ถ้ามี ไม่งั้นคืน list ว่าง)"""
    q = (q or "").strip()
    if not q or not _YF_OK:
        return []
    try:
        res = yf.Search(q, max_results=10)
        quotes = getattr(res, "quotes", []) or []
        return [
            {
                "symbol": x.get("symbol"),
                "name": x.get("shortname") or x.get("longname"),
                "exchange": x.get("exchange"),
            }
            for x in quotes if x.get("symbol")
        ]
    except Exception:
        return []
