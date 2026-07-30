"""
Crisis study — เรียนรู้จากวิกฤตในอดีต เพื่อรู้จัก "สัญญาณเตือนล่วงหน้า"

ตอบ 2 คำถาม
-----------
1) วิกฤตแต่ละแบบ (เงินเฟ้อ/ดอกเบี้ย · อสังหา+หนี้เสีย · สงคราม · โรคระบาด ·
   ฟองสบู่เทค) ทำให้หุ้นที่เราถือเสียหายแค่ไหน และใช้เวลาฟื้นนานเท่าไหร่
2) ก่อนวิกฤตแต่ละครั้ง "สัญญาณเตือน" หน้าตาเป็นยังไง แล้ววันนี้เราอยู่ตรงไหน
   เทียบกับตอนนั้น

⚠️ ข้อจำกัดที่ต้องรู้ก่อนใช้
---------------------------
- GDELT (ข่าว) มีข้อมูลย้อนหลังถึงราว ปี 2017 เท่านั้น จึง **ใช้ทำ backtest
  วิกฤต 2008 หรือ 2000 ไม่ได้** โมดูลนี้จึงใช้ "ราคา + ตัวชี้วัดมหภาค" ซึ่ง
  ย้อนหลังได้ถึงปี 1990s-2000s แทน
- วิกฤตในอดีตมีแค่หยิบมือ (7-8 ครั้งใน 25 ปี) จำนวนตัวอย่างน้อยมาก
  จะสรุปเป็นกฎเหล็กไม่ได้ ใช้เป็น "บริบท" เท่านั้น
- ทุกครั้งที่วิกฤตเกิด สาเหตุไม่เหมือนกัน สัญญาณที่เคยเตือนได้ครั้งก่อน
  อาจไม่เตือนครั้งหน้า (และเคยเตือนผิดหลายครั้งที่ไม่เกิดวิกฤต)
"""
import datetime as dt

import numpy as np

from database import cache_get, cache_set
from services import stock_data


# ---------------------------------------------------------------------------
# วิกฤตสำคัญ — start = จุดสูงสุดก่อนร่วง, trough = จุดต่ำสุด
# ---------------------------------------------------------------------------
CRISES = [
    {"key": "dotcom", "name": "ฟองสบู่ดอทคอม", "cause": "ฟองสบู่หุ้นเทค",
     "start": "2000-03-24", "trough": "2002-10-09",
     "note": "หุ้นเทคราคาแพงเกินพื้นฐานมาก แล้วปรับฐานยาว 2 ปีครึ่ง"},
    {"key": "gfc", "name": "วิกฤตซับไพรม์ 2008", "cause": "อสังหา + หนี้เสีย",
     "start": "2007-10-09", "trough": "2009-03-09",
     "note": "สินเชื่อบ้านคุณภาพต่ำผิดนัดชำระเป็นวงกว้าง ลามไปทั้งระบบธนาคาร"},
    {"key": "eurodebt", "name": "วิกฤตหนี้ยุโรป 2011", "cause": "หนี้ภาครัฐ",
     "start": "2011-04-29", "trough": "2011-10-03",
     "note": "กรีซ/อิตาลี/สเปน เสี่ยงผิดนัดชำระหนี้"},
    {"key": "china2015", "name": "จีนลดค่าเงิน 2015", "cause": "ค่าเงิน + เศรษฐกิจจีน",
     "start": "2015-05-21", "trough": "2016-02-11",
     "note": "จีนลดค่าหยวนกะทันหัน ตลาดเกิดใหม่และสินค้าโภคภัณฑ์ร่วง"},
    {"key": "q4_2018", "name": "ขึ้นดอกเบี้ย + สงครามการค้า 2018", "cause": "ดอกเบี้ย + การค้า",
     "start": "2018-09-20", "trough": "2018-12-24",
     "note": "เฟดขึ้นดอกเบี้ยพร้อมสงครามการค้าสหรัฐ-จีน"},
    {"key": "covid", "name": "โควิด-19 2020", "cause": "โรคระบาด",
     "start": "2020-02-19", "trough": "2020-03-23",
     "note": "ร่วงเร็วและแรงที่สุดในประวัติศาสตร์ แต่ฟื้นเร็วมากเช่นกัน"},
    {"key": "inflation2022", "name": "เงินเฟ้อ + ขึ้นดอกเบี้ยแรง 2022", "cause": "เงินเฟ้อ + ดอกเบี้ย",
     "start": "2022-01-03", "trough": "2022-10-12",
     "note": "เงินเฟ้อสูงสุดใน 40 ปี เฟดขึ้นดอกเบี้ยเร็วที่สุดในรอบหลายสิบปี "
             "(ช่วงเดียวกับสงครามรัสเซีย-ยูเครน)"},
    {"key": "svb2023", "name": "แบงก์สหรัฐล้ม (SVB) 2023", "cause": "ธนาคาร + ดอกเบี้ย",
     "start": "2023-02-02", "trough": "2023-03-13",
     "note": "ธนาคารขาดทุนจากพันธบัตรเมื่อดอกเบี้ยขึ้นแรง เกิดแห่ถอนเงิน"},
]

