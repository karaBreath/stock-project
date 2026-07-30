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
import threading
import time
import urllib.parse

from config import Config
from database import cache_get, cache_set
from services import country_geo

try:
    import requests
    _REQ_OK = True
except Exception:  # pragma: no cover
    requests = None
    _REQ_OK = False


_UA = "NEBULA-Stock-App/1.0 (educational stock research)"

# เพดาน timespan ที่ GDELT ยอมรับจริง (ทดสอบจากเซิร์ฟเวอร์จริง)
#   30d / 90d / 3m -> HTTP 200
#   100d / 120d / 180d / 365d / 540d / 18m -> HTTP 429 "query too large"
# ถ้าขอยาวกว่านี้จะไม่ได้ข้อมูลเลย ไม่ใช่ได้ข้อมูลน้อยลง
MAX_TIMESPAN_DAYS = 90

# GDELT จำกัดอัตราการเรียกต่อ IP ค่อนข้างแรง (เจอ 429 บ่อยจากเซิร์ฟเวอร์ cloud)
# จึงบังคับเว้นจังหวะระหว่างการเรียกทุกครั้ง + พักยาวเมื่อโดน 429 ติด ๆ กัน
_MIN_GAP_SEC = 1.2
_COOLDOWN_SEC = 30
# พักเฉพาะเมื่อ "ล้มติดกันหลายครั้ง" — ล้มครั้งเดียวห้ามทำให้ทั้งระบบหยุด
# (บั๊กที่เจอจริง: ล้ม 1 ครั้ง -> พัก 45 วิ -> ธีมที่เหลืออีก 8 ธีมถูกข้ามหมด
#  ลูกโลกจึงว่างเปล่าทั้งที่ GDELT แค่งอแงชั่วคราว)
_FAILS_BEFORE_COOLDOWN = 3
_rate_lock = threading.Lock()
_last_call = [0.0]
_cooldown_until = [0.0]
_fail_streak = [0]


def _clamp_timespan(timespan: str) -> str:
    """
    ตัด timespan ให้ไม่เกินเพดานที่ GDELT รับได้
    รองรับรูปแบบ '540d', '18m', '2y', '24h' (ชั่วโมงปล่อยผ่าน)
    """
    s = (timespan or "").strip().lower()
    if not s:
        return f"{MAX_TIMESPAN_DAYS}d"
    unit, num = s[-1], s[:-1]
    if unit == "h":
        return s
    try:
        n = float(num)
    except ValueError:
        return f"{MAX_TIMESPAN_DAYS}d"
    days = {"d": n, "w": n * 7, "m": n * 30, "y": n * 365}.get(unit)
    if days is None:
        return f"{MAX_TIMESPAN_DAYS}d"
    return f"{int(min(days, MAX_TIMESPAN_DAYS))}d"


def in_cooldown() -> bool:
    """ตอนนี้อยู่ในช่วงพักหลังโดน GDELT ปฏิเสธซ้ำ ๆ หรือไม่"""
    return time.time() < _cooldown_until[0]


def cooldown_left() -> int:
    return max(0, int(_cooldown_until[0] - time.time()))


