"""
ข้อมูล "เหตุการณ์" ของหุ้นรายตัว — วันประกาศงบ และการซื้อขายของผู้บริหาร

ใช้เป็นวัตถุดิบของกลยุทธ์ตระกูลเหตุการณ์ใน Strategy Lab:
  - PEAD   : หุ้นที่งบดีกว่าคาดมักไหลต่ออีก 1-3 เดือน
  - insider: ผู้บริหารซื้อหุ้นบริษัทตัวเอง = สัญญาณที่มีสถิติรองรับ

ทั้งคู่ดึงจาก Yahoo Finance ผ่าน yfinance ซึ่งเป็นแหล่งฟรีที่เรามีอยู่แล้ว
และมีข้อจำกัดที่ต้องรู้ (เขียนไว้ในแต่ละฟังก์ชัน) — ระบบจะรายงานตรง ๆ
เมื่อข้อมูลไม่พอ ไม่เดาแทนและไม่ทำเป็นว่ามีสัญญาณ
"""
import datetime as dt

from database import cache_get, cache_set

try:
    import yfinance as yf
    _YF_OK = True
except Exception:  # pragma: no cover
    yf = None
    _YF_OK = False

CACHE_TTL = 60 * 60 * 12          # ข้อมูลพวกนี้เปลี่ยนไม่บ่อย เก็บครึ่งวันพอ
MIN_EVENTS = 4                    # น้อยกว่านี้ทดสอบอะไรไม่ได้ อย่าไปหลอกตัวเอง


def _day(value) -> str:
    """แปลงค่าวันที่หลายรูปแบบให้เป็น 'YYYY-MM-DD' · คืน '' ถ้าอ่านไม่ออก"""
    if value is None:
        return ""
    for attr in ("date",):
        if hasattr(value, attr):
            try:
                return value.date().isoformat()
            except Exception:
                pass
    s = str(value).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "")).date().isoformat()
    except Exception:
        return ""


def _num(v):
    try:
        f = float(v)
        return None if f != f else f          # กัน NaN
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1) วันประกาศงบ + เซอร์ไพรส์ (PEAD)
# ---------------------------------------------------------------------------
def earnings_surprises(ticker: str) -> dict:
    """
    คืนรายการ {day, surprise_pct} ของงบที่ประกาศไปแล้ว

    ข้อจำกัดที่ต้องรู้:
      - Yahoo ให้ย้อนหลังจำกัด (ราว 4-12 ไตรมาส) ยาวกว่านั้นไม่มี
      - หุ้นไทย (.BK) ส่วนใหญ่ไม่มีค่าคาดการณ์ จึงคำนวณเซอร์ไพรส์ไม่ได้
      - บางแถวเป็นงบ "ที่ยังไม่ประกาศ" (อนาคต) ต้องตัดทิ้ง ไม่งั้นจะมองเห็นอนาคต
        ซึ่งทำให้ backtest สวยแบบหลอก ๆ (look-ahead bias)
    """
    key = f"events:earn:{ticker}"
    cached = cache_get(key)
    if cached:
        return cached

    out = {"ticker": ticker, "events": [], "ok": False}
    if not _YF_OK:
        out["error"] = "ไม่มีไลบรารี yfinance"
        return out

    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=24)
    except Exception as e:
        out["error"] = f"ดึงวันประกาศงบไม่ได้: {str(e)[:120]}"
        return out
    if df is None or getattr(df, "empty", True):
        out["error"] = "Yahoo ไม่มีข้อมูลวันประกาศงบของหุ้นตัวนี้"
        return out

    today = dt.date.today().isoformat()
    cols = {str(c).lower(): c for c in df.columns}
    sur_col = next((cols[c] for c in cols if "surprise" in c), None)
    est_col = next((cols[c] for c in cols if "estimate" in c), None)
    rep_col = next((cols[c] for c in cols if "reported" in c), None)

    for idx, row in df.iterrows():
        day = _day(idx)
        if not day or day > today:            # งบที่ยังไม่ประกาศ = ห้ามใช้
            continue
        pct = _num(row.get(sur_col)) if sur_col else None
        if pct is None and est_col and rep_col:
            est, rep = _num(row.get(est_col)), _num(row.get(rep_col))
            if est not in (None, 0) and rep is not None:
                pct = (rep - est) / abs(est) * 100.0
        if pct is None:
            continue
        out["events"].append({"day": day, "surprise_pct": round(pct, 2)})

    out["events"].sort(key=lambda e: e["day"])
    out["ok"] = len(out["events"]) >= MIN_EVENTS
    if not out["ok"] and not out.get("error"):
        out["error"] = (f"มีงบที่คำนวณเซอร์ไพรส์ได้แค่ {len(out['events'])} ครั้ง "
                        f"(ต้องการ {MIN_EVENTS}+) — หุ้นไทยมักไม่มีค่าคาดการณ์ใน Yahoo")
    if out["ok"]:
        cache_set(key, out, CACHE_TTL)
    return out


