"""
Strategy Lab — "โรงงานกลยุทธ์" แบบ Renaissance-style

แนวคิด (บทเรียนจริงจาก Jim Simons)
----------------------------------
Medallion ไม่ได้รวยเพราะกลยุทธ์เดียวที่เก่ง แต่เพราะ "ทดสอบสมมติฐานเป็นพัน ๆ อัน
เก็บเฉพาะที่รอดสถิติ แล้ววางเดิมพันเล็ก ๆ จำนวนมาก" — edge ต่อไม้ของเขา
เล็กมาก (ชนะ ~50.75%) แต่เครื่องคัดกรองซื่อสัตย์และทำซ้ำได้

แล็บนี้เอาวิธีทำงานนั้นมาใช้:
  1. กลยุทธ์หลายตระกูล (momentum, trend, ข่าวพุ่ง, ข่าวนำราคา, volume profile)
  2. ทุกตัววิ่งผ่าน "ประตูความซื่อสัตย์" เดียวกัน:
       - walk-forward: หาเกณฑ์จากช่วง train เท่านั้น เทรดในช่วง test ที่ไม่เคยเห็น
       - หักค่าธรรมเนียมทุกไม้ · เทียบ buy & hold เสมอ · ตรวจร่องรอย overfit
  3. league table จัดอันดับ — ตัวที่รอดค่อยเอาไปใช้จริง ตัวที่ตกโดนปิด
     (เหมือน LVN ใน volume profile ที่ backtest ขาดทุนแล้วถูก gate ถาวร)

⚠️ ผ่านแล็บ ≠ การันตีอนาคต — แปลว่า "มีหลักฐานพอให้ลองด้วยเงินส่วนน้อย" เท่านั้น
"""
import bisect
import datetime as dt

import numpy as np

from services import events_data, gdelt, news_backtest, stock_data
from services.volume_profile import SETUP_EXPECTANCY


DEFAULT_DAYS = 900          # ~3.5 ปีปฏิทิน (~620 วันทำการ) — พอสำหรับ momentum 12 เดือน
DEFAULT_FEE_PCT = 0.1       # ค่าคอม+สลิปเพจต่อขา (%)
MIN_RET_DAYS = 120
MOM_LONG = 252              # 12 เดือน (วันทำการ)
MOM_SKIP = 21               # เว้นเดือนล่าสุด (short-term reversal)
SMA_LEN = 200
NEWS_HOLD_DAYS = 3          # ถือกี่วันทำการหลังข่าวพุ่ง
NEWS_SPIKE_Q = 0.85         # ปริมาณข่าวต้องอยู่ top 15% ของช่วง train
DEFAULT_BASKET = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
LEAGUE_KEYS = ["momentum", "trend", "news_velocity", "news_lag"]


