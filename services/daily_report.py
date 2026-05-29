"""
Daily report — สแกน universe + watchlist หาหุ้นน่าซื้อ พร้อมจุดเข้า/ตัดขาดทุน/เป้าราคา
และสรุปภาวะตลาด (Fear & Greed + มหภาค)
"""
import datetime as dt

from config import Config
from database import query
from services import scoring, sentiment as sentiment_svc, macro


def generate(market="th", top_n=5) -> dict:
    base = Config.DEFAULT_TH_TICKERS if market == "th" else Config.DEFAULT_US_TICKERS
    watch = [w["ticker"] for w in query("SELECT ticker FROM watchlist")]
    universe = list(dict.fromkeys(base + watch))  # unique, รักษาลำดับ

    scored = []
    for t in universe:
        try:
            s = scoring.overall(t)
            if s.get("total_score") is not None:
                scored.append(s)
        except Exception:
            continue

    scored.sort(key=lambda x: x["total_score"], reverse=True)
    top_buys = [s for s in scored if s["total_score"] >= 55][:top_n]
    top_avoid = [s for s in scored if s["total_score"] < 40][-top_n:]

    fg = sentiment_svc.fear_greed(market)
    mac = macro.get_macro()

    return {
        "date": dt.date.today().isoformat(),
        "market": market,
        "fear_greed": fg,
        "macro": mac["items"][:6],
        "top_buys": top_buys,
        "watch_avoid": top_avoid,
        "scanned": len(scored),
    }