# ---------------------------------------------------------------------------
# 2) ผู้บริหารซื้อหุ้นตัวเอง (insider)
# ---------------------------------------------------------------------------
BUY_WORDS = ("purchase", "buy", "acquis")
SELL_WORDS = ("sale", "sell", "disposition")


def insider_buys(ticker: str) -> dict:
    """
    คืนรายการ {day, shares, value, who} เฉพาะรายการ "ซื้อ" ของผู้บริหาร

    ข้อจำกัดที่ต้องรู้:
      - Yahoo ให้ย้อนหลังราว 1-2 ปีเท่านั้น
      - เป็นข้อมูลของตลาดสหรัฐเป็นหลัก · หุ้นไทยแทบไม่มี
      - วันที่ในข้อมูลคือ "วันที่ทำรายการ" ซึ่งมักถูกรายงานช้ากว่าจริง 1-2 วัน
        กลยุทธ์จึงต้องเข้าซื้อ "วันถัดไป" เสมอ ไม่ใช่วันเดียวกัน
    """
    key = f"events:insider:{ticker}"
    cached = cache_get(key)
    if cached:
        return cached

    out = {"ticker": ticker, "events": [], "ok": False}
    if not _YF_OK:
        out["error"] = "ไม่มีไลบรารี yfinance"
        return out

    try:
        df = yf.Ticker(ticker).insider_transactions
    except Exception as e:
        out["error"] = f"ดึงข้อมูล insider ไม่ได้: {str(e)[:120]}"
        return out
    if df is None or getattr(df, "empty", True):
        out["error"] = "Yahoo ไม่มีข้อมูล insider ของหุ้นตัวนี้"
        return out

    cols = {str(c).lower(): c for c in df.columns}
    c_text = next((cols[c] for c in cols if "text" in c or "transaction" in c), None)
    c_date = next((cols[c] for c in cols if "date" in c), None)
    c_shares = next((cols[c] for c in cols if "share" in c), None)
    c_value = next((cols[c] for c in cols if "value" in c), None)
    c_who = next((cols[c] for c in cols if "insider" in c), None)

    today = dt.date.today().isoformat()
    for _, row in df.iterrows():
        text = str(row.get(c_text, "")).lower() if c_text else ""
        if any(w in text for w in SELL_WORDS):
            continue
        if not any(w in text for w in BUY_WORDS):
            continue
        day = _day(row.get(c_date)) if c_date else ""
        if not day or day > today:
            continue
        out["events"].append({
            "day": day,
            "shares": _num(row.get(c_shares)) if c_shares else None,
            "value": _num(row.get(c_value)) if c_value else None,
            "who": str(row.get(c_who, ""))[:60] if c_who else "",
        })

    out["events"].sort(key=lambda e: e["day"])
    out["ok"] = len(out["events"]) >= MIN_EVENTS
    if not out["ok"] and not out.get("error"):
        out["error"] = (f"เจอรายการซื้อของผู้บริหารแค่ {len(out['events'])} ครั้ง "
                        f"(ต้องการ {MIN_EVENTS}+) — Yahoo ให้ย้อนหลังจำกัด "
                        "และหุ้นไทยแทบไม่มีข้อมูลนี้")
    if out["ok"]:
        cache_set(key, out, CACHE_TTL)
    return out
