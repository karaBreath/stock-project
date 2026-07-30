"""
GDELT Events 2.0 — ข่าวสำคัญ "ทั่วโลก" พร้อมพิกัดที่เกิดเหตุจริง

ทำไมต้องมีไฟล์นี้ (วัดจากเซิร์ฟเวอร์จริง ไม่ได้เดา)
------------------------------------------------------
วิธีเดิมใช้ DOC 2.0 ArtList ยิง "คำละครั้ง" ซึ่งมีเพดานในตัวเอง:
  - ครอบคลุมได้แค่คำที่เราคิดออก (ข่าวสำคัญที่ไม่ตรงคำจะไม่มีเลย)
  - GDELT จำกัด 1 คำขอ/5 วินาทีต่อ IP และปฏิเสธราว 50-70% บน IP ที่ใช้ร่วมกัน
  - ไม่มีพิกัดเหตุการณ์ (GEO 2.0 ปิดไปแล้ว) ต้องเดาจากพาดหัว/ประเทศสำนักข่าว

GDELT ปล่อยไฟล์ Events ใหม่ "ทุก 15 นาที" ที่ data.gdeltproject.org ซึ่งวัดแล้วได้:
  lastupdate.txt      HTTP 200 · 0.2s
  export.CSV.zip      54 KB · 0.0s · 832 เหตุการณ์ · 61 คอลัมน์
  ยิงซ้ำ 3 ครั้งติด    HTTP 200 ทุกครั้ง (ไม่ติดโควตาเหมือน API)
  พิกัด               ~65% ของแถว · ครอบคลุม 38 ประเทศ ใน 15 นาทีเดียว

ข้อจำกัดที่ต้องรู้: Events เก็บ "เหตุการณ์ระหว่างผู้เล่น" ตามรหัส CAMEO
(การเมือง/ความขัดแย้ง/การทูต) จึงเก่งภูมิรัฐศาสตร์มาก แต่ไม่ครอบคลุม
ข่าวตลาดหุ้น/ผลประกอบการ/ภัยธรรมชาติ — ส่วนนั้นยังใช้คลังคำของ services/gdelt.py
"""
import csv
import io
import re
import time
import zipfile
import datetime as dt

from config import Config
from database import cache_get, cache_set

try:
    import requests
    _REQ_OK = True
except Exception:  # pragma: no cover
    requests = None
    _REQ_OK = False


BASE = "http://data.gdeltproject.org/gdeltv2"
LASTUPDATE = f"{BASE}/lastupdate.txt"
_UA = "NEBULA-Stock-App/1.0 (educational stock research)"

# ตำแหน่งคอลัมน์ของ GDELT 2.0 Events (61 คอลัมน์ นับจาก 0)
# ⚠️ ต้องเป็น ActionGeo_* (ที่เกิดเหตุ) ไม่ใช่ Actor1Geo_* ที่อยู่คอลัมน์ 36-42
#    probe รอบแรกใช้ 36-41 แล้วได้ลองจิจูดหลุดไปคอลัมน์อื่น จึงรู้ว่าเลื่อน
C_ID, C_DATE = 0, 1
C_ROOT, C_QUAD = 28, 29
C_GOLD, C_MENTIONS, C_SOURCES, C_ARTICLES, C_TONE = 30, 31, 32, 33, 34
C_GEO_TYPE, C_GEO_NAME, C_GEO_CC = 51, 52, 53
C_LAT, C_LON = 56, 57
C_URL = 60
N_COLS = 61

STORE_KEY = "gdelt:events:store"
STORE_TTL = 60 * 60 * 24 * 3
EVENTS_HOURS = 12          # เก็บเหตุการณ์ย้อนหลังกี่ชั่วโมง
EVENTS_MAX = 6000          # เก็บสูงสุดกี่เหตุการณ์ (กันคลังบวม)
MAX_SLICES_PER_CALL = 4    # ต่อการเก็บหนึ่งครั้ง ดึงไฟล์ใหม่ไม่เกินกี่ไฟล์
TIMEOUT = 45


