"""
Daily report — สแกน universe + watchlist หาหุ้นน่าซื้อ พร้อมจุดเข้า/ตัดขาดทุน/เป้าราคา
และสรุปภาวะตลาด (Fear & Greed + มหภาค)
"""
import datetime as dt

import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import Config
from database import query
from services import scoring, sentiment as sentiment_svc, macro, gdelt
from services.universe import get_universe


def generate(market="us", top_n=5) -> dict:
    # ใช้ universe เต็ม + watchlist ส่วนตัว
    full = get_universe(market)
    watch = [w["ticker"] for w in query("SELECT ticker FROM watchlist")]
    # สุ่มดึง 80 ตัวจาก universe เพื่อความเร็ว + รวม watchlist ทั้งหมด
    sample = random.sample(full, min(80, len(full)))
    universe = list(dict.fromkeys(sample + watch))

    scored = []
    def _score(t):
        try:
            s = scoring.overall(t, deep=False)
            return s if s.get("total_score") is not None else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=15) as ex:
        for result in as_completed({ex.submit(_score, t): t for t in universe}):
            s = result.result()
            if s:
                scored.append(s)

    scored.sort(key=lambda x: x["total_score"], reverse=True)

    scored.sort(key=lambda x: x["total_score"], reverse=True)
    top_buys = [s for s in scored if s["total_score"] >= 55][:top_n]
    top_avoid = [s for s in scored if s["total_score"] < 40][-top_n:]

    fg = sentiment_svc.fear_greed(market)
    mac = macro.get_macro(market)

    # ---- บริบทข่าวโลกวันนี้ (ธีมที่ผิดปกติมากที่สุด) ----
    world = []
    try:
        rows = gdelt.theme_signals(timespan="7d").get("rows", [])
        world = sorted(
            [r for r in rows if r.get("deviation") is not None],
            key=lambda r: abs(r["deviation"]), reverse=True,
        )[:4]
    except Exception:
        world = []

    # ---- หุ้นที่ข่าวโลกกำลังหนุน/กดดัน (จากสิ่งที่เครื่องเรียนรู้ไว้) ----
    catalysts = [
        {"ticker": s["ticker"], "name": s.get("name"),
         "adjust": s["catalyst"]["adjust"],
         "label": s["catalyst"].get("label"),
         "reasons": [r["text"] for r in s["catalyst"].get("reasons", [])[:2]]}
        for s in scored
        if s.get("catalyst", {}).get("ok") and abs(s["catalyst"].get("adjust", 0)) >= 2
    ]
    catalysts.sort(key=lambda c: abs(c["adjust"]), reverse=True)

    return {
        "date": dt.date.today().isoformat(),
        "market": market,
        "fear_greed": fg,
        "macro": mac["items"][:6],
        "world_news": world,
        "catalysts": catalysts[:6],
        "top_buys": top_buys,
        "watch_avoid": top_avoid,
        "scanned": len(scored),
    }
