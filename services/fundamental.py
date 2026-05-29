"""
Fundamental analysis — งบการเงินย้อนหลัง 5 ปี + เปรียบเทียบคู่แข่ง + คะแนนพื้นฐาน 0-100
"""
from services import stock_data


def _growth(values):
    """คำนวณ % การเติบโตเฉลี่ยจากชุดตัวเลขย้อนหลัง (เก่า->ใหม่)"""
    vals = [v for v in values if v is not None]
    if len(vals) < 2 or vals[0] in (0, None):
        return None
    try:
        # CAGR
        first, last = vals[0], vals[-1]
        years = len(vals) - 1
        if first <= 0 or last <= 0:
            return round((last - first) / abs(first) * 100, 2)
        return round(((last / first) ** (1 / years) - 1) * 100, 2)
    except Exception:
        return None


def analyze(ticker: str) -> dict:
    quote = stock_data.get_quote(ticker)
    fin = stock_data.get_financials(ticker)

    out = {
        "ticker": ticker,
        "ok": quote.get("ok", False),
        "quote": quote,
        "financials": fin,
        "metrics": {},
        "growth": {},
        "fund_score": 50,
        "verdict": [],
    }

    # ---- ค้นรายการรายได้/กำไรจากงบ (ชื่อ index ของ yfinance) ----
    income = fin.get("income", {})
    def pick(d, *keys):
        for k in keys:
            for item, vals in d.items():
                if item.lower() == k.lower():
                    return vals
        return None

    revenue = pick(income, "Total Revenue", "Operating Revenue")
    net_income = pick(income, "Net Income", "Net Income Common Stockholders")

    if revenue:
        out["growth"]["revenue_cagr"] = _growth(revenue)
    if net_income:
        out["growth"]["net_income_cagr"] = _growth(net_income)

    # ---- metrics หลักจาก quote ----
    m = out["metrics"]
    m["pe"] = quote.get("pe")
    m["forward_pe"] = quote.get("forward_pe")
    m["pb"] = quote.get("pb")
    m["roe"] = quote.get("roe")
    m["debt_to_equity"] = quote.get("debt_to_equity")
    m["profit_margin"] = quote.get("profit_margin")
    m["dividend_yield"] = quote.get("dividend_yield")
    m["revenue_growth"] = quote.get("revenue_growth")

    out["fund_score"], out["verdict"] = _score(m, out["growth"])
    return out


def _score(m, growth):
    """ให้คะแนนพื้นฐาน 0-100 จากเกณฑ์ value/quality/growth"""
    score = 50.0
    notes = []

    pe = m.get("pe")
    if pe is not None:
        if 0 < pe <= 12:
            score += 12; notes.append({"ok": True, "text": f"P/E ต่ำ ({pe:.1f}) — ราคาน่าสนใจเชิงมูลค่า"})
        elif pe <= 20:
            score += 5; notes.append({"ok": True, "text": f"P/E สมเหตุสมผล ({pe:.1f})"})
        elif pe > 35:
            score -= 10; notes.append({"ok": False, "text": f"P/E สูง ({pe:.1f}) — ราคาแพงเทียบกำไร"})

    roe = m.get("roe")
    if roe is not None:
        roe_pct = roe * 100 if abs(roe) < 5 else roe
        if roe_pct >= 15:
            score += 12; notes.append({"ok": True, "text": f"ROE สูง ({roe_pct:.1f}%) — ทำกำไรจากส่วนผู้ถือหุ้นได้ดี"})
        elif roe_pct >= 8:
            score += 4; notes.append({"ok": True, "text": f"ROE พอใช้ ({roe_pct:.1f}%)"})
        else:
            score -= 6; notes.append({"ok": False, "text": f"ROE ต่ำ ({roe_pct:.1f}%)"})

    de = m.get("debt_to_equity")
    if de is not None:
        de_val = de if de < 10 else de / 100  # yfinance บางทีให้เป็น %
        if de_val <= 0.5:
            score += 8; notes.append({"ok": True, "text": f"หนี้สินต่ำ (D/E {de_val:.2f}) — ฐานะการเงินแข็งแรง"})
        elif de_val <= 1.5:
            score += 2; notes.append({"ok": True, "text": f"หนี้สินอยู่ในเกณฑ์รับได้ (D/E {de_val:.2f})"})
        else:
            score -= 10; notes.append({"ok": False, "text": f"หนี้สินสูง (D/E {de_val:.2f}) — ความเสี่ยงสูง"})

    pm = m.get("profit_margin")
    if pm is not None:
        pm_pct = pm * 100 if abs(pm) < 5 else pm
        if pm_pct >= 15:
            score += 8; notes.append({"ok": True, "text": f"อัตรากำไรสุทธิสูง ({pm_pct:.1f}%)"})
        elif pm_pct < 0:
            score -= 12; notes.append({"ok": False, "text": "ขาดทุนสุทธิ — ระวัง"})

    rg = growth.get("revenue_cagr") or (m.get("revenue_growth") * 100 if m.get("revenue_growth") else None)
    if rg is not None:
        if rg >= 10:
            score += 10; notes.append({"ok": True, "text": f"รายได้เติบโตดี (~{rg:.1f}%/ปี)"})
        elif rg < 0:
            score -= 8; notes.append({"ok": False, "text": f"รายได้หดตัว (~{rg:.1f}%/ปี)"})

    dy = m.get("dividend_yield")
    if dy is not None:
        dy_pct = dy * 100 if dy < 1 else dy
        if dy_pct >= 3:
            score += 5; notes.append({"ok": True, "text": f"ปันผลน่าสนใจ ({dy_pct:.1f}%)"})

    return max(0, min(100, round(score))), notes


def compare(tickers) -> dict:
    """เปรียบเทียบหุ้นหลายตัว (คู่แข่ง) แบบ side-by-side"""
    rows = []
    for t in tickers:
        a = analyze(t)
        q = a["quote"]
        rows.append({
            "ticker": t,
            "name": q.get("name"),
            "price": q.get("price"),
            "pe": q.get("pe"),
            "pb": q.get("pb"),
            "roe": q.get("roe"),
            "debt_to_equity": q.get("debt_to_equity"),
            "profit_margin": q.get("profit_margin"),
            "dividend_yield": q.get("dividend_yield"),
            "market_cap": q.get("market_cap"),
            "fund_score": a["fund_score"],
        })
    return {"rows": rows}
