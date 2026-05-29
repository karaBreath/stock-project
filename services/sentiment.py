"""
Sentiment service — Fear & Greed Index + sentiment ข่าวต่อหุ้น

Fear & Greed คำนวณแบบประมาณจากปัจจัยตลาด (โมเมนตัม, ความผันผวน, safe-haven)
โดยใช้ข้อมูลจาก Yahoo Finance เพื่อให้ทำงานได้โดยไม่ต้องพึ่ง API เฉพาะ
"""
import numpy as np

from config import Config
from database import cache_get, cache_set
from services import stock_data, news


def _pct_from_ma(symbol, period="6mo"):
    """ราคาปัจจุบันสูง/ต่ำกว่าเส้นค่าเฉลี่ย 125 วันกี่ %"""
    h = stock_data.get_history(symbol, period=period)
    _, closes = stock_data.history_to_series(h)
    if len(closes) < 30:
        return None
    ma = np.mean(closes[-125:]) if len(closes) >= 125 else np.mean(closes)
    return (closes[-1] - ma) / ma * 100 if ma else None


def _volatility(symbol, period="3mo"):
    h = stock_data.get_history(symbol, period=period)
    _, closes = stock_data.history_to_series(h)
    if len(closes) < 10:
        return None
    rets = np.diff(closes) / closes[:-1]
    return float(np.std(rets) * np.sqrt(252) * 100)  # annualized %


def fear_greed(market="us") -> dict:
    cache_key = f"feargreed:{market}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    index_symbol = "^SET.BK" if market == "th" else "^GSPC"
    components = {}
    score = 50.0

    # 1) momentum — ราคาเทียบ MA125
    mom = _pct_from_ma(index_symbol)
    if mom is not None:
        components["momentum"] = round(mom, 2)
        score += max(-25, min(25, mom * 2.5))

    # 2) volatility — ผันผวนสูง = กลัว
    vol = _volatility(index_symbol)
    if vol is not None:
        components["volatility"] = round(vol, 2)
        # vol 10% = ปกติ, สูงกว่านี้ลดคะแนน
        score -= max(-15, min(20, (vol - 15) * 0.8))

    # 3) safe haven — ทองขึ้นแรง = กลัว
    gold = _pct_from_ma("GC=F", period="3mo")
    if gold is not None:
        components["safe_haven_gold"] = round(gold, 2)
        score -= max(-10, min(10, gold * 0.5))

    score = int(max(0, min(100, round(score))))
    if score >= 75:
        label = "โลภสุดขีด (Extreme Greed)"
    elif score >= 55:
        label = "โลภ (Greed)"
    elif score >= 45:
        label = "เป็นกลาง (Neutral)"
    elif score >= 25:
        label = "กลัว (Fear)"
    else:
        label = "กลัวสุดขีด (Extreme Fear)"

    result = {"score": score, "label": label, "components": components, "market": market}
    cache_set(cache_key, result, Config.MACRO_CACHE_TTL)
    return result


def stock_sentiment(ticker: str) -> dict:
    """รวม sentiment ข่าวของหุ้นรายตัว เป็นคะแนน 0-100"""
    q = stock_data.get_quote(ticker)
    name = q.get("name") or ticker
    n = news.get_news(query=name, ticker=ticker, limit=15)
    s = n["summary"]
    total = max(1, s["positive"] + s["negative"] + s["neutral"])
    raw = (s["positive"] - s["negative"]) / total  # -1..1
    score = int(round(50 + raw * 50))
    return {
        "ticker": ticker,
        "sentiment_score": max(0, min(100, score)),
        "summary": s,
        "headlines": n["items"][:8],
    }
