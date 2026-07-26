"""
Correlation / Learning engine — "ตัวเรียนรู้"

เฝ้าดู 2 อย่างพร้อมกันแล้วหาจุดเชื่อม:
  1) ข่าวทั่วโลก (GDELT tone รายธีม)  2) ราคาหุ้น + ปัจจัยมหภาค

วิธีคิด
-------
- แปลงข่าวเป็น time series รายวัน (tone) และราคาเป็น "ผลตอบแทนรายวัน %"
- จับคู่กันตามวันที่ แล้วหา correlation ที่ lag ต่าง ๆ
    lag = 0  -> ข่าววันนี้ สัมพันธ์กับราคาวันนี้ (เกิดพร้อมกัน)
    lag = 1+ -> ข่าววันนี้ "นำ" ราคาอีก N วัน  <-- อันนี้แหละที่มีค่าในการเทรด
- เก็บผลลงตาราง correlations เพื่อสะสมความรู้ไว้ดูย้อนหลัง

ทำไมใช้ได้ตั้งแต่วันแรก
----------------------
GDELT ให้ timeline ย้อนหลังได้ถึง 1 ปี และ yfinance ให้ราคาย้อนหลังหลายปี
เครื่องจึงเรียนรู้จาก "อดีต" ได้ทันที ส่วนตาราง observations คือการสะสม
ข้อมูลสด ๆ เพิ่มขึ้นทุกวัน เพื่อให้แม่นขึ้นเรื่อย ๆ ในระยะยาว

⚠️ ข้อควรระวังทางสถิติ
- correlation ไม่ใช่ causation
- ยิ่งทดสอบหลายคู่ ยิ่งเจอความสัมพันธ์ "บังเอิญ" (multiple comparisons)
  จึงมีเกณฑ์ n ขั้นต่ำ + t-stat และแจ้งเตือนใน UI เสมอ
"""
import bisect
import datetime as dt
import math
from statistics import NormalDist

import numpy as np

from config import Config
from database import execute, query, obs_upsert, obs_series, obs_stats
from services import gdelt, stock_data


# ---------------------------------------------------------------------------
# ตัวช่วย: สร้าง time series
# ---------------------------------------------------------------------------
def _today() -> str:
    return dt.date.today().isoformat()


def _returns_series(ticker: str, days: int) -> dict:
    """คืน {day: ผลตอบแทน %} รายวันของหุ้น"""
    period = "2y" if days > 300 else ("1y" if days > 120 else "6mo")
    hist = stock_data.get_history(ticker, period=period)
    candles = [c for c in hist.get("candles", []) if c.get("close")]
    out = {}
    for i in range(1, len(candles)):
        prev, cur = candles[i - 1]["close"], candles[i]["close"]
        if prev:
            out[candles[i]["date"]] = (cur / prev - 1) * 100
    return out


def _feature_series(feature: str, days: int) -> dict:
    """
    คืน {day: value} ของ feature หนึ่งตัว
      'news:<theme>'   -> tone ข่าวจาก GDELT (ย้อนหลังได้)
      'volume:<theme>' -> ปริมาณข่าว
      'macro:<key>'    -> ผลตอบแทนรายวันของสินทรัพย์มหภาค
      'obs:<kind>:<key>' -> ข้อมูลที่สะสมไว้เองในตาราง observations
    """
    if feature.startswith("news:"):
        q = gdelt.theme_query(feature.split(":", 1)[1])
        return gdelt.tone_timeline(q, timespan=f"{days}d").get("series", {}) if q else {}

    if feature.startswith("volume:"):
        q = gdelt.theme_query(feature.split(":", 1)[1])
        return gdelt.volume_timeline(q, timespan=f"{days}d").get("series", {}) if q else {}

    if feature.startswith("macro:"):
        key = feature.split(":", 1)[1]
        sym = (Config.MACRO_SYMBOLS.get(key) or (None,))[0]
        return _returns_series(sym, days) if sym else {}

    if feature.startswith("obs:"):
        parts = feature.split(":", 2)
        if len(parts) == 3:
            since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
            return obs_series(parts[1], parts[2], since_day=since)

    return {}


def _shift_days(day: str, n: int) -> str:
    try:
        return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()
    except ValueError:
        return day


