"""
Risk management — วิเคราะห์ความเสี่ยงพอร์ต (ความผันผวน, การกระจุกตัว, max drawdown,
beta) และแนะนำสัดส่วนการลงทุนตามหลัก position sizing
"""
import numpy as np

from services import stock_data, portfolio


def _annual_vol(ticker):
    h = stock_data.get_history(ticker, period="1y")
    _, closes = stock_data.history_to_series(h)
    if len(closes) < 20:
        return None
    rets = np.diff(closes) / np.array(closes[:-1])
    return float(np.std(rets) * np.sqrt(252) * 100)


def _max_drawdown(closes):
    if len(closes) < 2:
        return None
    arr = np.array(closes)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / peak
    return float(dd.min() * 100)


def portfolio_risk() -> dict:
    summ = portfolio.summary()
    holdings = summ["holdings"]
    if not holdings:
        return {"ok": False, "message": "ยังไม่มีหุ้นในพอร์ต — เพิ่มหุ้นก่อนเพื่อดูความเสี่ยง"}

    rows = []
    weighted_vol = weighted_beta = 0.0
    total_value = summ["totals"]["value"] or 1
    concentration = 0.0  # Herfindahl index

    for h in holdings:
        q = stock_data.get_quote(h["ticker"])
        vol = _annual_vol(h["ticker"])
        beta = q.get("beta")
        w = h["value"] / total_value
        concentration += w ** 2
        if vol is not None:
            weighted_vol += w * vol
        if beta is not None:
            weighted_beta += w * beta
        rows.append({
            "ticker": h["ticker"],
            "weight": round(w * 100, 2),
            "volatility": round(vol, 2) if vol is not None else None,
            "beta": beta,
            "value": h["value"],
        })

    diversification = round((1 - concentration) * 100, 1)  # ยิ่งสูงยิ่งกระจายดี
    risk_level = _risk_level(weighted_vol, concentration)

    recs = _recommendations(rows, concentration, weighted_vol)

    return {
        "ok": True,
        "positions": rows,
        "portfolio_volatility": round(weighted_vol, 2),
        "portfolio_beta": round(weighted_beta, 2),
        "diversification_score": diversification,
        "concentration": round(concentration, 3),
        "risk_level": risk_level,
        "recommendations": recs,
    }


def _risk_level(vol, conc):
    score = 0
    if vol and vol > 35: score += 2
    elif vol and vol > 22: score += 1
    if conc > 0.4: score += 2
    elif conc > 0.25: score += 1
    return {0: "ต่ำ", 1: "ปานกลางค่อนต่ำ", 2: "ปานกลาง", 3: "ค่อนข้างสูง"}.get(score, "สูง")


def _recommendations(rows, conc, vol):
    recs = []
    over = [r for r in rows if r["weight"] > 25]
    for r in over:
        recs.append(f"⚠️ {r['ticker']} มีน้ำหนัก {r['weight']}% ของพอร์ต — กระจุกตัวสูง ควรลดให้ ≤ 20%")
    if conc > 0.35:
        recs.append("พอร์ตกระจุกตัวมาก ควรถือหุ้นอย่างน้อย 5-8 ตัวในหลายอุตสาหกรรม")
    if vol and vol > 30:
        recs.append(f"ความผันผวนพอร์ตสูง ({vol:.0f}%/ปี) — พิจารณาเพิ่มหุ้นปันผล/สินทรัพย์ปลอดภัย")
    if not recs:
        recs.append("✅ การกระจายความเสี่ยงอยู่ในเกณฑ์ดี")
    return recs


def position_size(account_size, risk_pct, entry, stop_loss) -> dict:
    """คำนวณจำนวนหุ้นที่ควรซื้อตามหลัก risk per trade"""
    try:
        account_size = float(account_size)
        risk_pct = float(risk_pct)
        entry = float(entry)
        stop_loss = float(stop_loss)
    except (TypeError, ValueError):
        return {"ok": False, "message": "กรอกตัวเลขให้ครบ"}

    risk_amount = account_size * risk_pct / 100
    per_share_risk = entry - stop_loss
    if per_share_risk <= 0:
        return {"ok": False, "message": "จุดตัดขาดทุนต้องต่ำกว่าจุดเข้า"}
    shares = int(risk_amount / per_share_risk)
    position_value = shares * entry
    return {
        "ok": True,
        "risk_amount": round(risk_amount, 2),
        "per_share_risk": round(per_share_risk, 2),
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct": round(position_value / account_size * 100, 2) if account_size else 0,
    }
