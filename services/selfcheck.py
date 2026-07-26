"""
Self-check — ตรวจว่าแหล่งข้อมูลภายนอกทุกตัวใช้งานได้จริงไหม

ทำไมต้องมี
----------
โค้ดส่วนที่คุยกับ GDELT / Yahoo เขียนตามเอกสาร แต่ API พวกนี้เปลี่ยนรูปแบบ
ได้ตลอด และบางตัวมี rate limit หรือใช้ไม่ได้ในบางประเทศ ถ้าไม่มีตัวตรวจ
เวลาพังจะเห็นแค่ "ไม่มีข้อมูล" โดยไม่รู้ว่าพังตรงไหน

หน้านี้จะยิงทดสอบทีละแหล่ง แล้วรายงานว่า
  - ต่อได้ไหม / ใช้เวลากี่ ms
  - ข้อมูลที่ได้กลับมา "หน้าตา" เป็นยังไง (คีย์อะไรบ้าง ตัวอย่างค่า)
  - ถ้าพัง พังเพราะอะไร

ผลลัพธ์ก็อปวางส่งต่อได้เลย เพื่อให้ดีบักได้โดยไม่ต้องเดา
"""
import time
import datetime as dt

from config import Config


def _timed(fn):
    """รันแล้วคืน (ผลลัพธ์, เวลาเป็น ms, error)"""
    t0 = time.time()
    try:
        return fn(), round((time.time() - t0) * 1000), None
    except Exception as e:
        return None, round((time.time() - t0) * 1000), f"{type(e).__name__}: {e}"


def _check(group, name, hint, fn, validate):
    """
    fn      -> ดึงข้อมูล
    validate(data) -> (ok: bool, detail: str, sample: any)
    """
    data, ms, err = _timed(fn)
    if err:
        return {"group": group, "name": name, "hint": hint, "ok": False,
                "ms": ms, "detail": "เรียกไม่สำเร็จ", "error": err, "sample": None}
    try:
        ok, detail, sample = validate(data)
    except Exception as e:
        ok, detail, sample = False, "อ่านผลลัพธ์ไม่ได้", None
        err = f"{type(e).__name__}: {e}"
    return {"group": group, "name": name, "hint": hint, "ok": bool(ok),
            "ms": ms, "detail": detail, "error": err, "sample": sample}


def _keys(d, limit=12):
    if isinstance(d, dict):
        return list(d.keys())[:limit]
    if isinstance(d, list):
        return f"list({len(d)})"
    return type(d).__name__


# ---------------------------------------------------------------------------
# 1) ไลบรารีที่ต้องมี
# ---------------------------------------------------------------------------
def _lib_checks():
    out = []
    for mod, why in [("requests", "เรียก GDELT"), ("yfinance", "ราคาหุ้น"),
                     ("pandas", "คำนวณ"), ("numpy", "สถิติ"),
                     ("feedparser", "ข่าว Google News")]:
        def fn(m=mod):
            import importlib
            lib = importlib.import_module(m)
            return getattr(lib, "__version__", "?")
        out.append(_check("ไลบรารี", mod, why, fn,
                          lambda v: (True, f"เวอร์ชัน {v}", None)))
    return out