def _throttle():
    """เว้นจังหวะก่อนยิง GDELT · ถ้าเพิ่งโดน 429 จะบอกให้ข้ามไปเลย"""
    with _rate_lock:
        now = time.time()
        if now < _cooldown_until[0]:
            return False
        wait = _MIN_GAP_SEC - (now - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        return True


# ---------------------------------------------------------------------------
# low-level fetch
# ---------------------------------------------------------------------------
def _fetch_json(path: str, params: dict, retries: int = 1, timeout: int = None):
    """
    เรียก GDELT แล้วคืน dict; คืน None ถ้าล้มเหลว (GDELT บางทีตอบ text ไม่ใช่ json)

    จัดการ 2 เรื่องที่เจอจริงบนเซิร์ฟเวอร์:
      - HTTP 429 (โดนจำกัดอัตรา หรือ query หนักเกิน) -> ถอยแล้วลองใหม่แบบเว้นนานขึ้น
      - timespan ยาวเกินเพดาน -> ตัดให้เหลือ MAX_TIMESPAN_DAYS ก่อนยิง
    """
    if not _REQ_OK:
        return None
    params = dict(params)
    if params.get("timespan"):
        params["timespan"] = _clamp_timespan(str(params["timespan"]))

    url = f"{Config.GDELT_BASE}/{path}"
    for attempt in range(retries + 1):
        if not _throttle():
            return None                     # อยู่ในช่วงพักหลังโดน 429 — อย่าซ้ำเติม
        try:
            r = requests.get(url, params=params,
                             timeout=timeout or Config.GDELT_TIMEOUT,
                             headers={"User-Agent": _UA})
            if r.status_code == 200 and r.text.strip():
                with _rate_lock:
                    _fail_streak[0] = 0     # สำเร็จแล้ว รีเซ็ตตัวนับ
                return r.json()
            if r.status_code == 429 and attempt == retries:
                _note_failure()
        except Exception:
            if attempt == retries:
                _note_failure()
        if attempt < retries:
            time.sleep(2.0 * (attempt + 1))
    return None


def _note_failure():
    """นับความล้มเหลวต่อเนื่อง — พักก็เมื่อล้มติดกันจนแน่ใจว่าโดนจำกัดจริง"""
    with _rate_lock:
        _fail_streak[0] += 1
        if _fail_streak[0] >= _FAILS_BEFORE_COOLDOWN:
            _cooldown_until[0] = time.time() + _COOLDOWN_SEC
            _fail_streak[0] = 0


def _day_of(stamp: str) -> str:
    """'20260725T063000Z' -> '2026-07-25'"""
    s = (stamp or "").strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]


# ---------------------------------------------------------------------------
# 1) จุดข่าวบนแผนที่ (สำหรับลูกโลก 3D)
# ---------------------------------------------------------------------------
POOL_KEY = "gdelt:pool"


def _pool_load() -> dict:
    d = cache_get(POOL_KEY) or {}
    return {"articles": d.get("articles") or [], "cursor": int(d.get("cursor") or 0),
            "updated": d.get("updated"), "last_ok": d.get("last_ok")}


def _pool_save(pool: dict):
    cache_set(POOL_KEY, pool, 60 * 60 * 24 * 7)


def _pool_prune(articles):
    """ตัดข่าวเก่าเกินอายุ + ตัดข่าวซ้ำ (ยึด url) + จำกัดจำนวน"""
    cutoff = time.time() - Config.WORLD_POOL_HOURS * 3600
    seen, out = set(), []
    for a in sorted(articles, key=lambda x: x.get("_t", 0), reverse=True):
        url = a.get("url")
        if not url or url in seen or (a.get("_t", 0) < cutoff):
            continue
        seen.add(url)
        out.append(a)
        if len(out) >= Config.WORLD_POOL_MAX:
            break
    return out


def _fetch_one_word(word: str):
    """
    ยิง GDELT 1 ครั้งด้วย "คำเดียว" + maxrecords=50 — รูปแบบเดียวที่วัดแล้วผ่านจริง
    (คำค้นที่มี OR หลายคำโดนปฏิเสธ 100% · maxrecords อื่นก็โดนปฏิเสธ)
    """
    data = _fetch_json("doc/doc", {
        "query": word,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": Config.WORLD_MAXRECORDS,
        "timespan": "24h",
        "sort": "DateDesc",
    }, retries=0)
    return (data or {}).get("articles") or []


