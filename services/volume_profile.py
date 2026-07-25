"""
Volume Profile engine — พอร์ตแนวคิดจาก volume-edge มาเป็น "อาวุธ" ให้ NEBULA

ทำอะไร
------
1) สร้าง composite Volume Profile จากราคาย้อนหลัง
   - กระจาย volume ของแต่ละแท่งตามช่วง high-low (ไม่มี tick data
     จึงแม่นระดับ "โซน" ไม่ใช่ระดับ tick — ตรงกับข้อจำกัดของ volume-edge)
   - POC (Point of Control) = ราคาที่มี volume หนาแน่นสุด
   - Value Area 70% (วิธี CBOT ขยายจาก POC)
   - HVN / LVN = โซน volume หนา / บาง
2) จับ setup แบบ long-only (ต้องยืนเหนือ SMA200) 2 แบบ:
   - VAB : เบรกขอบบน Value Area พร้อมการยอมรับราคา + volume
   - VAR : แหย่ใต้ขอบล่างแล้วโดนแรงซื้อดันกลับเข้า VA (เป้า POC)
   - LVN : ปิดไว้ (volume-edge backtest ขาดทุน จึงไม่ทำ)
3) ให้จุด entry / stop / target จากโครงสร้าง VP (แม่นกว่า ATR ล้วน)
   + เหตุผลภาษาไทย (ตามปรัชญา volume-edge: ทุกอย่างอธิบายได้)

⚠️ ความซื่อสัตย์: backtest ของ volume-edge เอง VAB +0.019R/ไม้, VAR +0.029R/ไม้
(แทบเสมอตัว และแพ้ถือ SPY เฉย ๆ) — เครื่องมือนี้ช่วยเรื่องวินัย + จังหวะ +
คำอธิบาย ไม่ใช่สัญญาว่ารวย
"""
import numpy as np
import pandas as pd

from services import stock_data, technical


# ตัวเลขอ้างอิงจาก backtest ของ volume-edge (โชว์ใน UI เพื่อความซื่อสัตย์)
SETUP_EXPECTANCY = {
    "VAB": {"oos_r": 0.019, "n": 1193, "note": "เบรกขอบบน Value Area"},
    "VAR": {"oos_r": 0.029, "n": 612, "note": "เด้งกลับจากขอบล่าง"},
    "LVN": {"oos_r": -0.484, "n": 34, "note": "ปิด — backtest ขาดทุน", "gated": True},
}

VALUE_AREA_PCT = 0.70     # Value Area = 70% ของ volume รอบ POC
DEFAULT_BINS = 60         # จำนวนช่องราคาในโปรไฟล์
LOOKBACK_DAYS = 20        # composite VP กี่วัน (ตาม volume-edge)


# ---------------------------------------------------------------------------
# 1) สร้าง Volume Profile
# ---------------------------------------------------------------------------
def _distribute_volume(df: pd.DataFrame, bins: int):
    """
    กระจาย volume ของแต่ละแท่งตามช่วง high-low ลงในช่องราคา
    คืน (bin_centers, bin_volumes, lo, hi, bin_size)
    """
    lo = float(df["low"].min())
    hi = float(df["high"].max())
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return None

    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    vol = np.zeros(bins)
    bin_size = (hi - lo) / bins

    for _, row in df.iterrows():
        h, l, v = row["high"], row["low"], row["volume"]
        if not (np.isfinite(h) and np.isfinite(l) and np.isfinite(v)) or v <= 0:
            continue
        if h <= l:
            # แท่งไม่มีช่วง -> ใส่ทั้งก้อนในช่องเดียว
            k = min(bins - 1, max(0, int((l - lo) / bin_size)))
            vol[k] += v
            continue
        # ช่วงของแท่งครอบช่องไหนบ้าง แล้วกระจายตามสัดส่วนที่ทับ
        lo_idx = max(0, int((l - lo) / bin_size))
        hi_idx = min(bins - 1, int((h - lo) / bin_size))
        span = h - l
        for k in range(lo_idx, hi_idx + 1):
            overlap = min(h, edges[k + 1]) - max(l, edges[k])
            if overlap > 0:
                vol[k] += v * (overlap / span)

    return centers, vol, lo, hi, bin_size


