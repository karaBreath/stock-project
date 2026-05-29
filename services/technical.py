"""
Technical analysis — คำนวณ indicator ด้วย pandas ล้วน (ไม่ต้องลง TA-Lib)

รองรับ: SMA/EMA, RSI, MACD, Bollinger Bands, Stochastic, ATR
และสรุปสัญญาณ (signal) เป็นภาษาคน + คะแนนเทคนิคัล 0-100
"""
import numpy as np
import pandas as pd

from services import stock_data


def _series(history: dict) -> pd.DataFrame:
    candles = history.get("candles", [])
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    for c in ("open", "high", "low", "close", "volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def sma(s: pd.Series, n: int):
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14):
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(s: pd.Series, fast=12, slow=26, signal=9):
    macd_line = ema(s, fast) - ema(s, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(s: pd.Series, n=20, k=2):
    mid = sma(s, n)
    sd = s.rolling(n).std()
    return mid + k * sd, mid, mid - k * sd


def stochastic(df: pd.DataFrame, n=14, d=3):
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    k = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    return k, k.rolling(d).mean()


def atr(df: pd.DataFrame, n=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _last(series):
    """ค่าล่าสุดที่ไม่ใช่ NaN -> float | None"""
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty:
        return None
    v = float(s.iloc[-1])
    return None if (np.isnan(v) or np.isinf(v)) else round(v, 4)


def _clean_list(series):
    return [None if (v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v)))) else round(float(v), 4)
            for v in series.tolist()]


def analyze(ticker: str, period: str = "1y") -> dict:
    """คืน indicator แบบ time-series (สำหรับกราฟ) + ค่าล่าสุด + สัญญาณ + คะแนน"""
    history = stock_data.get_history(ticker, period=period)
    df = _series(history)
    out = {"ticker": ticker, "ok": False}
    if df.empty or "close" not in df.columns or df["close"].dropna().empty:
        out["error"] = history.get("error", "ไม่มีข้อมูลราคา")
        return out

    close = df["close"]
    macd_line, signal_line, hist = macd(close)
    bb_up, bb_mid, bb_low = bollinger(close)
    stoch_k, stoch_d = stochastic(df) if {"high", "low"}.issubset(df.columns) else (pd.Series(dtype=float), pd.Series(dtype=float))

    indicators = {
        "dates": df["date"].tolist(),
        "close": _clean_list(close),
        "volume": _clean_list(df["volume"]) if "volume" in df.columns else [],
        "sma20": _clean_list(sma(close, 20)),
        "sma50": _clean_list(sma(close, 50)),
        "sma200": _clean_list(sma(close, 200)),
        "ema12": _clean_list(ema(close, 12)),
        "rsi": _clean_list(rsi(close)),
        "macd": _clean_list(macd_line),
        "macd_signal": _clean_list(signal_line),
        "macd_hist": _clean_list(hist),
        "bb_upper": _clean_list(bb_up),
        "bb_mid": _clean_list(bb_mid),
        "bb_lower": _clean_list(bb_low),
    }

    last = {
        "price": _last(close),
        "sma20": _last(sma(close, 20)),
        "sma50": _last(sma(close, 50)),
        "sma200": _last(sma(close, 200)),
        "rsi": _last(rsi(close)),
        "macd": _last(macd_line),
        "macd_signal": _last(signal_line),
        "macd_hist": _last(hist),
        "bb_upper": _last(bb_up),
        "bb_lower": _last(bb_low),
        "stoch_k": _last(stoch_k),
        "stoch_d": _last(stoch_d),
        "atr": _last(atr(df)) if {"high", "low"}.issubset(df.columns) else None,
    }

    signals, score = _build_signals(last)
    out.update({
        "ok": True,
        "indicators": indicators,
        "last": last,
        "signals": signals,
        "tech_score": score,
    })
    return out


def _build_signals(last: dict):
    """แปลงค่า indicator เป็นสัญญาณ + คะแนนเทคนิคัล 0-100"""
    signals = []
    score = 50.0  # กลาง ๆ
    price = last.get("price")
    rsi_v = last.get("rsi")

    # RSI
    if rsi_v is not None:
        if rsi_v < 30:
            signals.append({"name": "RSI", "value": rsi_v, "signal": "ซื้อ", "desc": "Oversold (RSI < 30) มีโอกาสเด้ง"})
            score += 12
        elif rsi_v > 70:
            signals.append({"name": "RSI", "value": rsi_v, "signal": "ขาย", "desc": "Overbought (RSI > 70) ระวังพักตัว"})
            score -= 12
        else:
            signals.append({"name": "RSI", "value": rsi_v, "signal": "ถือ", "desc": "อยู่ในโซนปกติ"})

    # MACD
    macd_v, sig_v = last.get("macd"), last.get("macd_signal")
    if macd_v is not None and sig_v is not None:
        if macd_v > sig_v:
            signals.append({"name": "MACD", "value": macd_v, "signal": "ซื้อ", "desc": "MACD ตัดขึ้นเหนือ signal (โมเมนตัมบวก)"})
            score += 12
        else:
            signals.append({"name": "MACD", "value": macd_v, "signal": "ขาย", "desc": "MACD ต่ำกว่า signal (โมเมนตัมลบ)"})
            score -= 8

    # ราคาเทียบเส้นค่าเฉลี่ย
    sma50, sma200 = last.get("sma50"), last.get("sma200")
    if price is not None and sma50 is not None:
        if price > sma50:
            signals.append({"name": "ราคา vs SMA50", "value": sma50, "signal": "ซื้อ", "desc": "ราคาอยู่เหนือเส้นค่าเฉลี่ย 50 วัน (แนวโน้มขึ้นระยะกลาง)"})
            score += 8
        else:
            signals.append({"name": "ราคา vs SMA50", "value": sma50, "signal": "ขาย", "desc": "ราคาอยู่ใต้เส้นค่าเฉลี่ย 50 วัน"})
            score -= 8
    if sma50 is not None and sma200 is not None:
        if sma50 > sma200:
            signals.append({"name": "Golden/Death Cross", "value": None, "signal": "ซื้อ", "desc": "SMA50 เหนือ SMA200 (Golden Cross — แนวโน้มขาขึ้น)"})
            score += 10
        else:
            signals.append({"name": "Golden/Death Cross", "value": None, "signal": "ขาย", "desc": "SMA50 ใต้ SMA200 (Death Cross — แนวโน้มขาลง)"})
            score -= 10

    # Bollinger
    bb_up, bb_low = last.get("bb_upper"), last.get("bb_lower")
    if price is not None and bb_up is not None and bb_low is not None:
        if price <= bb_low:
            signals.append({"name": "Bollinger", "value": bb_low, "signal": "ซื้อ", "desc": "ราคาแตะแถบล่าง อาจ oversold"})
            score += 6
        elif price >= bb_up:
            signals.append({"name": "Bollinger", "value": bb_up, "signal": "ขาย", "desc": "ราคาแตะแถบบน อาจ overbought"})
            score -= 6

    score = max(0, min(100, round(score)))
    return signals, score