STRATEGIES = {
    "momentum": {
        "name": "โมเมนตัม 12-1",
        "family": "ราคา",
        "runnable": True,
        "desc": ("ถือเมื่อผลตอบแทน 12 เดือนย้อนหลัง (เว้นเดือนล่าสุด) เป็นบวก — "
                 "factor ที่มีงานวิจัยรองรับหนาแน่นที่สุดตัวหนึ่ง (Jegadeesh & Titman 1993)"),
    },
    "trend": {
        "name": "เทรนด์ SMA200",
        "family": "ราคา",
        "runnable": True,
        "desc": ("ถือเมื่อราคาอยู่เหนือเส้นค่าเฉลี่ย 200 วัน — ไม่ได้หวังชนะขาขึ้น "
                 "แต่หวังหนีขาลงใหญ่ (แบบเดียวกับกฎ long-only ของ volume-edge)"),
    },
    "news_velocity": {
        "name": "ข่าวพุ่ง (news velocity)",
        "family": "ข่าว",
        "runnable": True,
        "desc": ("ปริมาณข่าวของหุ้นพุ่งผิดปกติ + โทนข่าวดีกว่าปกติ → ซื้อถือสั้น ๆ "
                 "— จับปรากฏการณ์เดียวกับสายเทรดข่าว Twitter แต่ใช้ GDELT ที่ฟรี"),
    },
    "news_lag": {
        "name": "ข่าวโลกนำราคา",
        "family": "ข่าว",
        "runnable": True,
        "desc": ("สัญญาณข่าวโลก/มหภาคที่เรียนรู้ว่า 'นำ' ราคาหุ้นตัวนี้ "
                 "(เครื่องเรียนรู้ + Bonferroni) แล้วเทรดตามในช่วง test"),
    },
    "vp_setup": {
        "name": "Volume Profile (VAB/VAR)",
        "family": "จังหวะเข้า",
        "runnable": False,
        "desc": ("จังหวะเข้า/ตัดขาดทุน/เป้า จากโครงสร้าง volume — มีผล backtest "
                 "จาก volume-edge แล้ว ใช้งานได้ที่แท็บ Volume ในหน้าวิเคราะห์"),
        "evidence": {k: v for k, v in SETUP_EXPECTANCY.items()},
    },
    "pead": {
        "name": "Earnings drift (PEAD)",
        "family": "เหตุการณ์",
        "runnable": True,
        "desc": ("งบดีกว่าที่ตลาดคาด แล้วราคามักไหลต่ออีกหลายสัปดาห์ — anomaly "
                 "คลาสสิก (Ball & Brown 1968) · ใช้ได้เฉพาะหุ้นที่ Yahoo มีค่าคาดการณ์ "
                 "ย้อนหลังให้ ซึ่งส่วนใหญ่เป็นหุ้นสหรัฐ"),
    },
    "insider": {
        "name": "ตามผู้บริหารซื้อหุ้นตัวเอง",
        "family": "เหตุการณ์",
        "runnable": True,
        "desc": ("ผู้บริหารซื้อหุ้นบริษัทตัวเอง = คนที่รู้ดีที่สุดเอาเงินตัวเองลง "
                 "· เข้าซื้อวันถัดจากวันทำรายการเสมอ (ข้อมูลถูกรายงานช้ากว่าจริง) "
                 "· Yahoo ให้ย้อนหลังราว 1-2 ปี และแทบไม่มีหุ้นไทย"),
    },
}


# ---------------------------------------------------------------------------
# ข้อมูลราคา
# ---------------------------------------------------------------------------
def _closes(ticker: str, days: int):
    """คืน (dates, closes) เรียงตามเวลา"""
    period = "5y" if days > 700 else ("3y" if days > 500 else "2y")
    hist = stock_data.get_history(ticker, period=period)
    candles = [c for c in hist.get("candles", []) if c.get("close")]
    dates = [c["date"] for c in candles]
    closes = [float(c["close"]) for c in candles]
    return dates, closes


def _returns(dates, closes) -> dict:
    """{day: ผลตอบแทน %} — วันแรกไม่มีผลตอบแทน"""
    out = {}
    for i in range(1, len(dates)):
        if closes[i - 1]:
            out[dates[i]] = (closes[i] / closes[i - 1] - 1) * 100
    return out


# ---------------------------------------------------------------------------
# สัญญาณตำแหน่ง (position 0/1 ต่อวัน) — คำนวณจากข้อมูล "ถึงเมื่อวาน" เท่านั้น
# ---------------------------------------------------------------------------
def _positions_momentum(dates, closes):
    """position วัน i ใช้ราคาถึงวัน i-1 (กัน look-ahead)"""
    pos = {}
    for i in range(1, len(dates)):
        j = i - 1
        if j - MOM_LONG < 0:
            continue
        mom = closes[j - MOM_SKIP] / closes[j - MOM_LONG] - 1
        pos[dates[i]] = 1 if mom > 0 else 0
    return pos, {"rule": "ถือเมื่อผลตอบแทน 12 เดือน (เว้น 1 เดือนล่าสุด) > 0",
                 "warmup_days": MOM_LONG}


def _positions_trend(dates, closes):
    pos = {}
    run_sum = 0.0
    for i in range(1, len(dates)):
        j = i - 1
        run_sum += closes[j]
        if j >= SMA_LEN:
            run_sum -= closes[j - SMA_LEN]
        if j >= SMA_LEN - 1:
            sma = run_sum / SMA_LEN
            pos[dates[i]] = 1 if closes[j] > sma else 0
    return pos, {"rule": f"ถือเมื่อราคาปิด > SMA{SMA_LEN}", "warmup_days": SMA_LEN}