def refill_pool(rounds: int = 1) -> dict:
    """
    เติมคลังข่าวทีละคำ วนไปเรื่อย ๆ (คำที่ล้มจะได้คิวใหม่รอบหน้าเอง)

    ⚠️ ฟังก์ชันนี้ "ช้า" โดยธรรมชาติ — วัดจริงแล้ว GDELT ใช้เวลาตอบ 10-18 วินาที
    ต่อคำขอ และปฏิเสธราวครึ่งหนึ่ง จึงห้ามเรียกจากเส้นทางที่ผู้ใช้นั่งรออยู่
    ให้เรียกจากเธรดเบื้องหลัง (ดู ensure_filling) เท่านั้น
    """
    pool = _pool_load()
    words = list(Config.WORLD_FETCH_WORDS)
    if not words:
        return {"added": 0, "tried": 0, "ok": 0}

    added = ok = tried = 0
    for i in range(max(1, rounds)):
        word = words[(pool["cursor"] + i) % len(words)]
        tried += 1
        arts = _fetch_one_word(word)
        if arts:
            ok += 1
            now = time.time()
            for a in arts:
                a["_t"] = now
                a["_w"] = word
            pool["articles"] = _pool_prune(pool["articles"] + arts)
            added += len(arts)
            pool["last_ok"] = dt.datetime.now().isoformat(timespec="minutes")

    pool["cursor"] = (pool["cursor"] + max(1, rounds)) % len(words)
    pool["updated"] = dt.datetime.now().isoformat(timespec="minutes")
    _pool_save(pool)
    return {"added": added, "tried": tried, "ok": ok,
            "pool_size": len(pool["articles"])}


# ---------------------------------------------------------------------------
# ตัวเก็บข่าวเบื้องหลัง — หัวใจที่ทำให้ลูกโลกไม่ค้างและไม่ว่าง
# ---------------------------------------------------------------------------
# เหตุผลที่ต้องมี (วัดจาก GDELT จริง ไม่ได้เดา):
#   - คำขอหนึ่งครั้งใช้เวลา 10-18 วินาที  -> ถ้าเปิดหน้าแล้วรอ = หน้าค้าง
#   - ถูกปฏิเสธราวครึ่งหนึ่งของคำขอ        -> ถ้ายิงครั้งเดียวต่อการเปิดหน้า
#                                            โอกาสได้ข่าวมีแค่ ~50% ลูกโลกจึงว่างบ่อย
# วิธีแก้: เปิดหน้า = อ่านจากคลังทันที (ไม่รอเน็ตเลย) แล้วสั่งให้เธรดเบื้องหลัง
# ไล่เก็บข่าวต่อจนคลังพอ ระหว่างนั้นหน้าเว็บ poll ดูคลังโตขึ้นแล้ววาดเพิ่มเอง
FILL_TARGET = 120          # ข่าวในคลังที่ถือว่าพอวาดลูกโลกได้ดี
FILL_MAX_SECONDS = 300     # ตัวเก็บทำงานต่อรอบไม่เกินเท่านี้
FILL_MAX_ROUNDS = 24       # และยิงไม่เกินเท่านี้ต่อรอบ (กันวนไม่รู้จบตอน GDELT ล่ม)
FILL_GAP_SEC = 5           # เว้นจังหวะระหว่างคำ (นอกเหนือจากเวลาที่ GDELT ใช้ตอบ)

_filler_lock = threading.Lock()
_filler = {"running": False, "started": 0.0, "tried": 0, "ok": 0,
           "added": 0, "finished": None}


def filler_state() -> dict:
    with _filler_lock:
        st = dict(_filler)
    st["cooldown"] = cooldown_left()
    return st


def fill_rounds(target: int = FILL_TARGET, max_rounds: int = FILL_MAX_ROUNDS,
                max_seconds: int = FILL_MAX_SECONDS, gap: float = FILL_GAP_SEC) -> dict:
    """
    ไล่เก็บข่าวจนคลังถึงเป้า — ล้มก็ลองคำถัดไป ไม่ยอมแพ้ตั้งแต่ครั้งแรก

    เหตุผล: วัดจริงแล้ว GDELT ปฏิเสธราวครึ่งหนึ่งของคำขอที่ถูกรูปแบบทุกอย่าง
    ยิงครั้งเดียวแล้วเลิก = ลูกโลกว่าง 50% ของเวลา · ยิงต่อ 4 ครั้ง = พลาดหมด ~6%
    """
    deadline = time.time() + max_seconds
    rounds = 0
    while rounds < max_rounds and time.time() < deadline:
        if len(_pool_load()["articles"]) >= target:
            break
        if in_cooldown():
            time.sleep(min(cooldown_left() + 1, 10))
            continue
        rounds += 1
        res = refill_pool(rounds=1)
        with _filler_lock:
            _filler["tried"] += res.get("tried", 0)
            _filler["ok"] += res.get("ok", 0)
            _filler["added"] += res.get("added", 0)
        if gap:
            time.sleep(gap)
    return filler_state()


