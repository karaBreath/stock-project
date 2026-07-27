"""
สะพานเชื่อม NEBULA ↔ volume-edge (ระบบเทรด MT5 ที่บ้าน)

ทำไมต้องเชื่อม
-------------
สองระบบนี้เก่งคนละอย่าง และไม่ทับกันเลย:

  volume-edge (รันที่บ้าน + MT5)     NEBULA (รันบนคลาวด์ 24 ชม.)
  ─────────────────────────────      ────────────────────────────
  · ไม้จริงที่เปิดอยู่ใน MT5          · ข่าวโลก GDELT + เครื่องเรียนรู้
  · เหตุผลเข้าไม้ (ไทย) + journal     · บทเรียนวิกฤต 25 ปี
  · Volume Profile + setup VAB/VAR    · แล็บกลยุทธ์ (walk-forward)
  · คุมความเสี่ยง/ยิงออเดอร์          · เปิดจากไอแพดได้ทุกที่

จุดร่วมที่ทำให้ "1+1 มากกว่า 2":
เอา **ไม้จริงที่ถืออยู่** จาก volume-edge มาผ่าน **เครื่องอ่านข่าวโลก** ของ NEBULA
→ รู้ว่าตอนนี้ข่าวโลกกำลังหนุนหรือกดดันไม้ที่ถืออยู่จริง ๆ

ทิศทางการเชื่อม
--------------
NEBULA เป็นฝ่าย "ดึง" เสมอ เพราะเปิดตลอด ส่วนเครื่องที่บ้านเปิด ๆ ปิด ๆ
และดึงเฉพาะคำสั่งอ่าน (GET) เท่านั้น — ไม่มีทางสั่งซื้อขายข้ามระบบได้
(ฝั่ง volume-edge เองก็ล็อกไว้แล้วว่าจากภายนอกเป็นโหมดดูอย่างเดียว)

ตั้งค่า (Environment variables บน Render)
  VE_BASE_URL = https://volume.twinpatta.com
  VE_AUTH_KEY = <กุญแจเดียวกับ AUTH_KEY ใน .env ของ volume-edge>
ไม่ตั้ง = ปิดฟีเจอร์นี้เงียบ ๆ ไม่กระทบส่วนอื่น
"""
import datetime as dt

from config import Config
from database import cache_get, cache_set

try:
    import requests
    _REQ_OK = True
except Exception:  # pragma: no cover
    requests = None
    _REQ_OK = False


TIMEOUT = 12          # เครื่องที่บ้านอาจหลับ/เน็ตบ้านช้า — อย่าให้หน้าเว็บรอนาน
CACHE_TTL = 45        # ข้อมูลไม้เปิดเปลี่ยนบ่อย แต่ก็ไม่ควรถล่มเครื่องที่บ้าน


def configured() -> bool:
    return bool(Config.VE_BASE_URL)


def _get(path: str, params: dict = None, ttl: int = CACHE_TTL):
    """
    ยิง GET ไปที่ volume-edge · คืน (data, error)
    error เป็นข้อความไทยที่เอาไปโชว์ได้เลย
    """
    if not configured():
        return None, "ยังไม่ได้ตั้งค่าที่อยู่ของระบบ MT5 (VE_BASE_URL)"
    if not _REQ_OK:
        return None, "ไม่มีไลบรารี requests"

    key = f"ve:{path}:{params}"
    cached = cache_get(key)
    if cached is not None:
        return cached, None

    url = Config.VE_BASE_URL.rstrip("/") + path
    q = dict(params or {})
    if Config.VE_AUTH_KEY:
        q["key"] = Config.VE_AUTH_KEY
    try:
        r = requests.get(url, params=q, timeout=TIMEOUT,
                         headers={"User-Agent": "NEBULA-bridge/1.0"})
    except Exception:
        return None, ("ต่อเครื่องที่บ้านไม่ได้ — เครื่องอาจปิดอยู่ "
                      "หรือ tunnel ไม่ทำงาน")
    if r.status_code == 401:
        return None, "กุญแจไม่ถูกต้อง (ตรวจ VE_AUTH_KEY ให้ตรงกับ AUTH_KEY ของ volume-edge)"
    if r.status_code == 403:
        return None, "ระบบที่บ้านยังไม่เปิดรับจากภายนอก (ยังไม่ได้ตั้ง AUTH_KEY)"
    if r.status_code != 200:
        return None, f"ระบบที่บ้านตอบกลับผิดปกติ (HTTP {r.status_code})"
    try:
        data = r.json()
    except Exception:
        return None, "อ่านข้อมูลจากระบบที่บ้านไม่ได้ (รูปแบบไม่ใช่ JSON)"

    if ttl:
        cache_set(key, data, ttl)
    return data, None


