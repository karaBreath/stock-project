"""
Unified scoring — รวมคะแนนพื้นฐาน + เทคนิคัล + sentiment เป็นคะแนนรวม 0-100
พร้อมคำแนะนำ (ซื้อ/ถือ/ขาย) จุดเข้า จุดตัดขาดทุน และเป้าราคา
"""
from services import fundamental, technical, sentiment as sentiment_svc, stock_data


# น้ำหนักของแต่ละด้าน (ปรับได้ง่ายในอนาคต)
WEIGHTS = {"fundamental": 0.45, "technical": 0.35, "sentiment": 0.20}


def overall(ticker: str) -> dict:
    fund = fundamental.analyze(ticker)
    tech = technical.analyze(ticker)
    senti = sentiment_svc.stock_sentiment(ticker)

    f_score = fund.get("fund_score", 50)
    t_score = tech.get("tech_score", 50)
    s_score = senti.get("sentiment_score", 50)

    total = round(
        f_score * WEIGHTS["fundamental"]
        + t_score * WEIGHTS["technical"]
        + s_score * WEIGHTS["sentiment"]
    )
    total = max(0, min(100, total))

    if total >= 70:
        rec = "ซื้อ"
    elif total >= 55:
        rec = "ทยอยซื้อ / ถือ"
    elif total >= 45:
        rec = "ถือ"
    elif total >= 30:
        rec = "ลดพอร์ต"
    else:
        rec = "ขาย / หลีกเลี่ยง"

    # ---- จุดเข้า/ตัดขาดทุน/เป้าราคา จาก ATR + แนวรับแนวต้าน ----
    levels = _trade_levels(tech, fund)

    return {
        "ticker": ticker,
        "name": fund["quote"].get("name", ticker),
        "price": fund["quote"].get("price"),
        "currency": fund["quote"].get("currency"),
        "total_score": total,
        "breakdown": {
            "fundamental": f_score,
            "technical": t_score,
            "sentiment": s_score,
            "weights": WEIGHTS,
        },
        "recommendation": rec,
        "levels": levels,
        "fundamental_notes": fund.get("verdict", []),
        "technical_signals": tech.get("signals", []),
        "sentiment_summary": senti.get("summary", {}),
    }


def _trade_levels(tech, fund):
    last = tech.get("last", {}) if tech.get("ok") else {}
    price = last.get("price") or fund["quote"].get("price")
    atr = last.get("atr")
    if not price:
        return {}

    if atr:
        stop = round(price - 2 * atr, 2)
        target = round(price + 3 * atr, 2)
        entry = round(price - 0.3 * atr, 2)
    else:
        stop = round(price * 0.93, 2)
        target = round(price * 1.12, 2)
        entry = round(price * 0.99, 2)

    risk = price - stop
    reward = target - price
    rr = round(reward / risk, 2) if risk > 0 else None
    return {
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "risk_reward": rr,
        "support": last.get("bb_lower") or last.get("sma50"),
        "resistance": last.get("bb_upper"),
    }