def _value_area(centers, vol, poc_idx):
    """
    ขยายจาก POC ขึ้น/ลง เลือกฝั่งที่ volume มากกว่า จนได้ 70% (วิธี CBOT)
    คืน (val, vah) = ขอบล่าง/บนของ Value Area
    """
    total = vol.sum()
    if total <= 0:
        return None, None
    target = total * VALUE_AREA_PCT
    acc = vol[poc_idx]
    lo_i = hi_i = poc_idx
    n = len(vol)

    while acc < target and (lo_i > 0 or hi_i < n - 1):
        # volume ที่จะได้ถ้าขยายลง 1 ช่อง vs ขึ้น 1 ช่อง (มองทีละ 2 ช่องแบบ CBOT)
        down = vol[lo_i - 1] if lo_i > 0 else -1
        up = vol[hi_i + 1] if hi_i < n - 1 else -1
        if up >= down:
            hi_i += 1
            acc += max(0, up)
        else:
            lo_i -= 1
            acc += max(0, down)

    return float(centers[lo_i]), float(centers[hi_i])


def _nodes(centers, vol):
    """หา HVN (จุดสูงสุดเฉพาะที่) และ LVN (จุดต่ำสุดเฉพาะที่)"""
    hvn, lvn = [], []
    mean = vol.mean()
    for i in range(1, len(vol) - 1):
        if vol[i] >= vol[i - 1] and vol[i] >= vol[i + 1] and vol[i] > mean:
            hvn.append(float(centers[i]))
        if vol[i] <= vol[i - 1] and vol[i] <= vol[i + 1] and vol[i] < mean * 0.6:
            lvn.append(float(centers[i]))
    return hvn, lvn


def build_profile(ticker: str, days: int = LOOKBACK_DAYS,
                  interval: str = "30m", bins: int = DEFAULT_BINS) -> dict:
    """
    สร้าง Volume Profile ของหุ้น 1 ตัว
    พยายามใช้ข้อมูล intraday 30m (ตรงกับ volume-edge) ถ้าไม่ได้ถอยไปใช้รายวัน
    """
    ticker = stock_data.normalize_ticker(ticker)
    out = {"ticker": ticker, "ok": False}

    df = _load(ticker, days, interval)
    if df is None or len(df) < 10:
        out["error"] = "ข้อมูลราคาไม่พอสำหรับสร้าง Volume Profile"
        return out

    res = _distribute_volume(df, bins)
    if res is None:
        out["error"] = "คำนวณ Volume Profile ไม่ได้ (ช่วงราคาผิดปกติ)"
        return out
    centers, vol, lo, hi, bin_size = res

    poc_idx = int(np.argmax(vol))
    poc = float(centers[poc_idx])
    val, vah = _value_area(centers, vol, poc_idx)
    hvn, lvn = _nodes(centers, vol)

    out.update({
        "ok": True,
        "interval": df.attrs.get("interval", interval),
        "bars": len(df),
        "price": float(df["close"].iloc[-1]),
        "poc": poc,
        "val": val,          # Value Area Low
        "vah": vah,          # Value Area High
        "hvn": hvn,
        "lvn": lvn,
        "range": {"low": lo, "high": hi},
        "histogram": [
            {"price": round(float(centers[i]), 2), "volume": float(vol[i])}
            for i in range(len(centers))
        ],
        "poc_volume": float(vol[poc_idx]),
    })
    return out


def _load(ticker, days, interval):
    """โหลดราคา — ลอง intraday ก่อน ถ้าล้มถอยไปรายวัน"""
    period_intraday = "60d" if days <= 60 else "60d"
    for iv, period in ((interval, period_intraday), ("1d", f"{max(days, 60)}d"), ("1d", "6mo")):
        h = stock_data.get_history(ticker, period=period, interval=iv)
        df = technical._series(h)
        if df.empty or "volume" not in df.columns:
            continue
        # เอาเฉพาะช่วง N วันล่าสุด (intraday จะมีหลายแท่งต่อวัน)
        if "date" in df.columns:
            keep_days = sorted(df["date"].unique())[-days:]
            df = df[df["date"].isin(keep_days)]
        df = df.dropna(subset=["high", "low", "volume"]).reset_index(drop=True)
        if len(df) >= 10:
            df.attrs["interval"] = iv
            return df
    return None


