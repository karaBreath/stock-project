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
import datetime as dt

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
def default_features():
    feats = [f"news:{k}" for k in Config.WORLD_THEMES]
    feats += [f"macro:{k}" for k in ("gold", "oil", "usdthb", "us10y", "dxy")]
    return feats


def analyze(ticker: str, days: int = None, features=None, lags=None, save: bool = True) -> dict:
    """
    หาความสัมพันธ์ระหว่าง feature ทั้งหมด กับผลตอบแทนของหุ้น 1 ตัว
    คืนผลเรียงตามความแรง (|r|) โดยกรองเฉพาะที่ข้อมูลพอ
    """
    ticker = stock_data.normalize_ticker(ticker)
    days = days or Config.LEARN_WINDOW_DAYS
    features = features or default_features()
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
            xs, ys = [], []
            for day, val in ser.items():
                fwd = rets.get(_shift_days(day, lag))
                if fwd is not None and val is not None:
                    xs.append(val)
                    ys.append(fwd)
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

    links.sort(key=lambda L: abs(L["r"]), reverse=True)
    solid = [L for L in links if L["enough_data"] and abs(L["r"]) >= 0.15]

    return {
        "ok": True,
        "ticker": ticker,
        "window_days": days,
        "tested": len(links),
        "links": links[:40],
        "top": solid[:8],
        "insights": _insights(ticker, solid),
        "min_samples": Config.LEARN_MIN_SAMPLES,
        "warning": (
            "ความสัมพันธ์ ≠ สาเหตุ · ยิ่งทดสอบหลายคู่ยิ่งเจอเรื่องบังเอิญ "
            f"(รอบนี้ทดสอบ {len(links)} คู่) — ใช้ประกอบการตัดสินใจเท่านั้น"
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
        tickers = Config.DEFAULT_TH_TICKERS[:5]
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