def _fill_loop():
    try:
        fill_rounds()
    except Exception as e:                       # เธรดเบื้องหลังห้ามล้มเงียบ ๆ
        with _filler_lock:
            _filler["error"] = str(e)[:200]
    finally:
        with _filler_lock:
            _filler["running"] = False
            _filler["finished"] = dt.datetime.now().isoformat(timespec="seconds")


def ensure_filling() -> bool:
    """
    สั่งให้ตัวเก็บข่าวเบื้องหลังทำงานถ้าคลังยังไม่พอ — คืนค่าว่ากำลังเก็บอยู่ไหม
    เรียกจากหน้าเว็บได้ เพราะ "ไม่บล็อก" (แค่ปลุกเธรดแล้วคืนค่าทันที)
    """
    if not _REQ_OK:
        return False
    with _filler_lock:
        if _filler["running"]:
            return True
        if len(_pool_load()["articles"]) >= FILL_TARGET:
            return False
        _filler.update({"running": True, "started": time.time(),
                        "tried": 0, "ok": 0, "added": 0, "finished": None})
        _filler.pop("error", None)
    threading.Thread(target=_fill_loop, daemon=True, name="gdelt-filler").start()
    return True


def world_snapshot(timespan: str = "24h", refill: bool = False) -> dict:
    """
    จุดข่าวบนลูกโลก — สร้างจาก "คลังข่าวสะสม" ไม่ใช่การยิงสด 9 ครั้ง

    ทำไมต้องเป็นแบบนี้ (วัดจาก GDELT จริง ไม่ได้เดา)
    ------------------------------------------------
    ArtList ของ GDELT ยอมรับเฉพาะ "คำเดียว + maxrecords=50" (ผ่าน 4/5 ครั้ง)
    ส่วนคำค้นที่มี OR หลายคำโดนปฏิเสธ 0/6 ครั้ง และ maxrecords ค่าอื่นก็โดนปฏิเสธ
    → จะยิงรวมทุกธีมในครั้งเดียวไม่ได้ และยิงธีมละครั้ง (9 ครั้ง) ก็ไม่รอด

    วิธีที่ใช้: เปิดหน้าแต่ละครั้งยิงแค่ "1 คำ" (วนคำไปเรื่อย ๆ) แล้วสะสมข่าวไว้
    ในคลังร่วมอายุ 36 ชม. → ลูกโลกวาดจากคลัง ไม่ต้องรอผลสด
    ยิ่งเปิดบ่อย/ตัวเก็บเบื้องหลังทำงาน คลังยิ่งเต็ม ครอบคลุมธีมมากขึ้นเรื่อย ๆ
    ถ้าคำที่ยิงรอบนี้ล้ม ลูกโลกก็ยังวาดจากคลังเดิมได้ตามปกติ

    ⚠️ GDELT ปิด GEO 2.0 API แล้ว (api/v2/geo/geo -> 404 ทุกแบบ) จึงใช้ประเทศ
    ต้นทางข่าว (sourcecountry) วางจุดที่พิกัดกลางของประเทศ = หยาบระดับประเทศ
    """
    fetch = None
    if refill:
        fetch = refill_pool(rounds=1)

    pool = _pool_load()
    arts = pool["articles"]
    if not arts:
        st = filler_state()
        return {"ok": False, "points": [], "themes": _empty_themes(),
                "timespan": timespan, "articles_seen": 0, "pool_size": 0,
                "fetch": fetch, "filling": st["running"], "filler": st,
                "error": ("กำลังเก็บข่าวจาก GDELT อยู่เบื้องหลัง — ลูกโลกจะขึ้นเองภายในไม่กี่สิบวินาที"
                          if st["running"] else
                          "ยังไม่มีข่าวในคลัง — GDELT ปฏิเสธคำขอรอบล่าสุด ระบบจะลองเก็บใหม่ให้")}

    by_theme = _classify_articles(arts)
    points, themes = [], []
    for key, (label, _q, color) in Config.WORLD_THEMES.items():
        pts = _points_from_articles(by_theme.get(key, []), color, key)
        for p in pts:
            p["theme"] = key
        points.extend(pts)
        themes.append({"key": key, "label": label, "color": color,
                       "count": len(pts), "articles": len(by_theme.get(key, [])),
                       "ok": bool(pts)})

    return {
        "ok": bool(points),
        "points": points,
        "themes": themes,
        "timespan": timespan,
        "articles_seen": len(arts),
        "pool_size": len(arts),
        "unclassified": len(by_theme.get("_none", [])),
        "source": "artlist-pool",
        "fetch": fetch,
        "filling": filler_state()["running"],
        "fetched_at": pool.get("last_ok") or pool.get("updated"),
    }


