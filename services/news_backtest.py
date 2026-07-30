"""
News-signal backtest — "ถ้าเทรดตามสัญญาณข่าวจริง ๆ จะได้กำไรไหม?"

⚠️ กับดักที่ทำให้ backtest ส่วนใหญ่โกหก
--------------------------------------
ถ้าเราหาความสัมพันธ์จากข้อมูล 1 ปี แล้วเอา "ปีเดียวกันนั้น" มาทดสอบ
ผลจะออกมาสวยเสมอ เพราะเราเลือกสัญญาณที่ fit กับข้อมูลชุดนั้นมาแล้ว
(overfitting / in-sample bias) — เป็นผลลวง ใช้ตัดสินใจไม่ได้

วิธีที่ถูกต้อง (walk-forward / out-of-sample)
-------------------------------------------
  |<----------- ช่วงเรียนรู้ (train) ----------->|<--- ช่วงทดสอบ (test) --->|
  หาสัญญาณจากตรงนี้เท่านั้น                        เทรดตามสัญญาณตรงนี้เท่านั้น

- ค้นหาความสัมพันธ์ + คำนวณเกณฑ์เข้าซื้อ จาก train เท่านั้น
- เอาสัญญาณที่ได้ไปเทรดใน test ซึ่งเครื่อง "ไม่เคยเห็น" มาก่อน
- เทียบกับ buy & hold ในช่วงเดียวกัน และหักค่าธรรมเนียมทุกไม้

ตัวเลขจากช่วง test เท่านั้นที่เชื่อได้
"""
import datetime as dt

import numpy as np

from config import Config
from services import correlation, stock_data


DEFAULT_FEE_PCT = 0.1     # ค่าคอม+สลิปเพจต่อขา (%)
MIN_TEST_DAYS = 40
MIN_TRAIN_DAYS = 60


def run(ticker: str, days: int = 540, train_frac: float = 0.6,
        fee_pct: float = DEFAULT_FEE_PCT, top_pct: float = 1 / 3) -> dict:
    ticker = stock_data.normalize_ticker(ticker)
    lags = [L for L in Config.LEARN_LAGS if L >= 1]   # ต้องเป็นสัญญาณที่ "นำ" ราคา

    rets = correlation._returns_series(ticker, days)
    dates = sorted(rets)
    if len(dates) < MIN_TRAIN_DAYS + MIN_TEST_DAYS:
        return {"ok": False, "ticker": ticker,
                "error": f"ข้อมูลราคาไม่พอ (มี {len(dates)} วัน ต้องการอย่างน้อย "
                         f"{MIN_TRAIN_DAYS + MIN_TEST_DAYS} วัน)"}

    split = int(len(dates) * train_frac)
    train_dates = dates[:split]
    test_dates = dates[split:]
    train_set = set(train_dates)

    # ---------- 1) ค้นหาสัญญาณ จาก train เท่านั้น ----------
    features = correlation.default_features(ticker)
    series_cache = {f: correlation._feature_series(f, days) for f in features}
    series_cache = {f: s for f, s in series_cache.items() if len(s) >= 10}
    if not series_cache:
        return {"ok": False, "ticker": ticker,
                "error": "ดึงข้อมูลข่าว/มหภาคไม่ได้ (ตรวจสอบอินเทอร์เน็ต)"}

    n_tests = max(1, len(series_cache) * len(lags))
    candidates = []
    for feat, ser in series_cache.items():
        for lag in lags:
            xs, ys = correlation.align(ser, rets, lag, allowed_days=train_set)
            if len(xs) < 20:
                continue
            r, t = correlation._pearson(xs, ys)
            if r is None:
                continue
            crit = correlation._critical_r(len(xs), n_tests)
            candidates.append({
                "feature": feat, "label": correlation._feature_label(feat),
                "lag": lag, "r": round(r, 3), "n": len(xs),
                "t_stat": round(t, 2), "critical_r": round(crit, 3),
                "significant": abs(r) >= crit,
                # เกณฑ์เข้าซื้อคำนวณจาก train เท่านั้น (กัน look-ahead)
                "threshold": float(np.quantile(xs, 1 - top_pct) if r >= 0
                                   else np.quantile(xs, top_pct)),
            })

    candidates.sort(key=lambda c: abs(c["r"]), reverse=True)
    passing = [c for c in candidates if c["significant"]]

    result = {
        "ok": True,
        "ticker": ticker,
        "days": days,
        "fee_pct": fee_pct,
        "train": {"from": train_dates[0], "to": train_dates[-1], "days": len(train_dates)},
        "test": {"from": test_dates[0], "to": test_dates[-1], "days": len(test_dates)},
        "tested_pairs": n_tests,
        "candidates": candidates[:10],
        "passing_count": len(passing),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }

    buyhold = _buy_and_hold(rets, test_dates)
    result["buyhold"] = buyhold

    if not passing:
        result["signal"] = None
        result["verdict"] = {
            "level": "none",
            "text": ("ไม่พบสัญญาณข่าวที่แรงพอในช่วงเรียนรู้ — ไม่มีอะไรให้เทรด "
                     "(นี่เป็นผลลัพธ์ที่ดี ดีกว่าเทรดตามสัญญาณลวง)")}
        return result

    best = passing[0]
    result["signal"] = best

    # ---------- 2) เทรดตามสัญญาณ ในช่วง test ----------
    ser = series_cache[best["feature"]]
    oos = _simulate(ser, rets, test_dates, best, fee_pct)
    ins = _simulate(ser, rets, train_dates, best, fee_pct)

    result["out_of_sample"] = oos       # <- ตัวเลขที่เชื่อได้
    result["in_sample"] = ins           # <- ไว้เทียบให้เห็นว่ามันสวยกว่าเสมอ
    result["verdict"] = _verdict(oos, buyhold, ins)
    return result