# ---------------------------------------------------------------------------
# 2) GDELT — 3 API ที่ใช้จริง
# ---------------------------------------------------------------------------
def _gdelt_checks():
    from services import gdelt
    out = []

    # จุดข่าวบนลูกโลก — ตอนนี้สร้างจาก ArtList + ประเทศต้นทาง
    # (GDELT ปิด GEO 2.0 API แล้ว ยิงเข้าไปได้ 404 ทุกแบบ)
    def geo():
        return gdelt.world_points(theme="market", timespan="24h")

    def geo_ok(d):
        pts = (d or {}).get("points") or []
        if not pts:
            return False, (d or {}).get("error") or "ไม่มีจุดข่าว (โดนจำกัดอัตราการเรียก?)", None
        top = pts[0]
        return True, (f"{len(pts)} ประเทศ · มากสุด {top['name']} {top['count']} ข่าว "
                      f"(จาก {d.get('articles_seen')} ข่าว)"), {
            "countries": len(pts), "articles_seen": d.get("articles_seen"),
            "top": {"name": top["name"], "count": top["count"]}}

    out.append(_check("GDELT", "จุดข่าวบนลูกโลก (ArtList + ประเทศ)",
                      "ถ้าพัง = ลูกโลกไม่มีจุดข่าว", geo, geo_ok))

    # DOC 2.0 TimelineTone — หัวใจของเครื่องเรียนรู้
    def tone():
        return gdelt._fetch_json("doc/doc", {
            "query": "inflation", "mode": "TimelineTone",
            "format": "json", "timespan": "30d"})

    def tone_ok(d):
        if not d:
            return False, "ไม่มีข้อมูลกลับมา", None
        tl = (d or {}).get("timeline") or []
        if not tl:
            return False, f"ไม่มี timeline · คีย์ที่ได้: {_keys(d)}", {"keys": _keys(d)}
        pts = (tl[0] or {}).get("data") or []
        first = pts[0] if pts else {}
        return bool(pts), f"{len(pts)} จุดเวลา · series: {(tl[0] or {}).get('series')}", {
            "series": (tl[0] or {}).get("series"), "points": len(pts),
            "first_point": first, "date_format": str(first.get("date"))[:20]}

    out.append(_check("GDELT", "DOC 2.0 TimelineTone",
                      "ถ้าพัง = เครื่องเรียนรู้ไม่มีข้อมูลข่าว", tone, tone_ok))

    # เพดาน timespan — ทดสอบจริงแล้วพบว่า GDELT รับได้ถึง ~90 วัน
    # (100d ขึ้นไปตอบ 429 "query too large") โค้ดจึงตัดให้อัตโนมัติ
    def tone_long():
        return gdelt._fetch_json("doc/doc", {
            "query": "inflation", "mode": "TimelineTone",
            "format": "json", "timespan": f"{gdelt.MAX_TIMESPAN_DAYS}d"})

    def tone_long_ok(d):
        if not d:
            return False, "ต่อ GDELT ไม่ได้ (ดูผลของ TimelineTone ด้านบน)", None
        pts = (((d or {}).get("timeline") or [{}])[0] or {}).get("data") or []
        if not pts:
            return False, f"ตอบกลับแต่ไม่มีข้อมูลที่ {gdelt.MAX_TIMESPAN_DAYS} วัน", None
        days = {str(p.get("date", ""))[:8] for p in pts}
        return True, f"รับได้ · {len(pts)} จุด ครอบคลุม {len(days)} วัน", {
            "points": len(pts), "distinct_days": len(days)}

    out.append(_check("GDELT", f"TimelineTone ย้อนหลัง {gdelt.MAX_TIMESPAN_DAYS} วัน",
                      "เพดานที่ GDELT ยอมรับ (ยาวกว่านี้โดนปฏิเสธ)",
                      tone_long, tone_long_ok))

    # ArtList — รายการข่าว
    def art():
        return gdelt._fetch_json("doc/doc", {
            "query": "inflation", "mode": "ArtList", "format": "json",
            "maxrecords": 5, "timespan": "24h", "sort": "DateDesc"})

    def art_ok(d):
        arts = (d or {}).get("articles") or []
        if not arts:
            return False, f"ไม่มี articles · คีย์: {_keys(d)}", None
        return True, f"{len(arts)} ข่าว · คีย์: {list(arts[0].keys())[:8]}", {
            "count": len(arts), "keys": list(arts[0].keys())[:8],
            "first_title": str(arts[0].get("title"))[:70]}

    out.append(_check("GDELT", "DOC 2.0 ArtList (รายการข่าว)",
                      "ถ้าพัง = ไม่มีรายการข่าวโลก", art, art_ok))

    return out


# ---------------------------------------------------------------------------
# 3) Yahoo Finance
# ---------------------------------------------------------------------------
def _yahoo_checks():
    from services import stock_data
    out = []

    def q(sym):
        return lambda: stock_data.get_quote(sym)

    def q_ok(d):
        if not d or not d.get("ok"):
            return False, d.get("error", "ดึงราคาไม่ได้") if d else "ไม่มีข้อมูล", None
        return True, f"ราคา {d.get('price')} {d.get('currency')}", {
            "price": d.get("price"), "name": str(d.get("name"))[:40],
            "pe": d.get("pe"), "sector": d.get("sector")}

    for sym, why in [("AAPL", "หุ้นสหรัฐ"), ("SPY", "กองทุน/ETF"),
                     ("PTT.BK", "หุ้นไทย")]:
        out.append(_check("Yahoo ราคา", sym, why, q(sym), q_ok))

    # ประวัติราคายาว — หน้าบทเรียนวิกฤตต้องใช้ period=max
    def hist_long():
        return stock_data.get_history("^GSPC", period="max")

    def hist_long_ok(d):
        c = (d or {}).get("candles") or []
        if len(c) < 1000:
            return False, f"ได้แค่ {len(c)} แท่ง — หน้าบทเรียนวิกฤตต้องการย้อนหลังหลายปี", None
        return True, f"{len(c)} แท่ง ตั้งแต่ {c[0]['date']} ถึง {c[-1]['date']}", {
            "candles": len(c), "from": c[0]["date"], "to": c[-1]["date"]}

    out.append(_check("Yahoo ราคา", "^GSPC period=max",
                      "ถ้าพัง = หน้าบทเรียนวิกฤตใช้ไม่ได้", hist_long, hist_long_ok))
    return out