def align(ser: dict, rets: dict, lag: int, allowed_days=None):
    """
    จับคู่ค่า feature กับผลตอบแทนล่วงหน้า lag **วันทำการ**

    ทำไมต้องนับวันทำการ ไม่ใช่วันปฏิทิน
    ---------------------------------
    ข่าวมีทุกวันรวมเสาร์อาทิตย์ แต่ราคามีเฉพาะวันทำการ
    ถ้าบวกวันปฏิทินตรง ๆ:
      - ข่าววันศุกร์ + 3 วัน = วันจันทร์ = ห่างแค่ 1 วันทำการ (ไม่ใช่ 3)
      - ข่าววันพุธ + 3 วัน = วันเสาร์ = ไม่มีราคา ตัวอย่างถูกทิ้ง
    ผลคือ lag เดียวกันปนกันหลายระยะ ทำให้ความสัมพันธ์เบลอและ n น้อยลง

    วิธีแก้: หาวันทำการแรกที่ >= วันของข่าว แล้วเลื่อนไปอีก lag ตำแหน่ง
    """
    ret_days = sorted(rets)
    xs, ys = [], []
    for day, val in ser.items():
        if val is None:
            continue
        if allowed_days is not None and day not in allowed_days:
            continue
        pos = bisect.bisect_left(ret_days, day)
        j = pos + lag
        if 0 <= j < len(ret_days):
            xs.append(val)
            ys.append(rets[ret_days[j]])
    return xs, ys


# ---------------------------------------------------------------------------
# สถิติ
# ---------------------------------------------------------------------------
def _pearson(x, y):
    """คืน (r, t_stat) — ไม่ต้องพึ่ง scipy"""
    n = len(x)
    if n < 3:
        return None, None
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if np.std(x) == 0 or np.std(y) == 0:
        return None, None
    r = float(np.corrcoef(x, y)[0, 1])
    if np.isnan(r):
        return None, None
    denom = max(1e-9, 1 - r * r)
    t = float(r * np.sqrt(max(0, n - 2) / denom))
    return r, t


def _hit_rate(feat_vals, ret_vals, direction):
    """
    ในวันที่สัญญาณ "แรง" (top/bottom tercile ตามทิศของ r)
    มีกี่ % ที่ผลตอบแทนล่วงหน้าไปในทิศที่คาด
    """
    if len(feat_vals) < 9:
        return None
    f = np.asarray(feat_vals, dtype=float)
    y = np.asarray(ret_vals, dtype=float)
    if direction >= 0:
        mask = f >= np.quantile(f, 2 / 3)      # ข่าวดีผิดปกติ -> คาดว่าราคาขึ้น
        wins = y[mask] > 0
    else:
        mask = f <= np.quantile(f, 1 / 3)      # ข่าวแย่ผิดปกติ -> คาดว่าราคาขึ้น (r ติดลบ)
        wins = y[mask] > 0
    if wins.size < 3:
        return None
    return float(np.mean(wins) * 100)


def _critical_r(n_samples: int, n_tests: int, alpha: float = 0.05) -> float:
    """
    เกณฑ์ |r| ขั้นต่ำที่จะถือว่า "ไม่ใช่ความบังเอิญ" เมื่อทดสอบ n_tests คู่พร้อมกัน

    ใช้ Bonferroni: ยิ่งทดสอบหลายคู่ ยิ่งต้องเข้มขึ้น
    เช่น ทดสอบ 80 คู่ ด้วยข้อมูล 150 วัน -> ต้องได้ |r| ≳ 0.28 ถึงจะเชื่อได้
    (ถ้าใช้เกณฑ์หลวม ๆ 0.15 จะมีคู่ที่ "ดูใช่" โผล่มาเพราะบังเอิญราว 4 คู่)
    """
    if n_samples < 5 or n_tests < 1:
        return 1.0
    a = min(0.5, alpha / n_tests)
    try:
        z = NormalDist().inv_cdf(1 - a / 2)
    except Exception:
        z = 3.5
    return min(0.99, z / math.sqrt(n_samples))