def _empty_themes():
    return [{"key": k, "label": v[0], "color": v[2], "count": 0, "articles": 0,
             "ok": False} for k, v in Config.WORLD_THEMES.items()]


def _classify_articles(arts) -> dict:
    """
    จัดข่าวเข้าธีมจากคำในพาดหัว · 1 ข่าวเข้าได้หลายธีม (เช่นข่าวชิปโดนภาษี)
    ข่าวที่ไม่เข้าธีมไหนเลยเก็บไว้ที่คีย์ '_none' เพื่อรายงานอย่างซื่อสัตย์
    """
    buckets = {}
    for a in arts:
        text = f" {(a.get('title') or '').lower()} "
        hit = False
        for key, words in Config.WORLD_THEME_KEYWORDS.items():
            if any(w in text for w in words):
                buckets.setdefault(key, []).append(a)
                hit = True
        if not hit:
            buckets.setdefault("_none", []).append(a)
    return buckets


def world_points(query: str = "", timespan: str = "24h", theme: str = "") -> dict:
    """
    จุดข่าวของธีมเดียว — อ่านจากคลัง **ไม่ยิงเน็ตเพิ่ม**

    สำคัญ: ผู้ใช้กดสลับธีมบนหน้าเว็บได้รัว ๆ ถ้าฟังก์ชันนี้ยิง GDELT ทุกครั้ง
    จะกลายเป็น 9 คำขอต่อการดูหนึ่งครั้ง = ปัญหาเดิมที่ทำให้ลูกโลกพัง
    ยิงได้กรณีเดียวคือคลังยังว่างสนิท (เช่นเปิดแอปครั้งแรก)
    """
    ensure_filling()
    snap = world_snapshot(timespan, refill=False)
    label, q, color = Config.WORLD_THEMES.get(
        theme, ("ข่าวทั่วโลก", query or "", "#4dd4ff"))
    pts = [p for p in snap.get("points", []) if not theme or p.get("theme") == theme]
    return {
        "theme": theme, "label": label, "color": color, "query": q,
        "timespan": snap.get("timespan", timespan),
        "points": pts, "ok": bool(pts), "total": len(pts),
        "filling": snap.get("filling", False),
        "pool_size": snap.get("pool_size", 0),
        "articles_seen": snap.get("articles_seen"),
        "stale": snap.get("stale", False),
        "note": snap.get("note"),
        "error": snap.get("error") if not pts else None,
        "source": snap.get("source"),
        "fetched_at": snap.get("fetched_at"),
    }


