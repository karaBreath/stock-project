"""
Portfolio service — บันทึกหุ้นที่ถือ คำนวณกำไร/ขาดทุน real-time
"""
from database import query, execute
from services import stock_data


def add_holding(ticker, shares, buy_price, buy_date=None, note=None):
    ticker = stock_data.normalize_ticker(ticker)
    hid = execute(
        "INSERT INTO holdings(ticker, shares, buy_price, buy_date, note) VALUES(?,?,?,?,?)",
        (ticker, float(shares), float(buy_price), buy_date, note),
    )
    return get_holding(hid)


def get_holding(hid):
    return query("SELECT * FROM holdings WHERE id = ?", (hid,), one=True)


def delete_holding(hid):
    execute("DELETE FROM holdings WHERE id = ?", (hid,))
    return {"deleted": hid}


def summary() -> dict:
    holdings = query("SELECT * FROM holdings ORDER BY created_at DESC")
    rows = []
    total_cost = total_value = 0.0
    for h in holdings:
        q = stock_data.get_quote(h["ticker"])
        price = q.get("price") or h["buy_price"]
        cost = h["shares"] * h["buy_price"]
        value = h["shares"] * price
        pnl = value - cost
        pnl_pct = (pnl / cost * 100) if cost else 0
        total_cost += cost
        total_value += value
        rows.append({
            **h,
            "name": q.get("name"),
            "current_price": price,
            "cost": round(cost, 2),
            "value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "change_pct": q.get("change_pct"),
            "currency": q.get("currency"),
        })

    total_pnl = total_value - total_cost
    # คำนวณสัดส่วนแต่ละตัว (สำหรับ risk/allocation)
    for r in rows:
        r["weight"] = round(r["value"] / total_value * 100, 2) if total_value else 0

    return {
        "holdings": rows,
        "totals": {
            "cost": round(total_cost, 2),
            "value": round(total_value, 2),
            "pnl": round(total_pnl, 2),
            "pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost else 0,
            "count": len(rows),
        },
    }