def _strength(r, n, t):
    """แปลผลเป็นภาษาคน แบบระมัดระวัง"""
    if r is None or n < Config.LEARN_MIN_SAMPLES:
        return "ข้อมูลยังน้อย"
    a = abs(r)
    if a >= 0.35 and abs(t) >= 2.5:
        return "ชัดเจน"
    if a >= 0.20 and abs(t) >= 2.0:
        return "พอมีนัย"
    if a >= 0.10:
        return "อ่อน"
    return "แทบไม่มี"


# ---------------------------------------------------------------------------
# วิเคราะห์หลัก
# ---------------------------------------------------------------------------
def default_features(ticker: str = ""):
    """
    รายการสัญญาณที่จะเอามาทดสอบกับหุ้น 1 ตัว
    หุ้น/กองทุนสหรัฐ กับหุ้นไทย สนใจปัจจัยมหภาคคนละชุด
    """
    feats = [f"news:{k}" for k in Config.WORLD_THEMES]
    if (ticker or "").upper().endswith(".BK"):
        macro = ("usdthb", "gold", "oil", "us10y", "dxy", "sp500")
    else:
        macro = ("vix", "us10y", "dxy", "nasdaq", "semis", "oil", "gold")
    feats += [f"macro:{k}" for k in macro]
    return feats