def _points_from_articles(arts, color: str, theme: str = "") -> list:
    """รวมข่าวเป็นจุดรายประเทศ + เก็บลิงก์ข่าวตัวอย่างไว้ให้คลิกดู"""
    # เลื่อนจุดของแต่ละธีมเล็กน้อย เพื่อไม่ให้แท่งของหลายธีมทับกันสนิท
    seed = sum(ord(c) for c in (theme or "x"))
    off_lat = ((seed % 7) - 3) * 0.55
    off_lon = ((seed % 11) - 5) * 0.55

    buckets = {}
    for a in arts:
        country = (a.get("sourcecountry") or "").strip()
        pos = country_geo.coords_for(country)
        if not pos:
            continue
        b = buckets.setdefault(country, {"count": 0, "articles": []})
        b["count"] += 1
        if len(b["articles"]) < 5 and a.get("url"):
            b["articles"].append({"title": (a.get("title") or "")[:160],
                                  "url": a.get("url")})

    points = []
    for country, b in buckets.items():
        lat, lon = country_geo.coords_for(country)
        points.append({
            "lat": round(lat + off_lat, 4),
            "lon": round(lon + off_lon, 4),
            "name": country,
            "count": b["count"],
            "color": color,
            "articles": b["articles"],
        })
    points.sort(key=lambda p: p["count"], reverse=True)
    return points[:Config.GDELT_MAX_POINTS]


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
    """
    จุดข่าวทุกธีมสำหรับหน้าลูกโลก — **ตอบทันทีจากคลัง ไม่รอ GDELT เลย**

    ถ้าคลังยังไม่พอ จะปลุกตัวเก็บเบื้องหลังให้ไปไล่เก็บ แล้วบอกหน้าเว็บว่า
    filling=True เพื่อให้หน้าเว็บถามซ้ำเป็นระยะและวาดเพิ่มเมื่อคลังโตขึ้น
    (เหตุผลที่ห้ามรอ: GDELT ใช้เวลาตอบ 10-18 วิ และปฏิเสธราวครึ่งหนึ่ง)
    """
    filling = ensure_filling()
    snap = world_snapshot(timespan, refill=False)
    themes = snap.get("themes") or _empty_themes()
    empty = [t for t in themes if not t.get("count")]
    st = filler_state()

    notes = []
    if filling:
        notes.append(f"กำลังเก็บข่าวเพิ่มเบื้องหลัง (ได้แล้ว {snap.get('pool_size', 0)} ข่าว) "
                     "— ลูกโลกจะขึ้นครบเองไม่ต้องกดอะไร")
    if snap.get("ok") and empty and not filling:
        notes.append(f"{len(empty)} ธีมยังไม่มีข่าวในคลัง — ระบบทยอยเก็บเพิ่มให้เอง")

    return {
        "themes": themes,
        "points": snap.get("points", []),
        "timespan": timespan,
        "ok": snap.get("ok", False),
        "filling": filling,
        "filler": st,
        "skipped_themes": len(empty) if snap.get("ok") else len(themes),
        "pool_size": snap.get("pool_size", 0),
        "articles_seen": snap.get("articles_seen"),
        "unclassified": snap.get("unclassified"),
        "error": snap.get("error"),
        "note": " · ".join(notes) if notes else None,
        "fetched_at": snap.get("fetched_at") or dt.datetime.now().isoformat(timespec="seconds"),
    }


def warm_cache(timespan: str = "24h") -> dict:
    """เติมคลังข่าวล่วงหน้าจากตัวเก็บข้อมูลรายชั่วโมง (บล็อกได้ เพราะไม่มีใครรออยู่)"""
    res = fill_rounds(max_rounds=6, max_seconds=180, gap=2)
    snap = world_snapshot(timespan, refill=False)
    return {"fetched": res, "points": len(snap.get("points", [])),
            "pool_size": snap.get("pool_size", 0)}


# ---------------------------------------------------------------------------
# 2) Timeline ของ Tone — หัวใจของเครื่องเรียนรู้ (ย้อนหลังได้ถึง 1 ปี)
# ---------------------------------------------------------------------------
def tone_timeline(query: str, timespan: str = "90d") -> dict:
    """คืน {day: average_tone} รายวัน (ยาวเกิน 90 วันจะแบ่งยิงเป็นช่วง ๆ ให้เอง)"""
    return _timeline(query, "TimelineTone", timespan, "tone")


def volume_timeline(query: str, timespan: str = "90d") -> dict:
    """คืน {day: volume%} — ปริมาณข่าว (สัดส่วนของข่าวทั้งโลกที่พูดเรื่องนี้)"""
    return _timeline(query, "TimelineVol", timespan, "vol")