# ---------------------------------------------------------------------------
# ดึงข้อมูลรายอย่าง
# ---------------------------------------------------------------------------
def status() -> dict:
    data, err = _get("/api/system/status", ttl=20)
    if err:
        return {"ok": False, "error": err, "online": False}
    mt5 = data.get("mt5") or {}
    market = data.get("market") or {}
    regime = data.get("regime") or {}
    return {
        "ok": True,
        "online": True,
        "halted": bool(data.get("halted")),
        "auto_trade": data.get("auto_trade"),
        "mt5": {
            "connected": bool(mt5.get("connected")),
            "demo": mt5.get("demo"),
            "equity": mt5.get("equity"),
            "error": mt5.get("error"),
        },
        "market_open": market.get("open"),
        "regime": {"level": regime.get("level"), "detail": regime.get("detail")},
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def positions(with_catalyst: bool = True) -> dict:
    """
    ไม้ที่เปิดอยู่จริงใน MT5 + เหตุผลตอนเข้า (จาก volume-edge)
    แล้ว **ต่อยอดด้วยข่าวโลกของ NEBULA**: ไม้นี้ตอนนี้ข่าวหนุนหรือกดดัน
    """
    data, err = _get("/api/positions")
    if err:
        return {"ok": False, "error": err, "positions": []}

    rows = list(data.get("positions") or [])
    if with_catalyst:
        _attach_catalyst(rows)

    return {
        "ok": True,
        "positions": rows,
        "summary": data.get("summary"),
        "total_pnl": data.get("total_pnl"),
        "count": len(rows),
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _attach_catalyst(rows):
    """เติมมุมมองข่าวโลกของ NEBULA ให้ไม้แต่ละตัว (นี่คือจุดที่สองระบบมาบรรจบกัน)"""
    from services import correlation
    for p in rows:
        sym = (p.get("symbol") or "").upper()
        if not sym:
            continue
        try:
            cat = correlation.catalyst_signal(sym)
        except Exception:
            continue
        p["news"] = {
            "adjust": cat.get("adjust", 0),
            "label": cat.get("label") or cat.get("hint") or "ยังไม่ได้เรียนรู้หุ้นตัวนี้",
            "reasons": [r.get("text") for r in (cat.get("reasons") or [])][:2],
            "learned": bool(cat.get("ok")),
        }


def trades(limit: int = 50, status_filter: str = "all") -> dict:
    data, err = _get(f"/api/trades", {"limit": limit, "status": status_filter}, ttl=60)
    if err:
        return {"ok": False, "error": err, "trades": []}
    return {"ok": True, "trades": data if isinstance(data, list) else [],
            "count": len(data or [])}


def signals(limit: int = 40) -> dict:
    """สัญญาณล่าสุด — รวมทั้งที่ 'ไม่ซื้อ' พร้อมเหตุผลไทย (บทเรียนอยู่ตรงนี้)"""
    data, err = _get("/api/signals", {"limit": limit}, ttl=60)
    if err:
        return {"ok": False, "error": err, "signals": []}
    return {"ok": True, "signals": data if isinstance(data, list) else []}


def setup_stats() -> dict:
    """สถิติจริงต่อ setup จากไม้ที่ปิดแล้ว (ของจริง ไม่ใช่ backtest)"""
    data, err = _get("/api/stats/setups", ttl=300)
    if err:
        return {"ok": False, "error": err, "rows": []}
    return {"ok": True, "rows": data if isinstance(data, list) else []}


def equity(limit: int = 400) -> dict:
    data, err = _get("/api/equity", {"limit": limit}, ttl=300)
    if err:
        return {"ok": False, "error": err, "curve": []}
    rows = data if isinstance(data, list) else []
    return {"ok": True, "curve": rows, "count": len(rows)}


def screener_latest() -> dict:
    """ผลสแกนล่าสุดของ volume-edge (หุ้นที่กำลังเข้า setup)"""
    data, err = _get("/api/screener/latest", ttl=120)
    if err:
        return {"ok": False, "error": err, "candidates": []}
    return {"ok": True, **(data if isinstance(data, dict) else {})}


def overview() -> dict:
    """รวมทุกอย่างที่หน้าเดียวต้องใช้ — ยิงทีเดียวจบ ไม่ต้องรอหลายรอบ"""
    from concurrent.futures import ThreadPoolExecutor
    if not configured():
        return {"ok": False, "configured": False,
                "error": "ยังไม่ได้เชื่อมระบบ MT5 — ตั้งค่า VE_BASE_URL และ VE_AUTH_KEY"}

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_st = ex.submit(status)
        f_pos = ex.submit(positions)
        f_sig = ex.submit(signals, 25)
        f_stats = ex.submit(setup_stats)
        st, pos, sig, stats = f_st.result(), f_pos.result(), f_sig.result(), f_stats.result()

    return {
        "ok": st.get("ok", False),
        "configured": True,
        "status": st,
        "positions": pos,
        "signals": sig,
        "setup_stats": stats,
        "base_url": Config.VE_BASE_URL,
    }
