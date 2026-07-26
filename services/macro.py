"""
Macro service — ปัจจัยมหภาค: ทอง น้ำมัน ค่าเงิน ดอกเบี้ย ดัชนีตลาด ฯลฯ
อิงสัญลักษณ์ใน Config.MACRO_SYMBOLS (ดึงจาก Yahoo Finance)
"""
import time

from config import Config
from database import cache_get, cache_set
from services import stock_data


def get_macro(market: str = "") -> dict:
    """
    ปัจจัยมหภาค — ถ้าระบุ market จะเรียงตัวที่สำคัญกับตลาดนั้นขึ้นก่อน
      th -> SET, บาท, ทอง, น้ำมัน
      us -> S&P, Nasdaq, VIX, บอนด์, DXY, เซมิคอนดักเตอร์
    """
    cached = cache_get("macro:all")
    if cached:
        return _focus(cached, market)

    def fetch(symbol):
        q = stock_data.get_quote(symbol)
        if not q.get("ok"):
            # Yahoo ชอบ rate-limit ตอนยิงหลายตัวติดกัน (เจอบ่อยบนเซิร์ฟเวอร์ cloud)
            # เว้นจังหวะแล้วลองอีกครั้ง ก่อนยอมแพ้
            time.sleep(0.6)
            q = stock_data.get_quote(symbol)
        return q

    items = []
    for key, (symbol, label) in Config.MACRO_SYMBOLS.items():
        q = fetch(symbol)
        items.append({
            "key": key,
            "symbol": symbol,
            "label": label,
            "price": q.get("price"),
            "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "ok": q.get("ok", False),
        })

    result = {"items": items}
    # ถ้ามีตัวที่ดึงไม่สำเร็จ อย่า cache นาน — ให้รอบหน้าได้ลองใหม่เร็ว ๆ
    # (บั๊กเดิม: ค่า "—" ถูก cache ค้างเต็ม TTL ทั้งที่ Yahoo หายเป็นปกติแล้ว)
    all_ok = all(i["ok"] for i in items)
    cache_set("macro:all", result, Config.MACRO_CACHE_TTL if all_ok else 60)
    return _focus(result, market)


def _focus(result: dict, market: str) -> dict:
    """เรียงตัวชี้วัดที่สำคัญกับตลาดที่กำลังดูขึ้นก่อน"""
    focus = Config.MACRO_FOCUS.get(market)
    if not focus:
        return result
    order = {k: i for i, k in enumerate(focus)}
    items = sorted(result.get("items", []),
                   key=lambda x: order.get(x["key"], 99))
    return {"items": items, "market": market, "focus": focus}


def sector_performance(market="us") -> dict:
    """เปรียบเทียบกลุ่มอุตสาหกรรม (sector rotation) ด้วย ETF/หุ้นตัวแทน"""
    cache_key = f"sector:{market}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    if market == "us":
        sectors = {
            "เทคโนโลยี": "XLK", "การเงิน": "XLF", "พลังงาน": "XLE",
            "สุขภาพ": "XLV", "อุตสาหกรรม": "XLI", "สินค้าผู้บริโภค": "XLY",
            "สาธารณูปโภค": "XLU", "วัสดุ": "XLB", "อสังหา": "XLRE",
        }
    else:
        # ใช้หุ้นไทยตัวแทนแต่ละกลุ่ม
        sectors = {
            "พลังงาน": "PTT.BK", "ธนาคาร": "KBANK.BK", "ค้าปลีก": "CPALL.BK",
            "สื่อสาร": "ADVANC.BK", "การแพทย์": "BDMS.BK", "อิเล็กทรอนิกส์": "DELTA.BK",
            "ขนส่ง": "AOT.BK", "วัสดุก่อสร้าง": "SCC.BK",
        }

    rows = []
    for name, sym in sectors.items():
        h = stock_data.get_history(sym, period="3mo")
        _, closes = stock_data.history_to_series(h)
        perf_1m = perf_3m = None
        if len(closes) > 21:
            perf_1m = round((closes[-1] / closes[-21] - 1) * 100, 2)
        if len(closes) > 2:
            perf_3m = round((closes[-1] / closes[0] - 1) * 100, 2)
        rows.append({"sector": name, "symbol": sym, "perf_1m": perf_1m, "perf_3m": perf_3m})

    rows.sort(key=lambda r: (r["perf_1m"] if r["perf_1m"] is not None else -999), reverse=True)
    result = {"market": market, "rows": rows}
    cache_set(cache_key, result, Config.MACRO_CACHE_TTL)
    return result