# ---------------------------------------------------------------------------
# กลยุทธ์ตระกูล "เหตุการณ์" — ถือ N วันหลังเหตุการณ์
# ---------------------------------------------------------------------------
PEAD_HOLD_GRID = (10, 21, 42, 63)       # ~2 สัปดาห์ ถึง ~3 เดือน
PEAD_MIN_SURPRISE = (0.0, 2.0, 5.0)     # เซอร์ไพรส์ขั้นต่ำ (%)
INSIDER_HOLD_GRID = (10, 21, 42, 63)


def _hold_after_events(dates, event_days, hold: int) -> dict:
    """
    สร้าง position: ถือ hold วันทำการ นับจาก "วันถัดจากวันเหตุการณ์"

    ที่ต้องเป็นวันถัดไปเพราะข่าวงบออกหลังตลาดปิด และรายการ insider ถูกรายงาน
    ช้ากว่าวันที่ทำจริง ถ้าเข้าวันเดียวกันคือมองเห็นข้อมูลที่ยังไม่มีใครรู้
    """
    pos = {d: 0 for d in dates}
    if not event_days:
        return pos
    for ev in event_days:
        i = bisect.bisect_right(dates, ev)      # วันทำการแรกที่ "หลัง" เหตุการณ์
        for d in dates[i:i + hold]:
            pos[d] = 1
    return pos


def _tune_on_train(dates, rets, train_set, events, grids, fee_pct):
    """
    เลือกพารามิเตอร์จาก "ช่วง train เท่านั้น" แล้วเอาไปใช้ทั้งเส้น

    หัวใจของความซื่อสัตย์: ถ้าไปเลือกค่าที่ดีที่สุดบนช่วง test ด้วย
    ตัวเลขที่ได้จะสวยแบบไม่มีความหมาย (overfit) — เราจึงตัดสินใจก่อนเห็น test
    """
    train_days = sorted(train_set)
    best = None
    for combo in grids:
        pos = _hold_after_events(dates, combo["events"], combo["hold"])
        res = _simulate_positions(train_days, rets, pos, fee_pct)
        score = res.get("total_return", 0) or 0
        if best is None or score > best["score"]:
            best = {"score": score, "combo": combo, "pos": pos}
    return best


def _positions_pead(ticker, dates, rets, train_set, fee_pct):
    data = events_data.earnings_surprises(ticker)
    if not data.get("ok"):
        return None, {"error": data.get("error") or "ไม่มีข้อมูลวันประกาศงบ"}

    evs = data["events"]
    grids = []
    for hold in PEAD_HOLD_GRID:
        for min_sur in PEAD_MIN_SURPRISE:
            days_ = [e["day"] for e in evs if (e["surprise_pct"] or 0) > min_sur]
            if len(days_) >= events_data.MIN_EVENTS:
                grids.append({"hold": hold, "min_surprise": min_sur,
                              "events": days_, "n": len(days_)})
    if not grids:
        return None, {"error": "งบที่ดีกว่าคาดมีน้อยเกินไปจนทดสอบไม่ได้"}

    best = _tune_on_train(dates, rets, train_set, evs, grids, fee_pct)
    c = best["combo"]
    return best["pos"], {
        "rule": (f"งบดีกว่าคาด > {c['min_surprise']}% แล้วถือ {c['hold']} วันทำการ "
                 "(เข้าวันถัดจากวันประกาศ)"),
        "hold_days": c["hold"], "min_surprise_pct": c["min_surprise"],
        "events_used": c["n"], "events_total": len(evs),
        "tuned_on": "ช่วง train เท่านั้น",
        "source": "Yahoo Finance earnings dates",
    }


def _positions_insider(ticker, dates, rets, train_set, fee_pct):
    data = events_data.insider_buys(ticker)
    if not data.get("ok"):
        return None, {"error": data.get("error") or "ไม่มีข้อมูล insider"}

    evs = data["events"]
    days_ = [e["day"] for e in evs]
    grids = [{"hold": h, "events": days_, "n": len(days_)}
             for h in INSIDER_HOLD_GRID]
    best = _tune_on_train(dates, rets, train_set, evs, grids, fee_pct)
    c = best["combo"]
    return best["pos"], {
        "rule": f"ผู้บริหารซื้อ แล้วถือ {c['hold']} วันทำการ (เข้าวันถัดไป)",
        "hold_days": c["hold"], "events_used": c["n"],
        "tuned_on": "ช่วง train เท่านั้น",
        "source": "Yahoo Finance insider transactions",
    }


