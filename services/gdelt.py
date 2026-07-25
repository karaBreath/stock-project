"""
GDELT service — ข่าวทั่วโลก 65 ภาษา (ฟรี ไม่ต้องใช้ API key)

ใช้ 2 API ของ GDELT Project:
  - GEO 2.0  : จุดข่าวพร้อมพิกัด lat/lon  -> เอาไปปักบน "ลูกโลก" 3D
  - DOC 2.0  : รายการข่าว + timeline ของ Tone (ความบวก/ลบของข่าว)

Tone คือคะแนนอารมณ์ข่าวที่ GDELT คำนวณมาให้แล้ว ปกติอยู่ราว -10..+10
(ติดลบ = ข่าวร้าย) ใช้แทน keyword-sentiment เดิมได้แม่นกว่ามาก

หมายเหตุ: ทุกฟังก์ชันมี fallback เมื่อ network ล้ม และ cache ลงใน SQLite
"""
import re
import datetime as dt
import urllib.parse

from config import Config
from database import cache_get, cache_set

try:
    import requests
    _REQ_OK = True
except Exception:  # pragma: no cover
    requests = None
    _REQ_OK = False


_UA = "NEBULA-Stock-App/1.0 (educational stock research)"


# ---------------------------------------------------------------------------
# low-level fetch
# ---------------------------------------------------------------------------
def _fetch_json(path: str, params: dict):
    """เรียก GDELT แล้วคืน dict; คืน None ถ้าล้มเหลว (GDELT บางทีตอบ text ไม่ใช่ json)"""
    if not _REQ_OK:
        return None
    url = f"{Config.GDELT_BASE}/{path}"
    try:
        r = requests.get(url, params=params, timeout=Config.GDELT_TIMEOUT,
                         headers={"User-Agent": _UA})
        if r.status_code != 200 or not r.text.strip():
            return None
        return r.json()
    except Exception:
        return None


def _day_of(stamp: str) -> str:
    """'20260725T063000Z' -> '2026-07-25'"""
    s = (stamp or "").strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]


# ---------------------------------------------------------------------------
# 1) จุดข่าวบนแผนที่ (สำหรับลูกโลก 3D)
# ---------------------------------------------------------------------------
def world_points(query: str = "", timespan: str = "24h", theme: str = "") -> dict:
    """
    คืนจุดข่าวพร้อมพิกัดสำหรับปักบนลูกโลก
    ถ้าไม่ระบุ query จะใช้ query ของ theme (จาก Config.WORLD_THEMES)
    """
    color = "#4dd4ff"
    label = "ข่าวทั่วโลก"
    if theme and theme in Config.WORLD_THEMES:
        label, q, color = Config.WORLD_THEMES[theme]
        query = query or q
    query = query or "stock market OR economy"

    cache_key = f"gdelt:geo:{theme}:{query}:{timespan}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"theme": theme, "label": label, "color": color, "query": query,
           "timespan": timespan, "points": [], "ok": False}

    data = _fetch_json("geo/geo", {
        "query": query,
        "format": "GeoJSON",
        "mode": "PointData",
        "timespan": timespan,
        "maxpoints": Config.GDELT_MAX_POINTS,
    })

    if not data or not isinstance(data, dict):
        out["error"] = "ดึงข้อมูล GDELT ไม่ได้ (network หรือ rate limit)"
        return out

    for f in (data.get("features") or []):
        try:
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            props = f.get("properties") or {}
            try:
                count = int(float(props.get("count", 1) or 1))
            except (TypeError, ValueError):
                count = 1
            out["points"].append({
                "lat": lat,
                "lon": lon,
                "name": props.get("name") or "",
                "count": count,
                "color": color,
                "articles": _links_from_html(props.get("html", ""))[:5],
            })
        except (TypeError, ValueError):
            continue

    out["ok"] = bool(out["points"])
    out["total"] = len(out["points"])
    if out["ok"]:
        cache_set(cache_key, out, Config.GDELT_CACHE_TTL)
    return out


