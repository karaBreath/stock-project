"""
Trailing stop — เลื่อนจุดตัดขาดทุนตามราคาที่วิ่งไป ไม่เลื่อนถอยหลังเด็ดขาด

ทำไมต้องมี
----------
จุดตัดขาดทุนแบบตายตัวมีปัญหาสองด้าน: ตั้งชิดไปก็โดนเขี่ยออกจากการแกว่งปกติ
ตั้งห่างไปก็คืนกำไรที่ได้มาแล้วทั้งหมด trailing stop แก้ด้วยการ "ล็อกกำไรทีละขั้น"
คือเลื่อนจุดตัดขึ้นตามราคาสูงสุดที่เคยทำได้ แต่ห้ามเลื่อนลงกลับ

ระยะห่างคิดจาก ATR (ความผันผวนจริงของหุ้นตัวนั้น) ไม่ใช่เปอร์เซ็นต์ตายตัว
เพราะหุ้นที่แกว่ง 5%/วัน กับ 1%/วัน ต้องการระยะไม่เท่ากัน ถ้าใช้ค่าเดียวกัน
ตัวที่แกว่งแรงจะโดนเขี่ยออกตลอด

⚠️ ข้อจำกัดที่ต้องบอกตรง ๆ
  - นี่คือ "ตัวคำนวณและตัวเตือน" ไม่ใช่ระบบส่งคำสั่งอัตโนมัติ
    ระบบนี้ไม่ต่อคำสั่งซื้อขายกับโบรกเกอร์ใด ๆ (สะพาน MT5 เป็นแบบอ่านอย่างเดียว)
  - คำนวณจากราคาปิดรายวัน จุดตัดจริงระหว่างวันอาจต่างจากนี้
"""
import datetime as dt

from services import stock_data

DEFAULT_ATR_LEN = 14
DEFAULT_MULT = 2.5          # ระยะ = 2.5 เท่าของ ATR (ค่ากลาง ๆ ที่ใช้กันทั่วไป)
MIN_BARS = 20


def _true_ranges(highs, lows, closes):
    """
    True Range รายวัน — รวม "ช่องว่างราคาข้ามคืน" (gap) ด้วย ไม่ใช่แค่ high-low
    เพราะราคากระโดดข้ามวันคือความเสี่ยงจริงที่ต้องนับ
    """
    return [max(highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))]


def _atr_series(highs, lows, closes, length: int = DEFAULT_ATR_LEN):
    """
    ATR ของ "ทุกแท่ง" ไม่ใช่ค่าเดียวจากปลายชุด

    ⚠️ เหตุผลสำคัญ (บั๊กจริงที่เทสจับได้):
    ถ้าใช้ ATR ค่าเดียวจากปลายชุดมาคิดย้อนทั้งเส้น พอราคาย่อแรง ATR จะโตขึ้น
    ทำให้ "จุดตัดที่คำนวณใหม่วันนี้" ต่ำกว่าที่คำนวณเมื่อวาน = เลื่อนถอยหลัง
    ซึ่งทำลายคุณสมบัติเดียวที่ทำให้ trailing stop มีประโยชน์ (ล็อกกำไร)
    การเดินด้วย ATR ของแต่ละแท่งทำให้เส้นทางจุดตัดคงที่ ไม่ว่าจะคำนวณวันไหน
    """
    trs = _true_ranges(highs, lows, closes)
    if len(trs) < length:
        return None
    out = [None] * len(closes)
    run = sum(trs[:length])
    out[length] = run / length              # แท่งแรกที่มี ATR ครบหน้าต่าง
    for i in range(length + 1, len(closes)):
        run += trs[i - 1] - trs[i - 1 - length]
        out[i] = run / length
    return out


def _atr(highs, lows, closes, length: int = DEFAULT_ATR_LEN):
    """ATR ล่าสุด (ใช้แสดงผล)"""
    series = _atr_series(highs, lows, closes, length)
    if not series:
        return None
    latest = next((v for v in reversed(series) if v is not None), None)
    return latest