def _news_query(ticker: str) -> str:
    base = ticker.replace(".BK", "").strip()
    return f'"{base}"' if " " in base else base


def _positions_news_velocity(ticker, ret_days, train_set, days):
    """
    เกณฑ์ (threshold ปริมาณข่าว + โทนกลาง) คำนวณจากช่วง train เท่านั้น
    วันไหนข่าวพุ่ง + โทนดีกว่าปกติ -> ถือ NEWS_HOLD_DAYS วันทำการถัดไป
    """
    q = _news_query(ticker)
    vol = gdelt.volume_timeline(q, timespan=f"{days}d").get("series") or {}
    tone = gdelt.tone_timeline(q, timespan=f"{days}d").get("series") or {}

    train_vol = [v for d, v in vol.items() if d in train_set and v is not None]
    train_tone = [v for d, v in tone.items() if d in train_set and v is not None]
    if len(train_vol) < 30:
        return None, {"error": f"ข่าวของ {ticker} ในช่วงเรียนรู้มีแค่ {len(train_vol)} วัน "
                               "(ต้องการ 30+) — GDELT อาจไม่รู้จักชื่อนี้"}

    thr = float(np.quantile(train_vol, NEWS_SPIKE_Q))
    tone_med = float(np.median(train_tone)) if train_tone else 0.0

    pos = {}
    for d, v in vol.items():
        if v is None or v < thr:
            continue
        if tone.get(d, tone_med) <= tone_med:
            continue
        # เข้าซื้อวันทำการแรก "หลัง" วันข่าว แล้วถือ NEWS_HOLD_DAYS วัน
        start = bisect.bisect_right(ret_days, d)
        for k in range(start, min(start + NEWS_HOLD_DAYS, len(ret_days))):
            pos[ret_days[k]] = 1
    return pos, {"rule": f"ปริมาณข่าว ≥ top {round((1 - NEWS_SPIKE_Q) * 100)}% ของช่วง train "
                         f"และโทนข่าว > ค่ากลาง → ถือ {NEWS_HOLD_DAYS} วันทำการ",
                 "query": q, "volume_threshold": round(thr, 3),
                 "tone_median": round(tone_med, 3),
                 "news_days": len(vol)}


# ---------------------------------------------------------------------------
# เครื่องจำลองการเทรดจาก position รายวัน (หักค่าธรรมเนียมทุกไม้)
# ---------------------------------------------------------------------------
def _simulate_positions(period_dates, rets, pos, fee_pct):
    fee = fee_pct / 100.0
    equity = 1.0
    prev = 0
    entry_eq = None
    trades = []
    curve = []
    held = 0

    for day in period_dates:
        p = 1 if pos.get(day) else 0
        if prev == 1 and p == 0 and entry_eq is not None:   # ปิดสถานะ (ที่ปิดเมื่อวาน)
            equity *= (1 - fee)
            trades.append((equity / entry_eq - 1) * 100)
            entry_eq = None
        if prev == 0 and p == 1:                            # เปิดสถานะ (ซื้อปิดเมื่อวาน)
            equity *= (1 - fee)
            entry_eq = equity
        if p:
            equity *= (1 + rets.get(day, 0.0) / 100.0)
            held += 1
        prev = p
        curve.append({"date": day, "equity": round(equity, 5)})

    if prev == 1 and entry_eq is not None:                  # ค้างสถานะตอนจบ
        equity *= (1 - fee)
        trades.append((equity / entry_eq - 1) * 100)
        if curve:
            curve[-1]["equity"] = round(equity, 5)

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    days_n = max(1, len(period_dates))
    return {
        "total_return_pct": round((equity - 1) * 100, 2),
        "num_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "avg_trade_pct": round(float(np.mean(trades)), 3) if trades else None,
        "avg_win_pct": round(float(np.mean(wins)), 2) if wins else None,
        "avg_loss_pct": round(float(np.mean(losses)), 2) if losses else None,
        "max_drawdown_pct": round(news_backtest._max_drawdown(
            [c["equity"] for c in curve]), 2),
        "exposure_pct": round(held / days_n * 100, 1),
        "annualized_pct": round(((equity ** (252 / days_n)) - 1) * 100, 2) if equity > 0 else None,
        "curve": news_backtest._thin(curve, 180),
    }