def _simulate(ser: dict, rets: dict, period_dates: list, sig: dict, fee_pct: float) -> dict:
    """
    เทรดตามสัญญาณ: วันไหน feature ทะลุเกณฑ์ -> เข้าซื้อที่ราคาปิดวันนั้น
    ถือ lag วัน แล้วขาย · หักค่าธรรมเนียมทั้งขาเข้าและขาออก
    """
    lag = sig["lag"]
    thr = sig["threshold"]
    positive = sig["r"] >= 0
    equity = 1.0
    curve = []
    trades = []
    hold_left = 0
    entry_equity = None
    fee = fee_pct / 100.0

    for day in period_dates:
        # ถืออยู่ -> รับผลตอบแทนของวันนี้
        if hold_left > 0:
            equity *= (1 + rets.get(day, 0.0) / 100.0)
            hold_left -= 1
            if hold_left == 0:                       # ปิดสถานะ
                equity *= (1 - fee)
                trades.append((equity / entry_equity - 1) * 100)
                entry_equity = None

        # ยังว่าง -> ดูว่าวันนี้มีสัญญาณไหม (ใช้ค่า feature ของวันนี้ = รู้ตอนปิดตลาด)
        if hold_left == 0:
            v = ser.get(day)
            fired = v is not None and ((v >= thr) if positive else (v <= thr))
            if fired:
                equity *= (1 - fee)                  # ค่าธรรมเนียมขาเข้า
                entry_equity = equity
                hold_left = lag

        curve.append({"date": day, "equity": round(equity, 5)})

    # ยังค้างสถานะตอนจบช่วง -> ปิดตามราคาสุดท้าย
    if hold_left > 0 and entry_equity is not None:
        equity *= (1 - fee)
        trades.append((equity / entry_equity - 1) * 100)
        if curve:
            curve[-1]["equity"] = round(equity, 5)

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    days_n = max(1, len(period_dates))
    total = (equity - 1) * 100

    return {
        "total_return_pct": round(total, 2),
        "num_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "avg_trade_pct": round(float(np.mean(trades)), 3) if trades else None,
        "avg_win_pct": round(float(np.mean(wins)), 2) if wins else None,
        "avg_loss_pct": round(float(np.mean(losses)), 2) if losses else None,
        "max_drawdown_pct": round(_max_drawdown([c["equity"] for c in curve]), 2),
        "exposure_pct": round(len(trades) * sig["lag"] / days_n * 100, 1),
        "annualized_pct": round(((equity ** (252 / days_n)) - 1) * 100, 2) if equity > 0 else None,
        "curve": _thin(curve, 180),
    }