# ตัวชี้วัดเตือนภัยล่วงหน้า (ทุกตัวดึงจาก Yahoo ได้ ย้อนหลังยาว)
WARNING_INDICATORS = {
    "yield_curve": {
        "label": "ส่วนต่างดอกเบี้ย 10 ปี − 3 เดือน",
        "hint": "ติดลบ (inverted) = ตลาดบอนด์เตือนเศรษฐกิจถดถอย มักนำวิกฤต 6-18 เดือน",
        "kind": "spread", "a": "^TNX", "b": "^IRX",
        "danger": "below", "danger_level": 0.0,
    },
    "vix": {
        "label": "VIX ดัชนีความกลัว",
        "hint": "ปกติ 12-20 · เกิน 30 = ตลาดตื่นตระหนก",
        "kind": "level", "a": "^VIX",
        "danger": "above", "danger_level": 30.0,
    },
    "credit": {
        "label": "หุ้นกู้เสี่ยงสูง / หุ้นกู้คุณภาพดี (HYG÷LQD)",
        "hint": "ลดลง = นักลงทุนหนีความเสี่ยง กลัวหนี้เสีย (มีข้อมูลตั้งแต่ 2007)",
        "kind": "ratio", "a": "HYG", "b": "LQD",
        "danger": "falling",
    },
    "housing": {
        "label": "หุ้นกลุ่มบ้าน / ตลาดรวม (ITB÷S&P500)",
        "hint": "ลดลงนำตลาด = ภาคอสังหาเริ่มมีปัญหาก่อน (มีข้อมูลตั้งแต่ 2006)",
        "kind": "ratio", "a": "ITB", "b": "^GSPC",
        "danger": "falling",
    },
    "banks": {
        "label": "หุ้นกลุ่มธนาคาร / ตลาดรวม (XLF÷S&P500)",
        "hint": "ลดลงนำตลาด = ระบบการเงินเริ่มตึงตัว",
        "kind": "ratio", "a": "XLF", "b": "^GSPC",
        "danger": "falling",
    },
}

LOOKBACKS = [180, 90, 30]   # ดูย้อนหลังกี่วันก่อนวิกฤตเริ่ม


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def _closes(symbol: str) -> dict:
    """{date: close} ย้อนหลังให้ยาวที่สุดเท่าที่มี"""
    cache_key = f"crisis:closes:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    h = stock_data.get_history(symbol, period="max")
    out = {c["date"]: c["close"] for c in h.get("candles", []) if c.get("close")}
    if out:
        cache_set(cache_key, out, 86400)
    return out


def _value_on(series: dict, day: str, tolerance: int = 10):
    """ค่าที่ใกล้วันที่ระบุที่สุด (เผื่อวันหยุด) — ไม่เกิน tolerance วัน"""
    if not series:
        return None
    try:
        d0 = dt.date.fromisoformat(day)
    except ValueError:
        return None
    for off in range(tolerance + 1):
        for sign in (0, -1, 1) if off else (0,):
            k = (d0 + dt.timedelta(days=off * sign)).isoformat()
            if k in series:
                return series[k]
    return None


