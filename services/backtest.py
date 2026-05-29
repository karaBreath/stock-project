"""
Backtesting — ทดสอบกลยุทธ์กับข้อมูลย้อนหลัง วัด win rate, ผลตอบแทน, max drawdown

กลยุทธ์ที่รองรับ:
- sma_cross : ตัดกันของเส้นค่าเฉลี่ย (default 50/200 หรือกำหนดเอง)
- rsi       : ซื้อเมื่อ RSI < oversold, ขายเมื่อ RSI > overbought
- macd      : ซื้อเมื่อ MACD ตัดขึ้น, ขายเมื่อตัดลง
"""
import numpy as np
import pandas as pd

from services import stock_data, technical


def _load(ticker, period):
    h = stock_data.get_history(ticker, period=period)
    candles = h.get("candles", [])
    if not candles:
        return None
    df = pd.DataFrame(candles)
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"]).reset_index(drop=True)


def _signals(df, strategy, params):
    close = df["close"]
    sig = pd.Series(0, index=df.index)  # 1 = ถือหุ้น, 0 = ถือเงินสด

    if strategy == "sma_cross":
        fast = technical.sma(close, int(params.get("fast", 50)))
        slow = technical.sma(close, int(params.get("slow", 200)))
        sig = (fast > slow).astype(int)
    elif strategy == "rsi":
        r = technical.rsi(close, int(params.get("period", 14)))
        lo = float(params.get("oversold", 30))
        hi = float(params.get("overbought", 70))
        pos = 0
        out = []
        for v in r:
            if not np.isnan(v):
                if v < lo: pos = 1
                elif v > hi: pos = 0
            out.append(pos)
        sig = pd.Series(out, index=df.index)
    elif strategy == "macd":
        macd_line, signal_line, _ = technical.macd(close)
        sig = (macd_line > signal_line).astype(int)

    return sig.shift(1).fillna(0)  # เข้าออเดอร์วันถัดไป (ป้องกัน look-ahead)


def run(ticker, strategy="sma_cross", period="5y", params=None) -> dict:
    params = params or {}
    df = _load(ticker, period)
    if df is None or len(df) < 30:
        return {"ok": False, "message": "ข้อมูลไม่พอสำหรับ backtest"}

    df["signal"] = _signals(df, strategy, params)
    df["ret"] = df["close"].pct_change().fillna(0)
    df["strat_ret"] = df["ret"] * df["signal"]

    # equity curve
    df["equity"] = (1 + df["strat_ret"]).cumprod()
    df["buyhold"] = (1 + df["ret"]).cumprod()

    # นับเทรด (เปลี่ยนสถานะ 0->1 = เปิด, 1->0 = ปิด)
    trades = []
    entry_price = None
    for i in range(1, len(df)):
        prev, cur = df["signal"].iloc[i - 1], df["signal"].iloc[i]
        if prev == 0 and cur == 1:
            entry_price = df["close"].iloc[i]
        elif prev == 1 and cur == 0 and entry_price is not None:
            exit_price = df["close"].iloc[i]
            trades.append((exit_price - entry_price) / entry_price * 100)
            entry_price = None
    if entry_price is not None:  # ปิดสถานะสุดท้าย
        trades.append((df["close"].iloc[-1] - entry_price) / entry_price * 100)

    wins = [t for t in trades if t > 0]
    total_return = (df["equity"].iloc[-1] - 1) * 100
    bh_return = (df["buyhold"].iloc[-1] - 1) * 100
    mdd = _max_drawdown(df["equity"].values)

    # equity curve ย่อ (ไม่เกิน ~200 จุดเพื่อกราฟ)
    step = max(1, len(df) // 200)
    curve = [
        {"date": df["date"].iloc[i], "strategy": round(float(df["equity"].iloc[i]), 4),
         "buyhold": round(float(df["buyhold"].iloc[i]), 4)}
        for i in range(0, len(df), step)
    ]

    return {
        "ok": True,
        "ticker": ticker,
        "strategy": strategy,
        "period": period,
        "total_return_pct": round(total_return, 2),
        "buyhold_return_pct": round(bh_return, 2),
        "num_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "avg_win": round(np.mean(wins), 2) if wins else 0,
        "avg_loss": round(np.mean([t for t in trades if t <= 0]), 2) if any(t <= 0 for t in trades) else 0,
        "max_drawdown_pct": round(mdd, 2),
        "curve": curve,
    }


def _max_drawdown(equity):
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min() * 100)
