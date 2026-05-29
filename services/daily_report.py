"""
Daily report — สแกน universe + watchlist หาหุ้นน่าซื้อ พร้อมจุดเข้า/ตัดขาดทุน/เป้าราคา
และสรุปภาวะตลาด (Fear & Greed + มหภาค)
"""
import datetime as dt

import random
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import Config
from database import query
from services import scoring, sentiment as sentiment_svc, macro
from services.universe import get_universe


def generate(market="th", top_n=5) -> dict:
    # ใช้ universe เต็ม + watchlist ส่วนตัว
    full = get_universe(market)
    watch = [w["ticker"] for w in query("SELECT ticker FROM watchlist")]
    # สุ่มดึง 80 ตัวจาก universe เพื่อความเร็ว + รวม watchlist ทั้งหมด
    sample = random.sample(full, min(80, len(full)))
    universe = list(dict.fromkeys(sample + watch))

    scored = []
    def _score(t):
        try:
            s = scoring.overall(t)
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
