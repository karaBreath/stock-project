"""
Stock Screener — คัดกรองหุ้นตามเกณฑ์ P/E, ROE, D/E, market cap, ปันผล ฯลฯ
ใช้ universe หุ้นไทย 300+ ตัว และ US 500+ ตัว
ดึงข้อมูลแบบ parallel เพื่อความเร็ว
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from services import stock_data
from services.universe import get_universe


def _passes(q, f):
    def ok_max(val, key):
        if f.get(key) in (None, ""): return True
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
        ok_max(q.get("market_cap"), "mcap_max"),
    ]
    return all(checks)


def _fetch_one(ticker):
    try:
        return stock_data.get_quote(ticker)
    except Exception:
        return {"ok": False, "ticker": ticker}


def screen(filters: dict, market="us") -> dict:
    # ใช้ universe ที่ระบุหรือ universe เต็ม
    tickers = filters.get("tickers") or get_universe(market)

    results = []
    # ดึงข้อมูลแบบ parallel (20 threads พร้อมกัน)
    with ThreadPoolExecutor(max_workers=20) as ex:
        future_map = {ex.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(future_map):
            q = future.result()
            if not q.get("ok"):
                continue
            if _passes(q, filters):
                results.append({
                    "ticker": q.get("ticker"),
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
    return {"count": len(results), "results": results, "market": market,
            "scanned": len(tickers)}