# ---------------------------------------------------------------------------
# 4) สัญลักษณ์มหภาค + ตัวชี้วัดวิกฤต (ตัวไหนดึงไม่ได้บ้าง)
# ---------------------------------------------------------------------------
def _symbol_checks():
    from services import stock_data, crisis
    out = []

    symbols = {sym: label for sym, label in
               ((v[0], v[1]) for v in Config.MACRO_SYMBOLS.values())}
    for cfg in crisis.WARNING_INDICATORS.values():
        symbols.setdefault(cfg["a"], cfg["label"])
        if cfg.get("b"):
            symbols.setdefault(cfg["b"], cfg["label"])

    def mk(sym):
        return lambda: stock_data.get_quote(sym)

    def ok(d):
        if not d or not d.get("ok") or d.get("price") is None:
            return False, "ดึงไม่ได้ / สัญลักษณ์อาจเปลี่ยน", None
        return True, f"{d.get('price')}", {"price": d.get("price")}

    for sym, label in symbols.items():
        out.append(_check("สัญลักษณ์", sym, label, mk(sym), ok))
    return out


# ---------------------------------------------------------------------------
# 5) ฐานข้อมูล + การตั้งค่า
# ---------------------------------------------------------------------------
def _local_checks():
    from database import obs_stats, query
    out = []

    def db():
        obs_stats()
        return query("SELECT COUNT(*) AS c FROM correlations", one=True)

    out.append(_check("ในเครื่อง", "ฐานข้อมูล SQLite", "อ่าน/เขียนได้ไหม", db,
                      lambda d: (True, f"correlations {d.get('c', 0)} แถว", d)))

    out.append(_check("ในเครื่อง", "เก็บข้อมูลอัตโนมัติ",
                      "เธรดสะสมข้อมูลของเครื่องเรียนรู้",
                      lambda: Config.LEARN_AUTO,
                      lambda v: (True, "เปิด" if v else "ปิด (ตั้ง LEARN_AUTO=1 เพื่อเปิด)", None)))

    out.append(_check("ในเครื่อง", "LINE แจ้งเตือน", "ตั้ง token แล้วหรือยัง",
                      lambda: bool(Config.LINE_CHANNEL_TOKEN or Config.LINE_NOTIFY_TOKEN),
                      lambda v: (True, "ตั้งค่าแล้ว" if v else "ยังไม่ได้ตั้ง (ไม่บังคับ)", None)))
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run(include_symbols: bool = True) -> dict:
    checks = []
    checks += _local_checks()
    checks += _lib_checks()
    checks += _gdelt_checks()
    checks += _yahoo_checks()
    if include_symbols:
        checks += _symbol_checks()

    # ตัวที่ "ไม่บังคับ" ไม่ควรทำให้ผลรวมกลายเป็นล้มเหลว
    optional = {"LINE แจ้งเตือน", "เก็บข้อมูลอัตโนมัติ"}
    critical = [c for c in checks if c["name"] not in optional]
    failed = [c for c in critical if not c["ok"]]

    groups = {}
    for c in checks:
        g = groups.setdefault(c["group"], {"total": 0, "ok": 0})
        g["total"] += 1
        g["ok"] += 1 if c["ok"] else 0

    return {
        "ok": not failed,
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total": len(checks),
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": len(failed),
        "groups": groups,
        "checks": checks,
        "failed_names": [f"{c['group']}/{c['name']}" for c in failed],
        "verdict": ("ทุกอย่างพร้อมใช้งาน ✅" if not failed
                    else f"มี {len(failed)} รายการที่ใช้ไม่ได้ — ดูรายละเอียดด้านล่าง"),
    }


def as_text(result: dict) -> str:
    """สรุปเป็นข้อความสั้น ๆ ก็อปวางส่งต่อได้"""
    lines = [f"SELF-CHECK {result.get('checked_at')} — "
             f"ผ่าน {result.get('passed')}/{result.get('total')}"]
    for c in result.get("checks", []):
        mark = "OK  " if c["ok"] else "FAIL"
        lines.append(f"[{mark}] {c['group']}/{c['name']} ({c['ms']}ms) — {c['detail']}"
                     + (f" | {c['error']}" if c.get("error") else ""))
    return "\n".join(lines)