# ---------------------------------------------------------------------------
# CAMEO EventRootCode -> ธีมของเรา
# ---------------------------------------------------------------------------
# 01 แถลง · 02 เรียกร้อง · 03 แสดงเจตนาร่วมมือ · 04 หารือ · 05 ร่วมมือทางการทูต
# 06 ร่วมมือเป็นรูปธรรม · 07 ให้ความช่วยเหลือ · 08 ยอมตาม · 09 สอบสวน · 10 เรียกร้อง
# 11 ไม่เห็นด้วย · 12 ปฏิเสธ · 13 ข่มขู่ · 14 ประท้วง · 15 แสดงกำลัง
# 16 ลดความสัมพันธ์ · 17 บีบบังคับ · 18 ทำร้าย · 19 สู้รบ · 20 ความรุนแรงหมู่
# ⚠️ อย่าเหมารหัสที่ไม่ใช่การสู้รบว่าเป็น "การค้า" — เจอจริงจากผลรัน:
#    จุดเกือบทั้งหมด (เตหะราน เคียฟ กาซา ลอนดอน) ถูกติดป้าย "การค้า/ภาษี"
#    ทั้งที่เป็นข่าวการเมือง/การทูต = ป้ายผิดและลูกโลกกลายเป็นสีเดียวทั้งใบ
#    เหตุการณ์การเมืองจึงมีธีมของตัวเอง ส่วนธีมการเงินให้ดูจากลิงก์ข่าวแทน
ROOT_THEME = {
    # 13-20 = ข่มขู่ / ประท้วง / แสดงกำลัง / บีบบังคับ / ทำร้าย / สู้รบ / ความรุนแรงหมู่
    "13": "conflict", "14": "conflict", "15": "conflict", "16": "conflict",
    "17": "conflict", "18": "conflict", "19": "conflict", "20": "conflict",
    # 01-12 = แถลง / เรียกร้อง / หารือ / ร่วมมือ / ให้ความช่วยเหลือ / ไม่เห็นด้วย / ปฏิเสธ
    "01": "geopolitics", "02": "geopolitics", "03": "geopolitics",
    "04": "geopolitics", "05": "geopolitics", "06": "geopolitics",
    "07": "geopolitics", "08": "geopolitics", "09": "geopolitics",
    "10": "geopolitics", "11": "geopolitics", "12": "geopolitics",
}

# คำในลิงก์ข่าวที่บอกธีมได้ชัดกว่ารหัส CAMEO (Events ไม่มีพาดหัวมาให้)
# ⚠️ ลำดับสำคัญ — ตัวแรกที่ตรงชนะ จึงต้องเรียง "เฉพาะเจาะจง -> กว้าง"
#    (เทสจับได้: 'thailand-set-index' เคยกลายเป็นธีมตลาดโลก เพราะ 'index' ตรงก่อน)
URL_THEME = (
    ("thailand", ("thailand", "thai-", "bangkok")),
    ("disaster", ("earthquake", "flood", "hurricane", "typhoon", "wildfire",
                  "drought", "outbreak", "cyclone", "landslide", "volcano")),
    ("energy", ("oil", "crude", "opec", "gas-", "gasoline", "petrol",
                "pipeline", "refinery", "energy")),
    ("inflation", ("inflation", "interest-rate", "rate-cut", "rate-hike",
                   "central-bank", "federal-reserve", "cpi-")),
    ("tech", ("semiconductor", "chip", "nvidia", "artificial-intelligence",
              "data-center", "datacenter")),
    ("earnings", ("earnings", "quarterly-results", "profit", "revenue",
                  "guidance")),
    ("trade", ("tariff", "sanction", "trade-war", "export-ban", "customs")),
    ("market", ("stock", "shares", "nasdaq", "wall-street", "market",
                "bourse", "index")),
)


def _theme_of(root: str, url: str) -> str:
    """ธีมจากลิงก์ข่าวก่อน (ชัดกว่า) แล้วค่อยถอยไปใช้รหัสเหตุการณ์ CAMEO"""
    u = (url or "").lower()
    for theme, words in URL_THEME:
        if any(w in u for w in words):
            return theme
    return ROOT_THEME.get((root or "").zfill(2), "market")


# ---------------------------------------------------------------------------
# โหลดไฟล์
# ---------------------------------------------------------------------------
def _session():
    s = requests.Session()
    s.headers["User-Agent"] = _UA
    return s