# ---------------------------------------------------------------------------
# รันกลยุทธ์ 1 ตัว กับหุ้น 1 ตัว ผ่านประตูความซื่อสัตย์
# ---------------------------------------------------------------------------
def run(key: str, ticker: str, days: int = DEFAULT_DAYS, train_frac: float = 0.6,
        fee_pct: float = DEFAULT_FEE_PCT) -> dict:
    meta = STRATEGIES.get(key)
    if not meta:
        return {"ok": False, "error": f"ไม่รู้จักกลยุทธ์ '{key}'"}
    if not meta["runnable"]:
        return {"ok": False, "error": f"กลยุทธ์ '{meta['name']}' ยังรันในแล็บไม่ได้",
                "strategy": {"key": key, **meta}}

    # กันค่าพารามิเตอร์ประหลาดจาก URL (เช่น train_frac=0 จะทำให้ไม่มีช่วง train เลย)
    days = min(1800, max(200, days))
    train_frac = min(0.85, max(0.3, train_frac))
    fee_pct = min(2.0, max(0.0, fee_pct))

    ticker = stock_data.normalize_ticker(ticker)

    # news_lag ใช้เครื่อง backtest ข่าวที่มีอยู่แล้ว (walk-forward + Bonferroni)
    if key == "news_lag":
        res = news_backtest.run(ticker, days=min(days, 540),
                                train_frac=train_frac, fee_pct=fee_pct)
        res["strategy"] = {"key": key, "name": meta["name"], "desc": meta["desc"]}
        return res

    dates, closes = _closes(ticker, days)
    rets = _returns(dates, closes)
    ret_days = sorted(rets)
    if len(ret_days) < MIN_RET_DAYS:
        return {"ok": False, "ticker": ticker,
                "error": f"ข้อมูลราคาไม่พอ (มี {len(ret_days)} วัน ต้องการ {MIN_RET_DAYS}+)"}

    split = int(len(ret_days) * train_frac)
    train_days = ret_days[:split]
    test_days = ret_days[split:]

    if key == "momentum":
        if len(dates) < MOM_LONG + 40:
            return {"ok": False, "ticker": ticker,
                    "error": f"โมเมนตัม 12 เดือนต้องการราคา {MOM_LONG + 40}+ วัน "
                             f"(มี {len(dates)})"}
        pos, params = _positions_momentum(dates, closes)
    elif key == "trend":
        pos, params = _positions_trend(dates, closes)
    elif key == "news_velocity":
        pos, params = _positions_news_velocity(ticker, ret_days, set(train_days), days)
        if pos is None:
            return {"ok": False, "ticker": ticker, "error": params["error"]}
    elif key == "pead":
        pos, params = _positions_pead(ticker, ret_days, rets, set(train_days), fee_pct)
        if pos is None:
            return {"ok": False, "ticker": ticker, "error": params["error"],
                    "strategy": {"key": key, **meta}}
    elif key == "insider":
        pos, params = _positions_insider(ticker, ret_days, rets, set(train_days), fee_pct)
        if pos is None:
            return {"ok": False, "ticker": ticker, "error": params["error"],
                    "strategy": {"key": key, **meta}}
    else:
        return {"ok": False, "error": f"ยังไม่มีตัวรันของ '{key}'"}

    ins = _simulate_positions(train_days, rets, pos, fee_pct)
    oos = _simulate_positions(test_days, rets, pos, fee_pct)
    bh = news_backtest._buy_and_hold(rets, test_days)

    return {
        "ok": True,
        "ticker": ticker,
        "strategy": {"key": key, "name": meta["name"], "desc": meta["desc"]},
        "days": days,
        "fee_pct": fee_pct,
        "params": params,
        "train": {"from": train_days[0], "to": train_days[-1], "days": len(train_days)},
        "test": {"from": test_days[0], "to": test_days[-1], "days": len(test_days)},
        "in_sample": ins,
        "out_of_sample": oos,
        "buyhold": bh,
        "verdict": news_backtest._verdict(oos, bh, ins),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# League table — จัดอันดับกลยุทธ์ข้ามตะกร้าหุ้น
# ---------------------------------------------------------------------------
def league(tickers=None, days: int = DEFAULT_DAYS, include=None) -> dict:
    tickers = [stock_data.normalize_ticker(t) for t in (tickers or DEFAULT_BASKET)][:6]
    keys = [k for k in (include or LEAGUE_KEYS)
            if k in STRATEGIES and STRATEGIES[k]["runnable"]]

    rows = []
    for key in keys:
        edges = []
        verdicts = {}
        per = []
        for t in tickers:
            try:
                res = run(key, t, days=days)
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            oos = (res.get("out_of_sample") or {}) if res.get("ok") else {}
            if not res.get("ok") or "total_return_pct" not in oos:
                lvl = (res.get("verdict") or {}).get("level", "none")
                per.append({"ticker": t, "ok": False, "verdict": lvl,
                            "error": res.get("error")})
                continue
            bh = (res.get("buyhold") or {}).get("total_return_pct") or 0
            edge = round(oos["total_return_pct"] - bh, 2)
            lvl = (res.get("verdict") or {}).get("level", "unknown")
            verdicts[lvl] = verdicts.get(lvl, 0) + 1
            edges.append(edge)
            per.append({"ticker": t, "ok": True,
                        "oos": oos["total_return_pct"], "buyhold": bh, "edge": edge,
                        "trades": oos.get("num_trades"), "verdict": lvl})

        rows.append({
            "key": key,
            "name": STRATEGIES[key]["name"],
            "family": STRATEGIES[key]["family"],
            "runs": len(edges),
            "avg_edge": round(float(np.mean(edges)), 2) if edges else None,
            "median_edge": round(float(np.median(edges)), 2) if edges else None,
            "beat_market": sum(1 for e in edges if e > 0),
            "good": verdicts.get("good", 0),
            "overfit": verdicts.get("overfit", 0),
            "verdicts": verdicts,
            "status": _status(edges, verdicts),
            "per_ticker": per,
        })

    rows.sort(key=lambda r: r["avg_edge"] if r["avg_edge"] is not None else -1e9,
              reverse=True)
    return {
        "ok": True,
        "tickers": tickers,
        "days": days,
        "rows": rows,
        "caveat": ("edge = ผลตอบแทนช่วงทดสอบ (out-of-sample หักค่าธรรมเนียม) ลบ buy & hold · "
                   "ตะกร้าเล็กและช่วงเวลาเดียว — ใช้จัดลำดับว่าตัวไหน 'ควรตามต่อ' "
                   "ไม่ใช่คำตัดสินสุดท้าย · ผ่านแล็บ ≠ การันตีอนาคต"),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _status(edges, verdicts) -> dict:
    if not edges:
        return {"level": "no_data", "text": "หลักฐานไม่พอ (รันไม่สำเร็จ/ไม่มีสัญญาณ)"}
    avg = float(np.mean(edges))
    good = verdicts.get("good", 0)
    overfit = verdicts.get("overfit", 0)
    if avg > 0 and good >= max(1, len(edges) // 2):
        return {"level": "follow",
                "text": "น่าติดตาม — ชนะตลาดนอกกลุ่มตัวอย่างเกินครึ่ง (ยังต้องยืนยันซ้ำ)"}
    if avg > 0:
        return {"level": "mixed", "text": "ก้ำกึ่ง — บางตัวชนะบางตัวแพ้ รอหลักฐานเพิ่ม"}
    if overfit > len(edges) / 2:
        return {"level": "overfit", "text": "ส่อ overfit — สวยในอดีต พังตอนทดสอบ"}
    return {"level": "fail", "text": "ตกรอบ (ช่วงนี้) — แพ้ buy & hold โดยเฉลี่ย"}


def list_strategies() -> dict:
    items = []
    for key, m in STRATEGIES.items():
        items.append({"key": key, **{k: v for k, v in m.items()}})
    return {
        "ok": True,
        "strategies": items,
        "note": ("ทุกกลยุทธ์ต้องผ่านประตูเดียวกัน: walk-forward (เกณฑ์จาก train เท่านั้น) · "
                 "หักค่าธรรมเนียม 0.1%/ขา · เทียบ buy & hold · ตรวจ overfit — "
                 "ตัวที่ตกรอบจะถูกปิดเหมือน LVN ใน volume profile"),
    }