def _timeline(query: str, mode: str, timespan: str, tag: str) -> dict:
    days = _days_of(timespan)
    if days is not None and days > MAX_TIMESPAN_DAYS:
        return _chunked_timeline(query, mode, days, tag)

    span = _clamp_timespan(timespan)
    cache_key = f"gdelt:{tag}:{query}:{span}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    out = {"query": query, "timespan": span, "series": {}, "ok": False}
    series = _parse_timeline(_fetch_json("doc/doc", {
        "query": query, "mode": mode, "format": "json", "timespan": span}))
    if series:
        out["series"] = series
        out["ok"] = True
        out["fetched_at"] = dt.datetime.now().isoformat(timespec="minutes")
        cache_set(cache_key, out, Config.GDELT_TIMELINE_CACHE_TTL)
        cache_set(cache_key + ":last", out, LAST_GOOD_TTL)
        return out

    stale = cache_get(cache_key + ":last")
    if stale and stale.get("series"):
        stale = dict(stale)
        stale["stale"] = True
        return stale
    out["error"] = "ดึง timeline จาก GDELT ไม่ได้"
    return out


# ---------------------------------------------------------------------------
# แบ่งยิงทีละช่วง แล้วสะสมไว้ — ทะลุเพดาน 90 วันของ GDELT
# ---------------------------------------------------------------------------
CHUNK_DAYS = 85            # เผื่อขอบ ไม่ให้ชนเพดาน 90 วันพอดี
CHUNK_CACHE_TTL = 60 * 60 * 24 * 60   # ช่วงที่ผ่านไปแล้วไม่เปลี่ยนอีก เก็บยาว 60 วัน
LAST_GOOD_TTL = 60 * 60 * 24 * 7      # สำเนา "ครั้งที่ได้ผลล่าสุด" เก็บไว้ 7 วัน
MAX_NEW_CHUNKS_PER_CALL = 2           # ต่อ 1 คำขอ ดึงของใหม่ไม่เกินเท่านี้ (กันช้า/โดนบล็อก)


def _days_of(timespan: str):
    """แปลง '540d' / '18m' / '2y' เป็นจำนวนวัน · คืน None ถ้าเป็นชั่วโมงหรืออ่านไม่ออก"""
    s = (timespan or "").strip().lower()
    if not s or s[-1] == "h":
        return None
    try:
        n = float(s[:-1])
    except ValueError:
        return None
    per_unit = {"d": n, "w": n * 7, "m": n * 30, "y": n * 365}.get(s[-1])
    return int(per_unit) if per_unit is not None else None


def _stamp(d: dt.date) -> str:
    return d.strftime("%Y%m%d") + "000000"


def _chunk_ranges(days: int):
    """แบ่งช่วงเวลาย้อนหลังเป็นก้อนละ CHUNK_DAYS วัน เริ่มจากก้อนล่าสุดก่อน"""
    today = dt.date.today()
    out = []
    covered = 0
    while covered < days:
        end = today - dt.timedelta(days=covered)
        span = min(CHUNK_DAYS, days - covered)
        start = end - dt.timedelta(days=span)
        out.append((start, end))
        covered += span
    return out