def _shift(day: str, n: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def _indicator_series(cfg: dict) -> dict:
    """สร้าง time series ของตัวชี้วัด 1 ตัว"""
    a = _closes(cfg["a"])
    if not a:
        return {}
    if cfg["kind"] == "level":
        return a
    b = _closes(cfg["b"])
    if not b:
        return {}
    common = set(a) & set(b)
    if cfg["kind"] == "spread":
        return {d: a[d] - b[d] for d in common}
    return {d: (a[d] / b[d]) for d in common if b[d]}


# ---------------------------------------------------------------------------
# 1) วิกฤตแต่ละครั้งกระทบหุ้นที่เราถือแค่ไหน
# ---------------------------------------------------------------------------
def impact(ticker: str, benchmark: str = "^GSPC") -> dict:
    ticker = stock_data.normalize_ticker(ticker)
    px = _closes(ticker)
    bm = _closes(benchmark)
    if not px:
        return {"ok": False, "ticker": ticker,
                "error": "ดึงราคาย้อนหลังไม่ได้ (ตรวจสอบสัญลักษณ์/อินเทอร์เน็ต)"}

    first_day, last_day = min(px), max(px)
    rows = []
    for c in CRISES:
        # ต้องมีข้อมูลครอบคลุมทั้งช่วงวิกฤต ไม่ใช่แค่เริ่มก่อน
        if c["start"] < first_day:
            rows.append({**c, "covered": False,
                         "note_extra": f"หุ้นตัวนี้มีข้อมูลตั้งแต่ {first_day} — ยังไม่เกิด"})
            continue
        if c["start"] > last_day:
            rows.append({**c, "covered": False,
                         "note_extra": f"ข้อมูลราคาสิ้นสุด {last_day} ก่อนวิกฤตนี้"})
            continue

        dd = _drawdown(px, c["start"], c["trough"])
        if dd is None:
            rows.append({**c, "covered": False,
                         "note_extra": "ไม่มีราคาในช่วงวิกฤตนี้"})
            continue

        dd_bm = _drawdown(bm, c["start"], c["trough"])
        rec = _recovery_days(px, c["start"], c["trough"])
        partial = c["trough"] > last_day        # วิกฤตยังไม่จบในข้อมูลที่มี
        rows.append({
            **c, "covered": True,
            "partial": partial,
            "drawdown_pct": dd,
            "benchmark_drawdown_pct": dd_bm,
            "vs_market": round(dd - dd_bm, 1) if (dd is not None and dd_bm is not None) else None,
            "recovery_days": rec,
            "recovery_months": round(rec / 30.4, 1) if rec else None,
        })

    covered = [r for r in rows if r.get("covered") and r.get("drawdown_pct") is not None]
    worst = min(covered, key=lambda r: r["drawdown_pct"]) if covered else None
    avg_dd = round(float(np.mean([r["drawdown_pct"] for r in covered])), 1) if covered else None

    return {
        "ok": True,
        "ticker": ticker,
        "benchmark": benchmark,
        "data_from": first_day,
        "crises": rows,
        "covered_count": len(covered),
        "worst": worst,
        "avg_drawdown_pct": avg_dd,
        "summary": _impact_summary(ticker, covered, worst, avg_dd),
    }


def _drawdown(series: dict, start: str, trough: str):
    """ร่วงจากจุดเริ่มถึงจุดต่ำสุดกี่ % (หาค่าต่ำสุดจริงในช่วง)"""
    if not series:
        return None
    p0 = _value_on(series, start)
    if not p0:
        return None
    lows = [v for d, v in series.items() if start <= d <= trough and v]
    if not lows:
        return None
    return round((min(lows) / p0 - 1) * 100, 1)


def _recovery_days(series: dict, start: str, trough: str):
    """ใช้เวลากี่วันกลับมาเท่าราคาก่อนร่วง"""
    p0 = _value_on(series, start)
    if not p0:
        return None
    after = sorted(d for d in series if d > trough)
    for d in after:
        if series[d] >= p0:
            try:
                return (dt.date.fromisoformat(d) - dt.date.fromisoformat(start)).days
            except ValueError:
                return None
    return None      # ยังไม่ฟื้น


def _impact_summary(ticker, covered, worst, avg_dd):
    if not covered:
        return f"{ticker} ยังไม่มีข้อมูลย้อนหลังครอบคลุมวิกฤตใดเลย"
    parts = [f"{ticker} ผ่านวิกฤตมา {len(covered)} ครั้ง เฉลี่ยร่วง {avg_dd}%"]
    if worst:
        rec = (f"ใช้เวลาฟื้น {worst['recovery_months']} เดือน"
               if worst.get("recovery_months") else "ยังไม่ฟื้นกลับจุดเดิม")
        parts.append(f"หนักสุดคือ{worst['name']} ร่วง {worst['drawdown_pct']}% ({rec})")
    worse_than_market = [r for r in covered if (r.get("vs_market") or 0) < -5]
    if worse_than_market:
        parts.append(f"ร่วงแรงกว่าตลาดใน {len(worse_than_market)} จาก {len(covered)} ครั้ง")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# 2) สัญญาณเตือนล่วงหน้า — ก่อนวิกฤตหน้าตาเป็นยังไง แล้ววันนี้อยู่ตรงไหน
# ---------------------------------------------------------------------------
def warning_signals() -> dict:
    rows = []
    today = dt.date.today().isoformat()

    for key, cfg in WARNING_INDICATORS.items():
        ser = _indicator_series(cfg)
        if not ser:
            rows.append({"key": key, "label": cfg["label"], "hint": cfg["hint"],
                         "ok": False, "error": "ดึงข้อมูลไม่ได้"})
            continue

        days_sorted = sorted(ser)
        current = ser[days_sorted[-1]]
        first = days_sorted[0]

        # ค่าก่อนวิกฤตแต่ละครั้ง
        history = []
        for c in CRISES:
            if c["start"] < first:
                continue
            readings = {}
            for lb in LOOKBACKS:
                readings[f"d{lb}"] = _round(_value_on(ser, _shift(c["start"], -lb)))
            readings["at_start"] = _round(_value_on(ser, c["start"]))
            if any(v is not None for v in readings.values()):
                history.append({"crisis": c["name"], "cause": c["cause"],
                                "start": c["start"], **readings})

        pct = _percentile(ser, current)
        rows.append({
            "key": key, "label": cfg["label"], "hint": cfg["hint"],
            "ok": True,
            "current": _round(current),
            "as_of": days_sorted[-1],
            "data_from": first,
            "percentile": pct,
            "danger": _danger(cfg, current, ser),
            "before_crises": history,
        })

    return {"ok": True, "rows": rows, "lookbacks": LOOKBACKS,
            "generated_at": today,
            "caveat": ("วิกฤตในอดีตมีแค่ 8 ครั้งใน 25 ปี — ตัวอย่างน้อยมาก "
                       "สัญญาณเหล่านี้เคยเตือนถูกบ้างผิดบ้าง และเคยเตือนหลายครั้ง"
                       "ที่ไม่เกิดวิกฤตจริง ใช้เป็นบริบทประกอบ ไม่ใช่คำทำนาย")}


def _round(v, nd=3):
    return None if v is None else round(float(v), nd)


def _percentile(ser: dict, value) -> float:
    """ค่าปัจจุบันอยู่เปอร์เซ็นไทล์ที่เท่าไหร่ของประวัติทั้งหมด"""
    vals = [v for v in ser.values() if v is not None]
    if not vals or value is None:
        return None
    return round(float((np.asarray(vals) <= value).mean() * 100), 1)


def _danger(cfg, current, ser):
    """ตอนนี้อยู่ในโซนอันตรายไหม"""
    if current is None:
        return {"level": "unknown", "text": "—"}
    mode = cfg.get("danger")
    if mode == "below" and current < cfg.get("danger_level", 0):
        return {"level": "high", "text": "อยู่ในโซนเตือน (ติดลบ)"}
    if mode == "above" and current > cfg.get("danger_level", 99):
        return {"level": "high", "text": "อยู่ในโซนเตือน (สูงผิดปกติ)"}
    if mode == "falling":
        days_sorted = sorted(ser)
        past = _value_on(ser, _shift(days_sorted[-1], -90))
        if past and current < past * 0.95:
            return {"level": "medium", "text": "ลดลง >5% ใน 3 เดือน"}
    return {"level": "low", "text": "ยังปกติ"}


# ---------------------------------------------------------------------------
# 3) รวมทั้งสองอย่าง
# ---------------------------------------------------------------------------
def report(ticker: str = "") -> dict:
    out = {"ok": True, "signals": warning_signals(), "crises": CRISES}
    if ticker:
        out["impact"] = impact(ticker)
    return out