def compute(highs, lows, closes, entry: float, entry_index: int = 0,
            mult: float = DEFAULT_MULT, atr_len: int = DEFAULT_ATR_LEN) -> dict:
    """
    เดินราคาตั้งแต่วันที่เข้าจนถึงวันล่าสุด แล้วคืนจุดตัดขาดทุนปัจจุบัน

    กติกา:
      stop วันนี้ = max(stop เมื่อวาน, ราคาสูงสุดที่เคยทำได้ - mult × ATR)
    จึงเลื่อนขึ้นได้อย่างเดียว — นี่คือคุณสมบัติที่ทำให้มัน "ล็อกกำไร" ได้จริง
    """
    n = len(closes)
    if n < MIN_BARS or n != len(highs) or n != len(lows):
        return {"ok": False, "error": f"ข้อมูลราคาไม่พอ (มี {n} แท่ง ต้องการ {MIN_BARS}+)"}
    atrs = _atr_series(highs, lows, closes, atr_len)
    if not atrs:
        return {"ok": False, "error": "คำนวณ ATR ไม่ได้จากข้อมูลชุดนี้"}
    atr = next((v for v in reversed(atrs) if v is not None), None)
    if not atr or atr <= 0:
        return {"ok": False, "error": "คำนวณ ATR ไม่ได้จากข้อมูลชุดนี้"}

    start = max(1, min(entry_index, n - 1))
    first_atr = next((v for v in atrs[start:] if v is not None), atr)
    peak = highs[start]
    stop = entry - mult * first_atr    # ขั้นแรกวัดจากราคาที่เข้า
    hit_index = None
    for i in range(start, n):
        peak = max(peak, highs[i])
        a = atrs[i]
        if a:
            # เดินด้วย ATR ของแท่งนั้น ๆ แล้วยกขึ้นอย่างเดียว ห้ามถอยหลัง
            stop = max(stop, peak - mult * a)
        if hit_index is None and lows[i] <= stop:
            hit_index = i

    price = closes[-1]
    return {
        "ok": True,
        "stop": round(stop, 4),
        "peak": round(peak, 4),
        "atr": round(atr, 4),
        "mult": mult,
        "price": round(price, 4),
        # เหลือระยะให้ราคาถอยได้อีกกี่ % ก่อนโดนตัด
        "room_pct": round((price - stop) / price * 100, 2) if price else None,
        # ถ้าตัดตรงนี้ ล็อกกำไรได้เท่าไหร่เทียบกับราคาที่เข้า
        "locked_pct": round((stop - entry) / entry * 100, 2) if entry else None,
        "in_profit": stop > entry,
        "already_hit": hit_index is not None,
        "atr_len": atr_len,
    }


def for_ticker(ticker: str, entry: float, entry_date: str = "",
               mult: float = DEFAULT_MULT) -> dict:
    """คำนวณจากราคาจริงย้อนหลัง 1 ปีของหุ้นตัวนั้น"""
    ticker = stock_data.normalize_ticker(ticker)
    hist = stock_data.get_history(ticker, period="1y", interval="1d")
    if not hist.get("ok"):
        return {"ok": False, "ticker": ticker,
                "error": hist.get("error") or "ดึงราคาย้อนหลังไม่ได้"}

    candles = hist.get("candles") or []
    if not candles:
        return {"ok": False, "ticker": ticker, "error": "ไม่มีข้อมูลแท่งราคา"}

    days = [c.get("date", "")[:10] for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    closes = [float(c["close"]) for c in candles]

    idx = 0
    if entry_date:
        for i, d in enumerate(days):
            if d >= entry_date[:10]:
                idx = i
                break

    res = compute(highs, lows, closes, float(entry), idx, mult)
    res.update({"ticker": ticker, "entry": float(entry),
                "entry_date": days[idx] if days else entry_date,
                "as_of": days[-1] if days else None})
    return res


def _advice(row: dict) -> str:
    if not row.get("ok"):
        return "คำนวณไม่ได้"
    if row.get("already_hit"):
        return "ราคาเคยหลุดจุดตัดไปแล้ว — ทบทวนไม้นี้"
    if row.get("in_profit"):
        return f"ล็อกกำไรไว้แล้ว {row['locked_pct']}% ถ้าหลุด {row['stop']}"
    return f"ยังไม่ถึงจุดคุ้มทุน — ตัดที่ {row['stop']}"


def portfolio() -> dict:
    """
    trailing stop ของทุกไม้ในพอร์ตที่บันทึกไว้

    ล้มเป็นรายตัวได้ (เช่นหุ้นตัวหนึ่งดึงราคาไม่ได้) โดยตัวอื่นยังคำนวณต่อ
    """
    from database import query
    holdings = query("SELECT * FROM holdings ORDER BY created_at DESC") or []
    rows = []
    for h in holdings:
        try:
            r = for_ticker(h["ticker"], h["buy_price"], h.get("buy_date") or "")
        except Exception as e:
            r = {"ok": False, "ticker": h["ticker"], "error": str(e)[:120]}
        r["shares"] = h.get("shares")
        r["advice"] = _advice(r)
        rows.append(r)

    ok_rows = [r for r in rows if r.get("ok")]
    return {
        "ok": True,
        "rows": rows,
        "count": len(rows),
        "computed": len(ok_rows),
        "in_profit": sum(1 for r in ok_rows if r.get("in_profit")),
        "note": ("ตัวช่วยคำนวณและเตือนเท่านั้น ระบบไม่ส่งคำสั่งซื้อขายให้อัตโนมัติ "
                 "· คิดจากราคาปิดรายวัน จุดตัดจริงระหว่างวันอาจต่างจากนี้"),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
