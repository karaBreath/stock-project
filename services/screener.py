"""
Stock Screener — คัดกรองหุ้นตามเกณฑ์ P/E, ROE, D/E, market cap, ปันผล ฯลฯ
ทำงานบน universe หุ้นไทย/สหรัฐ ที่กำหนดใน Config (ขยายรายชื่อได้)
"""
from config import Config
from services import stock_data


def _passes(q, f):
    """ตรวจว่า quote q ผ่านเกณฑ์ filter f หรือไม่"""
    def ok_max(val, key):
        if f.get(key) in (None, "", ): return True
        return val is not None and val <= float(f[key])
    def ok_min(val, key):
        if f.get(key) in (None, ""): return True
        return val is not None and val >= float(f[key])

    roe = q.get("roe")
    roe_pct = roe * 100 if (roe is not None and abs(roe) < 5) else roe
    de = q.get("debt_to_equity")
    de_val = de / 100 if (de is not None and de > 10) else de
    dy = q.get("dividend_yield")
    dy_pct = dy * 100 if (dy is not None and dy < 1) else dy

    checks = [
        ok_max(q.get("pe"), "pe_max"),
        ok_min(q.get("pe"), "pe_min"),
        ok_min(roe_pct, "roe_min"),
        ok_max(de_val, "de_max"),
        ok_min(dy_pct, "dy_min"),
        ok_min(q.get("market_cap"), "mcap_min"),
    ]
    return all(checks)


def screen(filters: dict, market="th") -> dict:
    universe = filters.get("tickers")
    if not universe:
        universe = Config.DEFAULT_TH_TICKERS if market == "th" else Config.DEFAULT_US_TICKERS

    results = []
    for t in universe:
        q = stock_data.get_quote(t)
        if not q.get("ok"):
            continue
        if _passes(q, filters):
            results.append({
                "ticker": t,
                "name": q.get("name"),
                "price": q.get("price"),
                "change_pct": q.get("change_pct"),
                "pe": q.get("pe"),
                "roe": q.get("roe"),
                "debt_to_equity": q.get("debt_to_equity"),
                "dividend_yield": q.get("dividend_yield"),
                "market_cap": q.get("market_cap"),
                "sector": q.get("sector"),
            })

    results.sort(key=lambda r: (r["market_cap"] or 0), reverse=True)
    return {"count": len(results), "results": results, "market": market}