def latest_export_urls(sess=None) -> list:
    """ลิงก์ไฟล์ export ล่าสุดจาก lastupdate.txt (คืนลิสต์ เผื่ออนาคตมีหลายไฟล์)"""
    if not _REQ_OK:
        return []
    s = sess or _session()
    try:
        r = s.get(LASTUPDATE, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
    except Exception:
        return []
    out = []
    for line in r.text.strip().splitlines():
        parts = line.split()
        if parts and ".export.CSV" in parts[-1]:
            out.append(parts[-1])
    return out


def _slice_id(url: str) -> str:
    m = re.search(r"/(\d{14})\.export", url or "")
    return m.group(1) if m else (url or "")[-30:]


def _prev_slices(url: str, n: int) -> list:
    """
    ไล่ย้อนไฟล์ก่อนหน้าทีละ 15 นาที — ใช้ตอนคลังยังว่าง เพื่อให้มีข่าวพอทันที
    (ไฟล์เก่ายังอยู่บนเซิร์ฟเวอร์ ไม่ต้องรอ 15 นาทีต่อไฟล์)
    """
    sid = _slice_id(url)
    try:
        t = dt.datetime.strptime(sid, "%Y%m%d%H%M%S")
    except ValueError:
        return []
    out = []
    for i in range(1, n + 1):
        p = t - dt.timedelta(minutes=15 * i)
        out.append(f"{BASE}/{p.strftime('%Y%m%d%H%M%S')}.export.CSV.zip")
    return out


def fetch_slice(url: str, sess=None) -> list:
    """โหลด+แตกไฟล์ 1 ช่วงเวลา คืนรายการเหตุการณ์ที่ 'มีพิกัดและมีลิงก์'"""
    if not _REQ_OK:
        return []
    s = sess or _session()
    try:
        r = s.get(url, timeout=TIMEOUT)
        if r.status_code != 200 or not r.content:
            return []
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        raw = zf.read(zf.namelist()[0]).decode("utf-8", "replace")
    except Exception:
        return []

    now = time.time()
    out = []
    for row in csv.reader(io.StringIO(raw), delimiter="\t"):
        if len(row) < N_COLS:
            continue
        lat, lon = row[C_LAT], row[C_LON]
        url_ = row[C_URL]
        if not lat or not lon or not url_:
            continue
        try:
            lat_f, lon_f = float(lat), float(lon)
        except ValueError:
            continue
        try:
            mentions = int(row[C_MENTIONS] or 0)
        except ValueError:
            mentions = 0
        try:
            tone = float(row[C_TONE] or 0.0)
        except ValueError:
            tone = 0.0
        out.append({
            "id": row[C_ID],
            "lat": round(lat_f, 3),
            "lon": round(lon_f, 3),
            "place": row[C_GEO_NAME],
            "cc": row[C_GEO_CC],
            "root": row[C_ROOT],
            "mentions": mentions,
            "tone": round(tone, 2),
            "url": url_,
            "theme": _theme_of(row[C_ROOT], url_),
            "_t": now,
        })
    return out


# ---------------------------------------------------------------------------
# คลังเหตุการณ์สะสม
# ---------------------------------------------------------------------------
def _store_load() -> dict:
    d = cache_get(STORE_KEY) or {}
    return {"events": d.get("events") or [], "slices": d.get("slices") or [],
            "updated": d.get("updated")}


def _store_save(store: dict):
    cache_set(STORE_KEY, store, STORE_TTL)


def _prune(events: list) -> list:
    """ตัดเหตุการณ์เก่า + ตัดซ้ำ (ยึด id) + จำกัดจำนวน (เก็บที่ถูกรายงานเยอะไว้ก่อน)"""
    cutoff = time.time() - EVENTS_HOURS * 3600
    seen, fresh = set(), []
    for e in events:
        eid = e.get("id")
        if not eid or eid in seen or e.get("_t", 0) < cutoff:
            continue
        seen.add(eid)
        fresh.append(e)
    if len(fresh) > EVENTS_MAX:
        fresh.sort(key=lambda x: (-x.get("mentions", 0), -x.get("_t", 0)))
        fresh = fresh[:EVENTS_MAX]
    return fresh


def collect(max_slices: int = MAX_SLICES_PER_CALL) -> dict:
    """
    เก็บไฟล์ช่วงเวลาใหม่เข้าคลัง — เรียกจากเธรดเบื้องหลังเท่านั้น (มี network)

    ครั้งแรกที่คลังว่าง จะไล่ย้อนไฟล์ก่อนหน้าให้ด้วย เพื่อให้ลูกโลกมีข่าวทันที
    ไม่ต้องรอสะสม 15 นาทีต่อไฟล์
    """
    store = _store_load()
    sess = _session()
    latest = latest_export_urls(sess)
    if not latest:
        return {"ok": False, "added": 0, "slices": 0,
                "error": "อ่าน lastupdate.txt ของ GDELT ไม่ได้"}

    done = set(store["slices"])
    want = [u for u in latest if _slice_id(u) not in done]
    if not store["events"]:                    # คลังว่าง — ดึงย้อนหลังให้พอใช้เลย
        want += [u for u in _prev_slices(latest[0], max_slices * 2)
                 if _slice_id(u) not in done]

    added = ok_slices = 0
    for u in want[:max_slices]:
        rows = fetch_slice(u, sess)
        done.add(_slice_id(u))
        if rows:
            ok_slices += 1
            added += len(rows)
            store["events"] = _prune(store["events"] + rows)

    store["slices"] = sorted(done)[-200:]
    store["updated"] = dt.datetime.now().isoformat(timespec="minutes")
    _store_save(store)
    return {"ok": bool(added), "added": added, "slices": ok_slices,
            "total": len(store["events"]), "updated": store["updated"]}


# ---------------------------------------------------------------------------
# แปลงเป็นจุดบนลูกโลก
# ---------------------------------------------------------------------------
def _short_place(name: str) -> str:
    """'Sydney, New South Wales, Australia' -> 'Sydney, Australia'"""
    parts = [p.strip() for p in (name or "").split(",") if p.strip()]
    if len(parts) >= 3:
        return f"{parts[0]}, {parts[-1]}"
    return ", ".join(parts) or "—"


def points(theme: str = "", limit: int = None) -> dict:
    """
    จุดบนลูกโลกจากเหตุการณ์จริง — ไม่ยิงเน็ต อ่านจากคลังอย่างเดียว

    รวมเหตุการณ์ที่พิกัดใกล้กันเป็นจุดเดียว แล้วเรียงตาม "ถูกรายงานกี่ครั้ง"
    (NumMentions) = ตัววัดความสำคัญที่โลกให้กับข่าวนั้นจริง ๆ ไม่ใช่เราเดา
    """
    store = _store_load()
    events = store["events"]
    cutoff = time.time() - EVENTS_HOURS * 3600
    events = [e for e in events if e.get("_t", 0) >= cutoff]
    if theme:
        events = [e for e in events if e.get("theme") == theme]

    buckets = {}
    for e in events:
        key = (round(e["lat"], 1), round(e["lon"], 1))
        b = buckets.setdefault(key, {
            "lat": e["lat"], "lon": e["lon"], "names": {}, "themes": {},
            "count": 0, "mentions": 0, "tone_sum": 0.0, "articles": [],
        })
        b["count"] += 1
        b["mentions"] += e.get("mentions", 0)
        b["tone_sum"] += e.get("tone", 0.0)
        b["names"][e["place"]] = b["names"].get(e["place"], 0) + 1
        b["themes"][e["theme"]] = b["themes"].get(e["theme"], 0) + 1
        if len(b["articles"]) < 6:
            b["articles"].append({"url": e["url"],
                                  "title": _title_from_url(e["url"]),
                                  "mentions": e.get("mentions", 0)})

    colors = {k: v[2] for k, v in Config.WORLD_THEMES.items()}
    out = []
    for b in buckets.values():
        top_theme = max(b["themes"], key=b["themes"].get)
        top_name = max(b["names"], key=b["names"].get)
        out.append({
            "lat": b["lat"], "lon": b["lon"],
            "name": _short_place(top_name),
            "full_name": top_name,
            "count": b["count"],
            "mentions": b["mentions"],
            "tone": round(b["tone_sum"] / b["count"], 2),
            "theme": top_theme,
            "color": colors.get(top_theme, "#4dd4ff"),
            "articles": sorted(b["articles"], key=lambda a: -a["mentions"]),
            "exact": b["count"],          # Events ให้พิกัดที่เกิดเหตุมาตรง ๆ ทุกแถว
        })

    out.sort(key=lambda p: -p["mentions"])
    cap = limit or Config.GDELT_MAX_POINTS
    return {
        "points": out[:cap],
        "total_places": len(out),
        "events": len(events),
        "updated": store.get("updated"),
        "hours": EVENTS_HOURS,
    }


_SLUG_RE = re.compile(r"[-_]+")


def _title_from_url(url: str) -> str:
    """
    Events ไม่มีพาดหัวมาให้ — ถอดจาก slug ของลิงก์ให้อ่านออกพอสมควร
    (ถ้าถอดไม่ได้ คืนชื่อโดเมนแทน ไม่แต่งเรื่องขึ้นมาเอง)
    """
    try:
        path = (url or "").split("//", 1)[-1]
        domain, _, rest = path.partition("/")
        slug = rest.rstrip("/").rsplit("/", 1)[-1]
        slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.I)
        slug = re.sub(r"^\d{4,}[-_]?", "", slug)
        words = [w for w in _SLUG_RE.split(slug) if w and not w.isdigit()]
        if len(words) >= 3:
            text = " ".join(words)
            return (text[:1].upper() + text[1:])[:160]
        return domain
    except Exception:
        return url[:80] if url else "—"


def status() -> dict:
    store = _store_load()
    cutoff = time.time() - EVENTS_HOURS * 3600
    fresh = [e for e in store["events"] if e.get("_t", 0) >= cutoff]
    themes = {}
    for e in fresh:
        themes[e["theme"]] = themes.get(e["theme"], 0) + 1
    return {
        "events": len(fresh),
        "slices_seen": len(store["slices"]),
        "countries": len({e["cc"] for e in fresh if e.get("cc")}),
        "themes": themes,
        "updated": store.get("updated"),
        "source": "gdelt-events-2.0",
    }