def analyze(ticker: str, days: int = None, features=None, lags=None, save: bool = True) -> dict:
    """
    หาความสัมพันธ์ระหว่าง feature ทั้งหมด กับผลตอบแทนของหุ้น 1 ตัว
    คืนผลเรียงตามความแรง (|r|) โดยกรองเฉพาะที่ข้อมูลพอ
    """
    ticker = stock_data.normalize_ticker(ticker)
    days = days or Config.LEARN_WINDOW_DAYS
    features = features or default_features(ticker)
    lags = lags or Config.LEARN_LAGS

    rets = _returns_series(ticker, days)
    if len(rets) < 10:
        return {"ok": False, "ticker": ticker,
                "error": "ข้อมูลราคาย้อนหลังไม่พอ", "links": []}

    links = []
    for feat in features:
        ser = _feature_series(feat, days)
        if len(ser) < 10:
            continue
        for lag in lags:
            xs, ys = align(ser, rets, lag)
            n = len(xs)
            if n < 10:
                continue
            r, t = _pearson(xs, ys)
            if r is None:
                continue
            hit = _hit_rate(xs, ys, 1 if r >= 0 else -1)
            links.append({
                "feature": feat,
                "label": _feature_label(feat),
                "lag": lag,
                "r": round(r, 3),
                "n": n,
                "t_stat": round(t, 2) if t is not None else None,
                "hit_rate": round(hit, 1) if hit is not None else None,
                "strength": _strength(r, n, t or 0),
                "direction": "บวก" if r >= 0 else "ลบ",
                "enough_data": n >= Config.LEARN_MIN_SAMPLES,
            })
            if save:
                _save_link(ticker, feat, lag, r, n, t, hit, days)

    # ---- กันผลบังเอิญจากการทดสอบหลายคู่พร้อมกัน (Bonferroni) ----
    n_tests = max(1, len(links))
    for L in links:
        crit = _critical_r(L["n"], n_tests)
        L["critical_r"] = round(crit, 3)
        L["significant"] = bool(L["enough_data"] and abs(L["r"]) >= crit)

    links.sort(key=lambda L: abs(L["r"]), reverse=True)
    solid = [L for L in links if L["significant"]]
    avg_crit = round(sum(L["critical_r"] for L in links) / n_tests, 3) if links else None

    return {
        "ok": True,
        "ticker": ticker,
        "window_days": days,
        "tested": len(links),
        "links": links[:40],
        "top": solid[:8],
        "significant_count": len(solid),
        "critical_r": avg_crit,
        "insights": _insights(ticker, solid),
        "min_samples": Config.LEARN_MIN_SAMPLES,
        "warning": (
            f"ทดสอบ {len(links)} คู่พร้อมกัน — ถ้าไม่แก้อะไรเลยจะมีคู่ที่ 'ดูใช่' "
            f"โผล่มาเพราะบังเอิญราว {round(len(links) * 0.05)} คู่ "
            f"จึงยกเกณฑ์เป็น |r| ≥ {avg_crit} (Bonferroni) เหลือผ่าน {len(solid)} คู่ · "
            "ความสัมพันธ์ ≠ สาเหตุ ใช้ประกอบการตัดสินใจเท่านั้น"
        ),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _feature_label(feat: str) -> str:
    if feat.startswith("news:"):
        k = feat.split(":", 1)[1]
        t = Config.WORLD_THEMES.get(k)
        return f"ข่าว: {t[0]}" if t else feat
    if feat.startswith("volume:"):
        k = feat.split(":", 1)[1]
        t = Config.WORLD_THEMES.get(k)
        return f"ปริมาณข่าว: {t[0]}" if t else feat
    if feat.startswith("macro:"):
        k = feat.split(":", 1)[1]
        m = Config.MACRO_SYMBOLS.get(k)
        return f"มหภาค: {m[1]}" if m else feat
    return feat


def _insights(ticker: str, solid) -> list:
    """แปลผลเป็นประโยคที่เอาไปใช้เทรดได้จริง"""
    out = []
    for L in solid[:5]:
        lag = L["lag"]
        when = "วันเดียวกัน" if lag == 0 else f"อีก {lag} วันข้างหน้า"
        if L["r"] >= 0:
            move = "มักขึ้น"
            cond = "ดีขึ้น"
        else:
            move = "มักลง"
            cond = "ดีขึ้น"
        hit = f" · แม่น {L['hit_rate']}%" if L["hit_rate"] is not None else ""
        out.append(
            f"เมื่อ{L['label']} {cond} → {ticker} {move}{' ' + when if lag else ''}"
            f" (r={L['r']}, n={L['n']}{hit}, {L['strength']})"
        )
    if not out:
        out.append("ยังไม่พบความสัมพันธ์ที่ชัดพอ — ลองขยายช่วงเวลา หรือรอสะสมข้อมูลเพิ่ม")
    return out


def _save_link(ticker, feature, lag, r, n, t, hit, window):
    execute(
        "INSERT INTO correlations(target, feature, lag, r, n, t_stat, hit_rate, window_days) "
        "VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(target, feature, lag) DO UPDATE SET "
        "r=excluded.r, n=excluded.n, t_stat=excluded.t_stat, hit_rate=excluded.hit_rate, "
        "window_days=excluded.window_days, updated_at=strftime('%s','now')",
        (ticker, feature, lag, r, n, t, hit, window),
    )


# ---------------------------------------------------------------------------
# Snapshot — เก็บข้อมูลสดสะสมทุกวัน
# ---------------------------------------------------------------------------
def snapshot() -> dict:
    """
    เก็บภาพนิ่งของ "โลก ณ วันนี้" ลงตาราง observations
    เรียกได้บ่อยเท่าไหร่ก็ได้ — ข้อมูลวันเดียวกันจะทับของเดิม
    """
    day = _today()
    saved = {"news": 0, "macro": 0, "price": 0}

    # 1) tone ข่าวโลกรายธีม
    sig = gdelt.theme_signals(timespan="7d")
    for row in sig.get("rows", []):
        if row.get("tone") is not None:
            obs_upsert(day, "news", row["key"], row["tone"], {"label": row["label"]})
            saved["news"] += 1

    # 2) ปัจจัยมหภาค
    for key, (symbol, label) in Config.MACRO_SYMBOLS.items():
        q = stock_data.get_quote(symbol)
        if q.get("ok") and q.get("price") is not None:
            obs_upsert(day, "macro", key, q["price"],
                       {"label": label, "change_pct": q.get("change_pct")})
            saved["macro"] += 1

    # 3) ราคาหุ้นที่เราสนใจ (watchlist + พอร์ต)
    for t in _tracked_tickers():
        q = stock_data.get_quote(t)
        if q.get("ok") and q.get("price") is not None:
            obs_upsert(day, "price", t, q["price"], {"change_pct": q.get("change_pct")})
            saved["price"] += 1

    return {"ok": True, "day": day, "saved": saved, "stats": obs_stats()}


def _tracked_tickers(limit: int = 30):
    rows = query(
        "SELECT ticker FROM watchlist "
        "UNION SELECT ticker FROM holdings LIMIT ?", (limit,)
    )
    tickers = [r["ticker"] for r in rows if r.get("ticker")]
    if not tickers:
        tickers = Config.DEFAULT_US_TICKERS[:5]   # เน้นตลาดสหรัฐเป็นหลัก
    return tickers


# ---------------------------------------------------------------------------
# สรุปสิ่งที่เรียนรู้แล้ว
# ---------------------------------------------------------------------------
def learned(target: str = "", limit: int = 50) -> dict:
    """ดูความสัมพันธ์ที่เครื่องเรียนรู้เก็บไว้ (เรียงตามความแรง)"""
    sql = ("SELECT * FROM correlations WHERE n >= ? ")
    params = [Config.LEARN_MIN_SAMPLES]
    if target:
        sql += "AND target = ? "
        params.append(stock_data.normalize_ticker(target))
    sql += "ORDER BY ABS(r) DESC LIMIT ?"
    params.append(limit)

    rows = query(sql, tuple(params))
    for r in rows:
        r["label"] = _feature_label(r["feature"])
        r["strength"] = _strength(r["r"], r["n"], r["t_stat"] or 0)
    return {
        "ok": True,
        "rows": rows,
        "stats": obs_stats(),
        "min_samples": Config.LEARN_MIN_SAMPLES,
    }


# ---------------------------------------------------------------------------
# นำความรู้ที่เรียนได้ มาใช้กับ "ตอนนี้"  → ป้อนเข้าคะแนนรวม 0-100
# ---------------------------------------------------------------------------
CATALYST_MIN_R = 0.15      # ความสัมพันธ์อ่อนกว่านี้ไม่เอามาใช้
CATALYST_MIN_T = 3.3       # กันผลบังเอิญจากการทดสอบ ~80 คู่ (Bonferroni)
CATALYST_MAX_ADJUST = 10   # ปรับคะแนนรวมได้มากสุด ±10 คะแนน


def catalyst_signal(ticker: str) -> dict:
    """
    ดูว่า "ข่าวโลกตอนนี้" กำลังส่งสัญญาณอะไรกับหุ้นตัวนี้
    โดยใช้เฉพาะความสัมพันธ์ที่เรียนรู้ไว้แล้วและผ่านเกณฑ์ (n พอ + |r| พอ + lag ≥ 1)

    lag ≥ 1 เท่านั้น เพราะเราต้องการสัญญาณที่ "นำ" ราคา — ถ้า lag=0 คือ
    ข่าวกับราคาขยับพร้อมกัน เอามาทำนายอนาคตไม่ได้

    คืน adjust = คะแนนที่ควรบวก/ลบจากคะแนนรวม (จำกัด ±10)
    """
    ticker = stock_data.normalize_ticker(ticker)
    # เงื่อนไข: ข้อมูลพอ (n) + แรงพอ (|r|) + ผ่านเกณฑ์กันบังเอิญ (|t|) + นำราคาได้ (lag≥1)
    rows = query(
        "SELECT * FROM correlations "
        "WHERE target=? AND n>=? AND ABS(r)>=? AND ABS(COALESCE(t_stat,0))>=? AND lag>=1 "
        "ORDER BY ABS(r) DESC LIMIT 12",
        (ticker, Config.LEARN_MIN_SAMPLES, CATALYST_MIN_R, CATALYST_MIN_T),
    )
    if not rows:
        learned_any = query("SELECT 1 FROM correlations WHERE target=? LIMIT 1",
                            (ticker,), one=True)
        return {"ok": False, "ticker": ticker, "score": 50, "adjust": 0,
                "reasons": [], "used": 0,
                "hint": ("เรียนรู้แล้ว แต่ยังไม่พบความสัมพันธ์ที่แรงพอจะเชื่อได้ "
                         "— ไม่ปรับคะแนน (ดีกว่าเดาจากสัญญาณอ่อน)")
                if learned_any else
                "ยังไม่ได้เรียนรู้หุ้นตัวนี้ — เปิดเมนูเครื่องเรียนรู้แล้วกดวิเคราะห์"}

    # สภาพข่าวโลก ณ ตอนนี้ (deviation = ต่างจากค่าเฉลี่ย 7 วัน)
    signals = {r["key"]: r for r in gdelt.theme_signals(timespan="7d").get("rows", [])}

    num = den = 0.0
    reasons = []
    used = 0

    for row in rows:
        feat = row["feature"]
        dev = _current_deviation(feat, signals)
        if dev is None:
            continue
        r = row["r"]
        weight = abs(r)
        contrib = r * dev              # ทิศทางที่คาดว่าราคาจะไป (-1..+1 คร่าว ๆ)
        num += weight * contrib
        den += weight
        used += 1

        if abs(contrib) >= 0.08:
            direction = "หนุน" if contrib > 0 else "กดดัน"
            state = "ดีขึ้น" if dev > 0 else "แย่ลง"
            reasons.append({
                "label": _feature_label(feat),
                "state": state,
                "effect": direction,
                "lag": row["lag"],
                "r": round(r, 3),
                "n": row["n"],
                "contribution": round(contrib, 3),
                "text": (f"{_feature_label(feat)} {state} → {direction} {ticker} "
                         f"อีก {row['lag']} วัน (r={round(r, 3)}, n={row['n']})"),
            })

    if not den:
        return {"ok": False, "ticker": ticker, "score": 50, "adjust": 0,
                "reasons": [], "used": 0,
                "hint": "ยังดึงสภาพข่าวโลกตอนนี้ไม่ได้"}

    expected = num / den                                   # -1..+1
    expected = max(-1.0, min(1.0, expected))
    adjust = round(expected * CATALYST_MAX_ADJUST, 1)
    score = int(max(0, min(100, round(50 + expected * 50))))

    reasons.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return {
        "ok": True,
        "ticker": ticker,
        "score": score,
        "adjust": adjust,
        "expected": round(expected, 3),
        "used": used,
        "reasons": reasons[:4],
        "label": ("ข่าวโลกหนุน" if adjust >= 2 else
                  "ข่าวโลกกดดัน" if adjust <= -2 else "ข่าวโลกเป็นกลาง"),
    }


def _current_deviation(feature: str, signals: dict):
    """
    สภาพปัจจุบันของ feature เทียบค่าปกติ → normalize เป็นราว -1..+1
      news:<theme> ใช้ tone เทียบค่าเฉลี่ย 7 วัน
      macro:<key>  ใช้ % เปลี่ยนแปลงวันนี้
    """
    if feature.startswith("news:"):
        key = feature.split(":", 1)[1]
        row = signals.get(key)
        if not row or row.get("deviation") is None:
            return None
        return max(-1.0, min(1.0, row["deviation"] / 1.5))

    if feature.startswith("macro:"):
        key = feature.split(":", 1)[1]
        sym = (Config.MACRO_SYMBOLS.get(key) or (None,))[0]
        if not sym:
            return None
        q = stock_data.get_quote(sym)
        chg = q.get("change_pct")
        if chg is None:
            return None
        return max(-1.0, min(1.0, chg / 2.0))

    return None


def learn_watchlist(days: int = None, limit: int = 15) -> dict:
    """
    สั่งให้เครื่องเรียนรู้หุ้นใน watchlist + พอร์ต ทีเดียวทั้งหมด
    (ใช้ตอนเริ่มต้น เพื่อให้คะแนนรวมมีข้อมูลข่าวโลกใช้ทันที)
    """
    days = days or Config.LEARN_WINDOW_DAYS
    tickers = _tracked_tickers(limit)
    done = []
    for t in tickers:
        try:
            res = analyze(t, days=days)
            done.append({"ticker": t, "ok": res.get("ok", False),
                         "found": len(res.get("top", []))})
        except Exception as e:
            done.append({"ticker": t, "ok": False, "error": str(e)})
    return {"ok": True, "learned": done, "count": len(done), "stats": obs_stats()}


def status() -> dict:
    """สถานะคลังข้อมูล — ใช้โชว์ว่า 'เก็บมาแล้วเท่าไหร่'"""
    st = obs_stats()
    total_corr = query("SELECT COUNT(*) AS c FROM correlations", one=True) or {"c": 0}
    strong = query(
        "SELECT COUNT(*) AS c FROM correlations WHERE n >= ? AND ABS(r) >= 0.2",
        (Config.LEARN_MIN_SAMPLES,), one=True) or {"c": 0}
    return {
        "ok": True,
        "observations": st,
        "correlations": total_corr.get("c", 0),
        "strong_links": strong.get("c", 0),
        "auto": Config.LEARN_AUTO,
        "interval_sec": Config.LEARN_INTERVAL,
        "window_days": Config.LEARN_WINDOW_DAYS,
        "min_samples": Config.LEARN_MIN_SAMPLES,
    }