# ---------------------------------------------------------------------------
# 2) จับ setup (long-only, เหนือ SMA200)
# ---------------------------------------------------------------------------
def detect_setup(ticker: str) -> dict:
    """
    ดูว่าตอนนี้หุ้นเข้าเงื่อนไข setup VAB หรือ VAR ไหม
    คืนสัญญาณ + จุดเข้า/ตัดขาดทุน/เป้า จากโครงสร้าง VP + เหตุผลไทย
    """
    prof = build_profile(ticker)
    if not prof.get("ok"):
        return {"ok": False, "ticker": ticker, "setup": None,
                "error": prof.get("error")}

    # ต้องมีเทรนด์ขาขึ้น (ยืนเหนือ SMA200) — long-only ตาม volume-edge
    daily = technical._series(stock_data.get_history(ticker, period="2y", interval="1d"))
    trend_ok, sma200 = _above_sma200(daily)

    price = prof["price"]
    poc, val, vah = prof["poc"], prof["val"], prof["vah"]
    atr_val = _atr_value(daily)

    result = {
        "ok": True, "ticker": ticker, "setup": None,
        "price": price, "poc": poc, "val": val, "vah": vah,
        "trend_ok": trend_ok, "sma200": sma200,
        "profile": prof,
    }

    if not trend_ok:
        result["evidence"] = f"ราคายังไม่ยืนเหนือ SMA200 ({_fmt(sma200)}) — " \
                             "ระบบเป็น long-only จึงยังไม่เข้าเงื่อนไข"
        return result
    if val is None or vah is None:
        result["evidence"] = "คำนวณ Value Area ไม่ได้"
        return result

    va_width = vah - val
    near = va_width * 0.15 if va_width > 0 else price * 0.01

    setup = None
    evidence = []

    # ---- VAB: เบรกเหนือ VAH ----
    if price >= vah - near:
        acc = price > vah                              # การยอมรับราคา (ปิดเหนือขอบ)
        vol_ok = _recent_volume_surge(daily)
        if price > vah and vol_ok:
            setup = "VAB"
            evidence.append(f"ราคา {_fmt(price)} เบรกเหนือขอบบน Value Area "
                            f"(VAH {_fmt(vah)}) พร้อม volume หนาแน่นกว่าปกติ")
            evidence.append("= ตลาดยอมรับราคาเหนือโซนสมดุล มีโอกาสวิ่งต่อหา HVN ฝั่งบน")
        else:
            evidence.append(f"ราคาใกล้ขอบบน VAH {_fmt(vah)} แต่ยัง"
                            f"{'ไม่มี volume ยืนยัน' if not vol_ok else 'ไม่ปิดเหนือขอบชัดเจน'}"
                            " — รอการยืนยัน")

    # ---- VAR: แหย่ใต้ VAL แล้วเด้งกลับ ----
    elif _poked_below_and_recovered(daily, val):
        setup = "VAR"
        evidence.append(f"ราคาเคยแหย่ใต้ขอบล่าง Value Area (VAL {_fmt(val)}) "
                        f"แล้วถูกแรงซื้อดันกลับเข้าโซน")
        evidence.append(f"= ผู้ขายหมดแรงในโซนราคาถูก มีโอกาสเด้งกลับหา POC {_fmt(poc)}")
    else:
        evidence.append(f"ราคา {_fmt(price)} อยู่กลาง Value Area "
                        f"({_fmt(val)}–{_fmt(vah)}) ยังไม่เข้าเงื่อนไข setup")

    result["setup"] = setup
    result["evidence"] = " · ".join(evidence)
    if setup:
        result["levels"] = _levels(setup, price, poc, val, vah, prof["hvn"], atr_val)
        result["expectancy"] = SETUP_EXPECTANCY[setup]
    return result


