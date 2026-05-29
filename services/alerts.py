"""
Alerts + LINE notification

- เก็บเงื่อนไขแจ้งเตือนใน SQLite (ราคาทะลุ/ต่ำกว่า, RSI)
- ตรวจสอบเงื่อนไขกับราคา/อินดิเคเตอร์ปัจจุบัน
- ส่งแจ้งเตือนผ่าน LINE Messaging API (push) — รองรับ token เดิมของ LINE Notify ด้วย
"""
import requests

from config import Config
from database import query, execute
from services import stock_data, technical


# ---------------- LINE ----------------
def send_line(message: str) -> dict:
    """ส่งข้อความเข้า LINE; เลือกช่องทางตาม config ที่ตั้งไว้"""
    # 1) LINE Messaging API (แนะนำ — LINE Notify ปิดบริการแล้ว)
    if Config.LINE_CHANNEL_TOKEN and Config.LINE_USER_ID:
        try:
            r = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {Config.LINE_CHANNEL_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"to": Config.LINE_USER_ID, "messages": [{"type": "text", "text": message}]},
                timeout=10,
            )
            return {"ok": r.status_code == 200, "status": r.status_code, "channel": "messaging-api"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # 2) LINE Notify (เผื่อยังมี token เดิม)
    if Config.LINE_NOTIFY_TOKEN:
        try:
            r = requests.post(
                "https://notify-api.line.me/api/notify",
                headers={"Authorization": f"Bearer {Config.LINE_NOTIFY_TOKEN}"},
                data={"message": message}, timeout=10,
            )
            return {"ok": r.status_code == 200, "status": r.status_code, "channel": "notify"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "ยังไม่ได้ตั้งค่า LINE token (ดู README หัวข้อ LINE)"}


# ---------------- CRUD ----------------
def list_alerts():
    return query("SELECT * FROM alerts ORDER BY active DESC, created_at DESC")


def add_alert(ticker, condition, target, note=None):
    ticker = stock_data.normalize_ticker(ticker)
    aid = execute(
        "INSERT INTO alerts(ticker, condition, target, note) VALUES(?,?,?,?)",
        (ticker, condition, float(target), note),
    )
    return query("SELECT * FROM alerts WHERE id = ?", (aid,), one=True)


def delete_alert(aid):
    execute("DELETE FROM alerts WHERE id = ?", (aid,))
    return {"deleted": aid}


# ---------------- engine ----------------
def _condition_met(alert, quote, tech_last):
    cond, target = alert["condition"], alert["target"]
    price = quote.get("price")
    rsi_v = tech_last.get("rsi") if tech_last else None
    if cond == "above" and price is not None:
        return price >= target
    if cond == "below" and price is not None:
        return price <= target
    if cond == "rsi_above" and rsi_v is not None:
        return rsi_v >= target
    if cond == "rsi_below" and rsi_v is not None:
        return rsi_v <= target
    return False


def check_alerts(send=True) -> dict:
    """ตรวจ alert ที่ active ทั้งหมด ถ้าเข้าเงื่อนไขให้ส่ง LINE และปิด alert"""
    alerts = query("SELECT * FROM alerts WHERE active = 1")
    triggered = []
    # cache เทคนิคัลต่อ ticker เพื่อไม่ดึงซ้ำ
    tech_cache = {}
    for a in alerts:
        quote = stock_data.get_quote(a["ticker"])
        last = None
        if a["condition"].startswith("rsi"):
            if a["ticker"] not in tech_cache:
                t = technical.analyze(a["ticker"])
                tech_cache[a["ticker"]] = t.get("last", {})
            last = tech_cache[a["ticker"]]

        if _condition_met(a, quote, last):
            cond_th = {
                "above": "ทะลุขึ้นเหนือ", "below": "ลงต่ำกว่า",
                "rsi_above": "RSI สูงกว่า", "rsi_below": "RSI ต่ำกว่า",
            }.get(a["condition"], a["condition"])
            msg = (f"🔔 แจ้งเตือนหุ้น {a['ticker']}\n"
                   f"{cond_th} {a['target']}\n"
                   f"ราคาปัจจุบัน: {quote.get('price')}")
            if a.get("note"):
                msg += f"\nโน้ต: {a['note']}"
            res = send_line(msg) if send else {"ok": True, "skipped": True}
            execute("UPDATE alerts SET active = 0, triggered_at = strftime('%s','now') WHERE id = ?", (a["id"],))
            triggered.append({"alert": a, "message": msg, "line_result": res})

    return {"checked": len(alerts), "triggered": triggered}