_A_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _links_from_html(html: str):
    """ดึงลิงก์ข่าวออกจาก popup html ที่ GDELT ส่งมา"""
    items = []
    for url, text in _A_RE.findall(html or ""):
        title = _TAG_RE.sub("", text or "").strip()
        if url.startswith("http") and title:
            items.append({"title": title[:160], "url": url})
    return items


def all_theme_points(timespan: str = "24h") -> dict:
    """ดึงจุดข่าวของทุกธีมรวมกัน (ใช้ตอนเปิดหน้าลูกโลกครั้งแรก)"""
    themes = []
    points = []
    for key in Config.WORLD_THEMES:
        res = world_points(theme=key, timespan=timespan)
        themes.append({
            "key": key,
            "label": res["label"],
            "color": res["color"],
            "count": len(res["points"]),
            "ok": res["ok"],
        })
        for p in res["points"]:
            p["theme"] = key
            points.append(p)
    return {"themes": themes, "points": points, "timespan": timespan,
            "ok": bool(points),
            "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}


# ---------------------------------------------------------------------------
# 2) Timeline ของ Tone — หัวใจของเครื่องเรียนรู้ (ย้อนหลังได้ถึง 1 ปี)
# ---------------------------------------------------------------------------
def tone_timeline(query: str, timespan: str = "180d") -> dict:
    """
    คืน {day: average_tone} รายวัน
    จุดสำคัญ: GDELT ให้ข้อมูล "ย้อนหลัง" ได้ทันที ทำให้หาความสัมพันธ์ได้ตั้งแต่วันแรก
    ไม่ต้องรอสะสมข้อมูลเป็นเดือน
    """
    cache_key = f"gdelt:tone:{query}:{timespan}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"query": query, "timespan": timespan, "series": {}, "ok": False}
    data = _fetch_json("doc/doc", {
        "query": query,
        "mode": "TimelineTone",
        "format": "json",
        "timespan": timespan,
    })
    series = _parse_timeline(data)
    if series:
        out["series"] = series
        out["ok"] = True
        cache_set(cache_key, out, Config.GDELT_TIMELINE_CACHE_TTL)
    else:
        out["error"] = "ดึง timeline จาก GDELT ไม่ได้"
    return out


def volume_timeline(query: str, timespan: str = "180d") -> dict:
    """คืน {day: volume%} — ปริมาณข่าว (สัดส่วนของข่าวทั้งโลกที่พูดเรื่องนี้)"""
    cache_key = f"gdelt:vol:{query}:{timespan}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"query": query, "timespan": timespan, "series": {}, "ok": False}
    data = _fetch_json("doc/doc", {
        "query": query,
        "mode": "TimelineVol",
        "format": "json",
        "timespan": timespan,
    })
    series = _parse_timeline(data)
    if series:
        out["series"] = series
        out["ok"] = True
        cache_set(cache_key, out, Config.GDELT_TIMELINE_CACHE_TTL)
    else:
        out["error"] = "ดึง timeline จาก GDELT ไม่ได้"
    return out


def _parse_timeline(data) -> dict:
    """
    GDELT timeline format:
      {"timeline":[{"series":"Average Tone","data":[{"date":"20260718T000000Z","value":-1.2}]}]}
    ถ้ามีหลายจุดในวันเดียวกัน จะเฉลี่ยให้
    """
    if not data or not isinstance(data, dict):
        return {}
    buckets = {}
    for s in (data.get("timeline") or []):
        for pt in (s.get("data") or []):
            day = _day_of(str(pt.get("date", "")))
            val = pt.get("value")
            if not day or val is None:
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            buckets.setdefault(day, []).append(val)
        break  # ใช้ series แรกพอ
    return {d: sum(v) / len(v) for d, v in buckets.items() if v}


# ---------------------------------------------------------------------------
# 3) รายการข่าว
# ---------------------------------------------------------------------------
def articles(query: str, limit: int = 20, timespan: str = "24h") -> dict:
    cache_key = f"gdelt:art:{query}:{limit}:{timespan}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"query": query, "items": [], "ok": False}
    data = _fetch_json("doc/doc", {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max(1, min(250, limit)),
        "timespan": timespan,
        "sort": "DateDesc",
    })
    for a in ((data or {}).get("articles") or []):
        out["items"].append({
            "title": a.get("title", ""),
            "link": a.get("url"),
            "source": a.get("domain", ""),
            "country": a.get("sourcecountry", ""),
            "language": a.get("language", ""),
            "image": a.get("socialimage") or "",
            "published": a.get("seendate", ""),
        })
    out["ok"] = bool(out["items"])
    if out["ok"]:
        cache_set(cache_key, out, Config.GDELT_CACHE_TTL)
    return out


# ---------------------------------------------------------------------------
# 4) สัญญาณธีมข่าวโลก ณ ปัจจุบัน (ใช้ใน dashboard + snapshot)
# ---------------------------------------------------------------------------
def theme_signals(timespan: str = "7d") -> dict:
    """
    คืน tone ล่าสุด + ค่าเฉลี่ยของแต่ละธีมข่าวโลก
    tone ต่ำกว่าค่าเฉลี่ยมาก = ข่าวแย่ผิดปกติ = ตลาดมักตอบสนอง
    """
    cache_key = f"gdelt:signals:{timespan}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    rows = []
    for key, (label, q, color) in Config.WORLD_THEMES.items():
        tl = tone_timeline(q, timespan=timespan)
        ser = tl.get("series") or {}
        days = sorted(ser)
        latest = ser[days[-1]] if days else None
        avg = (sum(ser.values()) / len(ser)) if ser else None
        rows.append({
            "key": key,
            "label": label,
            "color": color,
            "tone": round(latest, 3) if latest is not None else None,
            "avg_tone": round(avg, 3) if avg is not None else None,
            "deviation": round(latest - avg, 3) if (latest is not None and avg is not None) else None,
            "days": len(ser),
            "ok": tl.get("ok", False),
        })

    result = {"rows": rows, "timespan": timespan,
              "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
              "ok": any(r["ok"] for r in rows)}
    if result["ok"]:
        cache_set(cache_key, result, Config.GDELT_CACHE_TTL)
    return result


# ---------------------------------------------------------------------------
# 5) tone ของหุ้นรายตัว — ใช้อัปเกรด services/sentiment.py
# ---------------------------------------------------------------------------
def stock_tone(ticker: str, name: str = "", timespan: str = "7d") -> dict:
    """
    หา tone ข่าวของหุ้นตัวหนึ่ง แล้วแปลงเป็นคะแนน 0-100
    tone ปกติอยู่ราว -10..+10 -> map เป็น 0..100 (0 tone = 50 คะแนน)
    """
    base = (name or "").strip() or ticker.replace(".BK", "")
    q = f'"{base}"' if " " in base else base

    tl = tone_timeline(q, timespan=timespan)
    ser = tl.get("series") or {}
    if not ser:
        return {"ok": False, "ticker": ticker, "query": q,
                "tone": None, "score": None, "days": 0}

    days = sorted(ser)
    latest = ser[days[-1]]
    avg = sum(ser.values()) / len(ser)
    score = int(max(0, min(100, round(50 + latest * 5))))
    return {
        "ok": True,
        "ticker": ticker,
        "query": q,
        "tone": round(latest, 3),
        "avg_tone": round(avg, 3),
        "score": score,
        "days": len(ser),
    }


def theme_query(key: str) -> str:
    """helper: คืน GDELT query ของธีม"""
    t = Config.WORLD_THEMES.get(key)
    return t[1] if t else ""