def _chunked_timeline(query: str, mode: str, days: int, tag: str) -> dict:
    """
    ยิงทีละช่วง 85 วัน ย้อนหลังไปเรื่อย ๆ แล้วรวมกัน

    ช่วงที่ดึงมาแล้วจะถูกเก็บไว้ (ข้อมูลอดีตไม่เปลี่ยนอีก) คำขอถัดไปจึงหยิบของเก่า
    มาใช้ทันที และไปดึงเฉพาะช่วงที่ยังขาด ครั้งละไม่กี่ช่วง — ทยอยสะสมจนครบเอง
    โดยผู้ใช้ไม่ต้องรอนาน (ตัวเก็บข้อมูลเบื้องหลังก็ช่วยดึงให้ทุกชั่วโมงด้วย)
    """
    merged = {}
    have = missing = fetched = 0

    for start, end in _chunk_ranges(days):
        ck = f"gdelt:{tag}:chunk:{query}:{_stamp(start)}:{_stamp(end)}"
        cached = cache_get(ck)
        if cached is not None:
            merged.update(cached.get("series") or {})
            have += 1
            continue

        if fetched >= MAX_NEW_CHUNKS_PER_CALL:
            missing += 1
            continue

        series = _parse_timeline(_fetch_json("doc/doc", {
            "query": query, "mode": mode, "format": "json",
            "startdatetime": _stamp(start), "enddatetime": _stamp(end)}))
        fetched += 1
        if series:
            # ช่วงล่าสุดยังไม่จบวัน จึงเก็บสั้นกว่า ส่วนช่วงอดีตเก็บยาว
            is_recent = (dt.date.today() - end).days < 2
            cache_set(ck, {"series": series},
                      Config.GDELT_TIMELINE_CACHE_TTL if is_recent else CHUNK_CACHE_TTL)
            merged.update(series)
            have += 1
        else:
            missing += 1

    return {
        "query": query, "timespan": f"{days}d", "series": merged,
        "ok": bool(merged),
        "chunks": {"total": have + missing, "ready": have, "pending": missing},
        "note": (f"ยังดึงไม่ครบ ขาดอีก {missing} ช่วง — ระบบจะทยอยเก็บให้เอง "
                 "เปิดหน้านี้อีกครั้งภายหลังจะได้ข้อมูลยาวขึ้น") if missing else None,
        "error": None if merged else "ดึง timeline จาก GDELT ไม่ได้",
    }


_backfill_cursor = [0]


def backfill(days: int = 540, themes_per_run: int = 2) -> dict:
    """
    ทยอยดึงข่าวย้อนหลังมาเก็บไว้ — เรียกจากเธรดเบื้องหลังทุกชั่วโมง

    วัดจริงแล้ว GDELT ปฏิเสธ (429) บ่อยมากแม้คำขอจะถูกต้อง จึงทำทีละ 2 ธีมต่อรอบ
    แบบวนไปเรื่อย ๆ ธีมที่ยังไม่ครบจะได้คิวในรอบถัดไปเอง
    ช่วงที่ดึงสำเร็จแล้วเก็บไว้ 60 วัน (ข้อมูลอดีตไม่เปลี่ยน) จึงไม่ต้องดึงซ้ำ
    ยิ่งแอปรันนาน คลังข่าวยิ่งยาว เครื่องเรียนรู้ยิ่งมีตัวอย่างเยอะ
    """
    keys = list(Config.WORLD_THEMES)
    if not keys:
        return {"themes": 0, "ready": 0, "pending": 0}

    done = {"themes": 0, "ready": 0, "pending": 0, "days": days}
    for i in range(min(themes_per_run, len(keys))):
        key = keys[(_backfill_cursor[0] + i) % len(keys)]
        q = theme_query(key)
        if not q:
            continue
        ch = (_chunked_timeline(q, "TimelineTone", days, "tone").get("chunks") or {})
        done["themes"] += 1
        done["ready"] += ch.get("ready", 0)
        done["pending"] += ch.get("pending", 0)

    _backfill_cursor[0] = (_backfill_cursor[0] + themes_per_run) % len(keys)
    return done


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

    เรียกจากหน้าวิเคราะห์ที่ผู้ใช้นั่งรออยู่ จึงตั้งเวลารอสั้นและไม่ลองซ้ำ
    ถ้า GDELT ช้า/ไม่ตอบ ให้ถอยไปใช้ sentiment จากพาดหัวข่าวแทนทันที
    """
    base = (name or "").strip() or ticker.replace(".BK", "")
    q = f'"{base}"' if " " in base else base

    span = _clamp_timespan(timespan)
    cache_key = f"gdelt:tone:{q}:{span}"
    cached = cache_get(cache_key)
    if cached:
        ser = cached.get("series") or {}
    else:
        ser = _parse_timeline(_fetch_json(
            "doc/doc",
            {"query": q, "mode": "TimelineTone", "format": "json", "timespan": span},
            retries=0, timeout=Config.GDELT_TIMEOUT_FAST))
        if ser:
            cache_set(cache_key, {"series": ser}, Config.GDELT_TIMELINE_CACHE_TTL)
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