def _buy_and_hold(rets: dict, period_dates: list) -> dict:
    equity = 1.0
    curve = []
    for day in period_dates:
        equity *= (1 + rets.get(day, 0.0) / 100.0)
        curve.append({"date": day, "equity": round(equity, 5)})
    days_n = max(1, len(period_dates))
    return {
        "total_return_pct": round((equity - 1) * 100, 2),
        "max_drawdown_pct": round(_max_drawdown([c["equity"] for c in curve]), 2),
        "annualized_pct": round(((equity ** (252 / days_n)) - 1) * 100, 2) if equity > 0 else None,
        "curve": _thin(curve, 180),
    }


def _verdict(oos: dict, bh: dict, ins: dict) -> dict:
    """
    สรุปเป็นภาษาคน แบบไม่เชียร์เกินจริง
    ถ้าตรวจพบร่องรอย overfitting จะขึ้นคำเตือน "ก่อน" ตัวเลขสวย ๆ เสมอ
    """
    n = oos.get("num_trades") or 0
    if n < 5:
        return {"level": "unknown",
                "text": (f"เทรดแค่ {n} ไม้ในช่วงทดสอบ — น้อยเกินกว่าจะสรุปอะไรได้ "
                         "ลองขยายช่วงข้อมูลหรือลดความเข้มของสัญญาณ")}

    oos_r = oos.get("total_return_pct") or 0
    bh_r = bh.get("total_return_pct") or 0
    ins_r = ins.get("total_return_pct") or 0
    oos_wr = oos.get("win_rate") or 0
    ins_wr = ins.get("win_rate") or 0
    edge = oos_r - bh_r

    # ---- ตรวจร่องรอย overfitting ก่อนอย่างอื่น ----
    warns = []
    if ins_r > 0 and oos_r < ins_r * 0.4:
        warns.append(f"ผลตอบแทนหล่นจาก {ins_r:.1f}% (ช่วงเรียนรู้) เหลือ {oos_r:.1f}% (ช่วงทดสอบ)")
    if ins_wr and oos_wr and oos_wr < ins_wr - 8:
        warns.append(f"ความแม่นหล่นจาก {ins_wr:.0f}% เหลือ {oos_wr:.0f}%")
    if oos_wr and oos_wr <= 53:
        warns.append(f"ความแม่นในช่วงทดสอบ {oos_wr:.0f}% แทบไม่ต่างจากเดาสุ่ม")

    if warns:
        return {"level": "overfit",
                "text": ("⚠️ สัญญาณนี้ fit กับอดีตมากกว่าจะใช้ได้จริง — "
                         + " · ".join(warns)
                         + f" · ตัวเลขช่วงทดสอบ {oos_r:+.1f}% (ซื้อแล้วถือ {bh_r:+.1f}%) "
                           "อย่าเอาไปใช้ตัดสินใจ")}

    if oos_r <= 0:
        return {"level": "bad",
                "text": f"❌ ขาดทุน {abs(oos_r):.1f}% ในช่วงทดสอบ — สัญญาณนี้ใช้ไม่ได้จริง"}
    if edge <= 0:
        return {"level": "bad",
                "text": (f"❌ กำไร {oos_r:.1f}% แต่ยังแพ้ซื้อแล้วถือ ({bh_r:.1f}%) "
                         "— ไม่คุ้มที่จะเทรดตาม")}
    if edge < 3:
        return {"level": "weak",
                "text": (f"🟡 กำไร {oos_r:.1f}% ชนะซื้อแล้วถือเล็กน้อย (+{edge:.1f}%) "
                         "— ส่วนต่างน้อย อาจหายไปกับค่าธรรมเนียม/สลิปเพจจริง")}
    return {"level": "good",
            "text": (f"✅ กำไร {oos_r:.1f}% ชนะซื้อแล้วถือ +{edge:.1f}% "
                     f"(แม่น {oos_wr:.0f}% · ถือหุ้นแค่ {oos.get('exposure_pct')}% ของเวลา) "
                     "— ผ่านการทดสอบนอกกลุ่มตัวอย่าง แต่ยังไม่รับประกันอนาคต")}


def _max_drawdown(equity) -> float:
    if not equity:
        return 0.0
    arr = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(arr)
    return float(((arr - peak) / peak).min() * 100)


def _thin(curve, max_points):
    if len(curve) <= max_points:
        return curve
    step = max(1, len(curve) // max_points)
    return curve[::step]