def _levels(setup, price, poc, val, vah, hvn, atr_val):
    """จุด entry/stop/target จากโครงสร้าง VP (ไม่ใช่ ATR ล้วน)"""
    atr_val = atr_val or price * 0.02
    if setup == "VAB":
        entry = round(price, 2)
        # stop ใต้จุดเบรก (VAH) เล็กน้อย — ถ้าหลุดกลับเข้า VA คือเบรกล้มเหลว
        # ไม่ลงลึกถึง POC เพราะจะทำให้ R:R แย่โดยไม่จำเป็น
        stop = round(vah - 0.5 * atr_val, 2)
        highs = sorted(h for h in hvn if h > price)
        target = round(highs[0] if highs else price + 2 * atr_val, 2)
    else:  # VAR
        entry = round(price, 2)
        stop = round(val - 1.0 * atr_val, 2)               # หลุด VAL ลงไปอีก = ผิดทาง
        target = round(poc, 2)                              # เป้าคือ POC
    risk = entry - stop
    reward = target - entry
    rr = round(reward / risk, 2) if risk > 0 else None
    return {"entry": entry, "stop_loss": stop, "target": target,
            "risk_reward": rr, "basis": "volume_profile"}


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------
def _above_sma200(daily: pd.DataFrame):
    if daily.empty or len(daily) < 200:
        return False, None
    s200 = technical.sma(daily["close"], 200)
    v = technical._last(s200)
    price = float(daily["close"].iloc[-1])
    return (price > v if v else False), (round(v, 2) if v else None)


def _atr_value(daily: pd.DataFrame):
    if daily.empty or len(daily) < 15:
        return None
    return technical._last(technical.atr(daily))


def _recent_volume_surge(daily: pd.DataFrame, mult: float = 1.2):
    """volume ล่าสุดสูงกว่าค่าเฉลี่ย 20 วัน x mult ไหม"""
    if daily.empty or len(daily) < 21 or "volume" not in daily.columns:
        return False
    v = daily["volume"]
    return float(v.iloc[-1]) > float(v.iloc[-21:-1].mean()) * mult


def _poked_below_and_recovered(daily: pd.DataFrame, val, window: int = 5):
    """ใน N วันล่าสุด: เคยมี low ต่ำกว่า VAL แต่ตอนนี้ปิดกลับเหนือ VAL"""
    if daily.empty or len(daily) < window or val is None:
        return False
    recent = daily.iloc[-window:]
    poked = (recent["low"] < val).any()
    recovered = float(daily["close"].iloc[-1]) > val
    return bool(poked and recovered)


def _fmt(v):
    return "—" if v is None else f"{v:,.2f}"


def _score_component(ticker: str) -> dict:
    """
    แปลง setup เป็น 'คะแนนเสริม' แบบมีเพดาน สำหรับป้อนเข้าคะแนนรวม 0-100
    ไม่มี setup = 0 (ไม่แตะคะแนนเดิม) เหมือน catalyst
    """
    try:
        s = detect_setup(ticker)
    except Exception as e:
        return {"ok": False, "adjust": 0, "setup": None, "error": str(e)}
    if not s.get("ok") or not s.get("setup"):
        return {"ok": bool(s.get("ok")), "adjust": 0,
                "setup": None, "evidence": s.get("evidence")}

    exp = SETUP_EXPECTANCY[s["setup"]]
    rr = (s.get("levels") or {}).get("risk_reward")
    # 3 ประตูก่อนจะบวกคะแนน (ปรัชญา "ประตูความซื่อสัตย์" ของ volume-edge):
    #   1) setup ต้องไม่ถูก gate ปิด   2) backtest expectancy เป็นบวก
    #   3) R:R ต้อง >= 1.2 (เสี่ยง 1 ควรได้คืนอย่างน้อย 1.2 — ไม่งั้นไม่คุ้ม)
    if exp.get("gated") or exp["oos_r"] <= 0 or not rr or rr < 1.2:
        adjust = 0
        reason = ("R:R ต่ำเกินไป ไม่คุ้มเสี่ยง" if (rr and rr < 1.2)
                  else "setup นี้ backtest ไม่ผ่าน")
    else:
        adjust = round(min(8, 3 + min(5, rr * 1.5)), 1)   # +4.5 ถึง +8 ตาม R:R
        reason = None
    return {"ok": True, "adjust": adjust, "setup": s["setup"],
            "evidence": s.get("evidence"), "levels": s.get("levels"),
            "expectancy": exp, "gate_note": reason}
