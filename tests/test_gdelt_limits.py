"""
ชุดทดสอบข้อจำกัดจริงของ GDELT ที่วัดได้จากเซิร์ฟเวอร์จริง

หลักฐาน (ยิงจากเครื่อง GitHub ตรงไปที่ api.gdeltproject.org):
  - api/v2/geo/geo        -> HTTP 404 ทุกแบบ (6 ครั้ง) = GDELT ปิด GEO 2.0 แล้ว
  - TimelineTone 30d/90d  -> HTTP 200
  - TimelineTone 100d ขึ้นไป (120d/180d/365d/540d/18m) -> HTTP 429 "query too large"

เทสพวกนี้ล็อกพฤติกรรมที่แก้ไว้ ไม่ให้เผลอกลับไปขอยาวเกินหรือใช้ endpoint ที่ตายแล้ว
(ไม่ต้องต่อเน็ต — ปลอมชั้นเรียก HTTP ทั้งหมด)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")

from database import init_db  # noqa: E402
from services import gdelt as G, country_geo as CG  # noqa: E402

# เก็บฟังก์ชันจริงไว้ก่อนที่ fixture จะแทนที่ (ใช้ตอนทดสอบตัวคุมจังหวะเอง)
_REAL_THROTTLE = G._throttle


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """ปิดการเว้นจังหวะ/คูลดาวน์ เพื่อให้เทสเร็วและไม่ขึ้นกับเวลาจริง"""
    monkeypatch.setattr(G, "_throttle", lambda: True)
    yield


# ---------------------------------------------------------------------------
# 1) เพดาน timespan — ต้องไม่ยิงเกิน 90 วันเด็ดขาด
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("given,expected", [
    ("30d", "30d"), ("90d", "90d"),
    ("100d", "90d"), ("180d", "90d"), ("540d", "90d"),   # เกินเพดาน -> ตัด
    ("3m", "90d"), ("18m", "90d"), ("2y", "90d"),
    ("24h", "24h"), ("6h", "6h"),                        # ชั่วโมงปล่อยผ่าน
    ("", "90d"), ("abc", "90d"),                         # ค่าเพี้ยน -> ค่าปลอดภัย
])
def test_timespan_clamped_to_supported_max(given, expected):
    assert G._clamp_timespan(given) == expected


def test_fetch_never_requests_more_than_90_days(monkeypatch):
    """ต่อให้โค้ดที่อื่นขอ 540 วัน คำขอจริงที่ออกไปต้องไม่เกิน 90 วัน"""
    sent = {}

    class FakeResp:
        status_code = 200
        text = "{}"
        def json(self): return {"ok": True}

    def fake_get(url, params=None, timeout=None, headers=None):
        sent.update(params or {})
        return FakeResp()

    monkeypatch.setattr(G.requests, "get", fake_get)
    G._fetch_json("doc/doc", {"query": "x", "timespan": "540d"})
    assert sent["timespan"] == "90d"


def test_during_cooldown_no_requests_are_sent(monkeypatch):
    """
    ระหว่างพัก ต้องไม่ยิงออกไปเลยแม้แต่ครั้งเดียว

    หมายเหตุ: การ "เข้าสู่โหมดพัก" ต้องล้มติดกันหลายครั้งก่อน (ดูเทสข้อ 6)
    ล้มครั้งเดียวแล้วพักทั้งระบบเป็นบั๊กที่เคยทำให้ลูกโลกว่างเปล่า
    """
    calls = {"n": 0}

    class Resp429:
        status_code = 429
        text = "rate limited"
        def json(self): return {}

    monkeypatch.setattr(G.requests, "get",
                        lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), Resp429())[1])
    monkeypatch.setattr(G.time, "sleep", lambda s: None)
    monkeypatch.setattr(G, "_throttle", _REAL_THROTTLE)

    G._fail_streak[0] = 0
    G._cooldown_until[0] = G.time.time() + 60          # จำลองว่ากำลังพักอยู่
    assert G.in_cooldown() is True and G.cooldown_left() > 0

    assert G._fetch_json("doc/doc", {"query": "x"}) is None
    assert calls["n"] == 0, "ระหว่างพักต้องไม่ยิงเน็ตเลย"

    G._cooldown_until[0] = 0.0
    G._fail_streak[0] = 0


# ---------------------------------------------------------------------------
# 2) จุดบนลูกโลกต้องมาจาก ArtList + ประเทศ (ไม่ใช่ GEO ที่ตายแล้ว)
# ---------------------------------------------------------------------------
# ข่าวจำลอง — ครอบคลุมทุกธีมและมีเคสขอบ (ประเทศไม่รู้จัก / ไม่เข้าธีมไหน)
ARTS = [
    {"title": "Stock market rallies as inflation cools", "url": "http://a",
     "sourcecountry": "United States"},
    {"title": "Nvidia lifts capex on AI chip demand", "url": "http://b",
     "sourcecountry": "United States"},
    {"title": "New tariff package hits semiconductor imports", "url": "http://c",
     "sourcecountry": "China"},
    {"title": "Ceasefire talks stall as airstrikes continue", "url": "http://d",
     "sourcecountry": "Israel"},
    {"title": "Crude oil climbs on OPEC supply cut", "url": "http://e",
     "sourcecountry": "Saudi Arabia"},
    {"title": "Earthquake damages port infrastructure", "url": "http://f",
     "sourcecountry": "Japan"},
    {"title": "Thai baht firms as SET index gains", "url": "http://g",
     "sourcecountry": "Thailand"},
    {"title": "Retailer cuts full-year guidance after weak revenue", "url": "http://h",
     "sourcecountry": "United Kingdom"},
    {"title": "Local bakery wins award", "url": "http://i",
     "sourcecountry": "France"},                                   # ไม่เข้าธีมไหน
    {"title": "Report from an unmapped place", "url": "http://j",
     "sourcecountry": "Neverland"},                                # ประเทศไม่รู้จัก
]


def _fake_gdelt(monkeypatch, per_call=None, store=None):
    """
    ปลอมชั้น HTTP + นับจำนวนคำขอ + ตรวจว่าคำขอ "ถูกรูปแบบที่วัดแล้วว่าผ่าน"
    per_call: ฟังก์ชัน(word, n) -> รายการข่าว (None = คืน ARTS ทุกครั้ง)
    """
    calls = {"n": 0, "words": []}
    store = store if store is not None else {}

    def fake_fetch(path, params, retries=1, timeout=None):
        calls["n"] += 1
        word = params.get("query", "")
        calls["words"].append(word)
        # ข้อจำกัดจริงจาก GDELT (วัดแล้ว): ต้องเป็นคำเดียว + maxrecords=50
        assert path == "doc/doc"
        assert params.get("mode") == "ArtList"
        assert " OR " not in word, "คำค้นที่มี OR โดน GDELT ปฏิเสธ 100% ห้ามใช้"
        assert " " not in word.strip(), "ต้องเป็นคำเดียวเท่านั้น"
        assert params.get("maxrecords") == G.Config.WORLD_MAXRECORDS
        return {"articles": (per_call(word, calls["n"]) if per_call else list(ARTS))}

    monkeypatch.setattr(G, "_fetch_json", fake_fetch)
    monkeypatch.setattr(G, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))
    # เส้นทางที่ผู้ใช้เปิดหน้าต้องไม่ยิงเน็ตเอง แค่ "ปลุก" ตัวเก็บเบื้องหลัง
    # เทสจึงนับการปลุกแทนการรันเธรดจริง (เธรดจริงมีเทสของตัวเองด้านล่าง)
    calls["fill_calls"] = 0

    def fake_ensure():
        calls["fill_calls"] += 1
        return not (store.get(G.POOL_KEY) or {}).get("articles")

    monkeypatch.setattr(G, "ensure_filling", fake_ensure)
    return calls, store


def test_page_load_never_waits_for_gdelt(monkeypatch):
    """
    เปิดหน้าลูกโลก = **ไม่ยิง GDELT แบบรอคำตอบเลย** แค่ปลุกตัวเก็บเบื้องหลัง

    วัดจริงแล้ว GDELT ใช้เวลาตอบ 10-18 วินาทีและปฏิเสธราวครึ่งหนึ่ง
    ถ้าเปิดหน้าแล้วรอ = หน้าค้างนานและว่างเปล่าบ่อย เทสนี้กันไม่ให้กลับไปเป็นแบบนั้น
    """
    calls, store = _fake_gdelt(monkeypatch)
    G.refill_pool(1)                              # สมมติตัวเก็บเบื้องหลังทำงานไปแล้ว
    before = calls["n"]

    res = G.all_theme_points("24h")
    assert calls["n"] == before, f"เปิดหน้าต้องไม่ยิง GDELT แต่ยิงเพิ่ม {calls['n'] - before}"
    assert calls["fill_calls"] == 1, "ต้องปลุกตัวเก็บเบื้องหลังทุกครั้งที่เปิดหน้า"
    assert res["ok"] and res["points"]


def test_empty_pool_page_still_answers_and_says_it_is_filling(monkeypatch):
    """คลังยังว่าง: หน้าเว็บต้องได้คำตอบทันที + รู้ว่ากำลังเก็บอยู่ (ไม่ใช่ค้างรอ)"""
    calls, _ = _fake_gdelt(monkeypatch)
    res = G.all_theme_points("24h")
    assert calls["n"] == 0, "คลังว่างก็ห้ามรอ GDELT ตรงหน้าเว็บ"
    assert res["filling"] is True and res["ok"] is False
    assert res.get("error") and res.get("note")


def test_request_shape_matches_what_gdelt_accepts(monkeypatch):
    """รูปแบบคำขอต้องตรงกับที่วัดแล้วว่าผ่าน (คำเดียว + maxrecords=50)"""
    calls, _ = _fake_gdelt(monkeypatch)          # assertion อยู่ใน fake_fetch
    G.refill_pool(rounds=1)
    assert calls["n"] == 1
    assert calls["words"][0] in G.Config.WORLD_FETCH_WORDS


def test_words_rotate_so_pool_covers_more_themes(monkeypatch):
    """เก็บหลายรอบต้องวนคำไปเรื่อย ๆ ไม่ยิงคำเดิมซ้ำ"""
    calls, store = _fake_gdelt(monkeypatch)
    for _ in range(4):
        G.refill_pool(1)
    assert len(set(calls["words"])) == 4, f"ต้องวนคำ แต่ได้ {calls['words']}"


def test_filler_keeps_trying_until_pool_is_full(monkeypatch):
    """
    หัวใจของการแก้ครั้งนี้: GDELT ปฏิเสธราวครึ่งหนึ่ง ตัวเก็บจึงห้ามยอมแพ้ครั้งเดียว

    จำลองให้ล้ม 3 ครั้งแรกแล้วค่อยสำเร็จ — ต้องได้ข่าวเข้าคลังจริง
    (ยิงครั้งเดียวแล้วเลิกแบบเดิม = ลูกโลกว่าง ซึ่งเป็นบั๊กที่ผู้ใช้เจอ)
    """
    calls, _ = _fake_gdelt(monkeypatch,
                           per_call=lambda w, n: [] if n <= 3 else list(ARTS))
    G.fill_rounds(target=len(ARTS), max_rounds=8, gap=0)
    assert calls["n"] >= 4, f"ต้องลองต่อหลังล้ม แต่ยิงแค่ {calls['n']} ครั้ง"
    assert len(G._pool_load()["articles"]) == len(ARTS)


def test_filler_stops_when_target_reached(monkeypatch):
    """ถึงเป้าแล้วต้องหยุด ไม่ยิง GDELT รัวไปเรื่อย ๆ"""
    calls, _ = _fake_gdelt(monkeypatch)
    G.fill_rounds(target=len(ARTS), max_rounds=8, gap=0)
    assert calls["n"] == 1, f"ได้ครบตั้งแต่ครั้งแรกต้องหยุด แต่ยิง {calls['n']} ครั้ง"


def test_filler_gives_up_after_max_rounds(monkeypatch):
    """GDELT ล่มยาว ตัวเก็บต้องเลิกตามจำนวนรอบ ไม่วนไม่รู้จบ"""
    calls, _ = _fake_gdelt(monkeypatch, per_call=lambda w, n: [])
    G.fill_rounds(target=100, max_rounds=5, gap=0)
    assert calls["n"] == 5


def test_pool_survives_failed_fetch(monkeypatch):
    """
    หัวใจของความทนทาน: รอบเก็บถัดไปล้ม ลูกโลกต้องยังวาดจากคลังเดิมได้
    """
    calls, store = _fake_gdelt(monkeypatch,
                               per_call=lambda w, n: list(ARTS) if n == 1 else [])
    G.refill_pool(1)
    first = G.all_theme_points("24h")
    assert first["ok"] and first["points"]

    G.refill_pool(1)                             # รอบนี้ GDELT คืนว่าง
    second = G.all_theme_points("24h")
    assert second["ok"], "ต้องยังวาดลูกโลกได้จากคลังเดิม"
    assert len(second["points"]) == len(first["points"])


def test_pool_dedupes_and_accumulates(monkeypatch):
    """ข่าวซ้ำต้องไม่นับซ้ำ · ข่าวใหม่ต้องสะสมเพิ่ม"""
    def per_call(word, n):
        if n == 1:
            return list(ARTS)
        return [{"title": "Chip plant expands in Korea", "url": "http://new1",
                 "sourcecountry": "South Korea"}] + list(ARTS[:3])   # ซ้ำ 3 ชิ้น

    calls, store = _fake_gdelt(monkeypatch, per_call=per_call)
    G.refill_pool(1)
    size1 = len(G._pool_load()["articles"])
    G.refill_pool(1)
    size2 = len(G._pool_load()["articles"])
    assert size1 == len(ARTS)
    assert size2 == size1 + 1, f"ควรเพิ่มแค่ข่าวใหม่ 1 ชิ้น แต่ได้ {size2 - size1}"


def test_pool_drops_articles_older_than_window(monkeypatch):
    import time as _t
    old = [{"title": "Old market news", "url": "http://old",
            "sourcecountry": "Japan",
            "_t": _t.time() - (G.Config.WORLD_POOL_HOURS + 2) * 3600}]
    fresh = [{"title": "Fresh market news", "url": "http://fresh",
              "sourcecountry": "Japan", "_t": _t.time()}]
    kept = G._pool_prune(old + fresh)
    urls = {a["url"] for a in kept}
    assert "http://fresh" in urls and "http://old" not in urls


def test_articles_classified_into_right_themes(monkeypatch):
    _fake_gdelt(monkeypatch)
    G.refill_pool(1)
    snap = G.world_snapshot("24h")
    got = {t["key"]: t["count"] for t in snap["themes"]}
    for key in ("market", "inflation", "tech", "trade", "conflict",
                "energy", "disaster", "thailand", "earnings"):
        assert got.get(key, 0) > 0, f"ธีม {key} ควรมีจุดจากข่าวที่ให้ไป"
    # ข่าวที่พาดหัวแยกธีมไม่ได้ ("Local bakery wins award") ต้องไม่หายไปเฉย ๆ
    # แต่ไปอยู่ในธีมของคำที่ใช้ค้นมา
    assert snap["unclassified"] == 0

    # ส่วนข่าวที่ไม่รู้ที่มา (ไม่มีคำค้นกำกับ) ต้องยังถูกนับไว้อย่างซื่อสัตย์
    orphan = G._classify_articles([{"title": "Local bakery wins award",
                                    "url": "http://x", "sourcecountry": "France"}])
    assert len(orphan.get("_none", [])) == 1


def test_theme_filter_does_not_fire_extra_requests(monkeypatch):
    """กดกรองธีมบนหน้าเว็บ ต้องไม่ยิง GDELT เพิ่ม"""
    calls, _ = _fake_gdelt(monkeypatch)
    G.refill_pool(1)
    before = calls["n"]
    for key in G.Config.WORLD_THEMES:
        assert G.world_points(theme=key, timespan="24h")["theme"] == key
    assert calls["n"] == before, "การกรองธีมต้องใช้คลังเดิม ไม่ยิงใหม่"


def test_unknown_country_skipped(monkeypatch):
    _fake_gdelt(monkeypatch)
    G.refill_pool(1)
    snap = G.world_snapshot("24h")
    names = {p["name"] for p in snap["points"]}
    assert "Neverland" not in names and "United States" in names
    us = [p for p in snap["points"]
          if p["name"] == "United States" and p["theme"] == "market"]
    assert us and us[0]["articles"], "ต้องมีลิงก์ข่าวให้คลิกดู"


def test_reports_error_when_pool_empty_and_fetch_fails(monkeypatch):
    _fake_gdelt(monkeypatch, per_call=lambda w, n: [])
    res = G.all_theme_points("24h")
    assert res["ok"] is False and res.get("error")
    assert len(res["themes"]) == len(G.Config.WORLD_THEMES)


def test_background_warm_fetches_more_words(monkeypatch):
    """ตัวเก็บเบื้องหลังไม่มีใครรอ จึงเติมได้หลายคำต่อรอบ"""
    calls, _ = _fake_gdelt(monkeypatch, per_call=lambda w, n: list(ARTS[:1]))
    G.warm_cache("24h")
    assert calls["n"] >= 3, f"ควรเติมหลายคำต่อรอบ แต่ยิง {calls['n']}"
    assert len(set(calls["words"])) == calls["n"], "ต้องวนคำไม่ซ้ำ"


def test_theme_points_offset_so_bars_do_not_overlap(monkeypatch):
    """สองธีมที่มีข่าวจากประเทศเดียวกัน ต้องไม่วางแท่งทับกันสนิท"""
    arts = [
        {"title": "War escalates in the region", "url": "http://w",
         "sourcecountry": "Japan"},
        {"title": "Chip maker expands data center", "url": "http://c",
         "sourcecountry": "Japan"},
    ]
    _fake_gdelt(monkeypatch, per_call=lambda w, n: list(arts))
    G.refill_pool(1)
    snap = G.world_snapshot("24h")
    a = [p for p in snap["points"] if p["theme"] == "conflict"][0]
    b = [p for p in snap["points"] if p["theme"] == "tech"][0]
    assert (a["lat"], a["lon"]) != (b["lat"], b["lon"])
    assert abs(a["lat"] - b["lat"]) < 6 and abs(a["lon"] - b["lon"]) < 6


# ---------------------------------------------------------------------------
# 3) ตารางพิกัดประเทศ
# ---------------------------------------------------------------------------
def test_country_coords_valid_and_aliases_resolve():
    assert CG.known_count() > 80
    for name, (lat, lon) in CG.COUNTRY_COORDS.items():
        assert -90 <= lat <= 90 and -180 <= lon <= 180, name
    assert CG.coords_for("USA") == CG.COUNTRY_COORDS["United States"]
    assert CG.coords_for("  Thailand  ") == CG.COUNTRY_COORDS["Thailand"]
    assert CG.coords_for("Atlantis") is None
    assert CG.coords_for("") is None


# ---------------------------------------------------------------------------
# 4) เครื่องเรียนรู้ต้องรวมข่าวสด + คลังที่สะสมเอง (ทะลุเพดาน 90 วันของ GDELT)
# ---------------------------------------------------------------------------
def test_feature_series_merges_stored_history_beyond_gdelt_window(monkeypatch):
    from services import correlation as C

    live = {"2026-07-20": 1.0, "2026-07-21": 2.0}          # GDELT ให้แค่ช่วงสั้น
    stored = {"2026-01-05": -5.0, "2026-07-20": 99.0}      # คลังของเราเองยาวกว่า

    monkeypatch.setattr(C.gdelt, "theme_query", lambda k: "q")
    monkeypatch.setattr(C.gdelt, "tone_timeline",
                        lambda q, timespan="": {"series": live})
    monkeypatch.setattr(C, "obs_series", lambda kind, key, since_day=None: stored)

    ser = C._feature_series("news:conflict", 90)
    assert "2026-01-05" in ser                 # ข้อมูลเก่ากว่าที่ GDELT ให้ ยังอยู่
    assert ser["2026-07-20"] == 1.0            # ช่วงที่ทับกัน ใช้ค่าจาก GDELT (สดกว่า)
    assert ser["2026-07-21"] == 2.0


# ---------------------------------------------------------------------------
# 5) แบ่งยิงทีละช่วง แล้วสะสมจนครบ — ทะลุเพดาน 90 วันของ GDELT
# ---------------------------------------------------------------------------
def test_chunk_ranges_cover_full_period_without_gaps():
    import datetime as dt
    for days in (90, 180, 365, 540):
        rs = G._chunk_ranges(days)
        assert sum((e - s).days for s, e in rs) == days      # ครอบคลุมครบ ไม่ขาดไม่เกิน
        for s, e in rs:
            assert 0 < (e - s).days <= G.CHUNK_DAYS          # ทุกช่วงไม่เกินเพดาน
        # ต่อกันสนิท: ปลายของช่วงถัดไป = ต้นของช่วงก่อนหน้า
        for prev, nxt in zip(rs, rs[1:]):
            assert nxt[1] == prev[0]


def test_chunked_timeline_merges_and_limits_new_fetches(monkeypatch):
    """ยาว 540 วัน -> ยิงใหม่ได้ไม่เกินโควตาต่อครั้ง แต่ของที่เก็บไว้ต้องเอามารวมหมด"""
    store = {}
    calls = {"n": 0}

    def fake_fetch(path, params, retries=2):
        calls["n"] += 1
        assert "startdatetime" in params and "enddatetime" in params
        assert "timespan" not in params
        day = params["startdatetime"][:8]
        return {"timeline": [{"series": "Average Tone",
                              "data": [{"date": day + "T000000Z", "value": 1.0}]}]}

    monkeypatch.setattr(G, "_fetch_json", fake_fetch)
    monkeypatch.setattr(G, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))

    first = G._chunked_timeline("q", "TimelineTone", 540, "tone")
    assert calls["n"] == G.MAX_NEW_CHUNKS_PER_CALL       # ครั้งแรกดึงแค่โควตา
    assert first["chunks"]["pending"] > 0 and first["note"]
    assert len(first["series"]) == G.MAX_NEW_CHUNKS_PER_CALL

    # เรียกซ้ำเรื่อย ๆ ต้องค่อย ๆ ครบ แล้วหยุดยิงเมื่อครบ
    for _ in range(10):
        res = G._chunked_timeline("q", "TimelineTone", 540, "tone")
        if not res["chunks"]["pending"]:
            break
    assert res["chunks"]["pending"] == 0
    assert res["chunks"]["ready"] == res["chunks"]["total"]
    assert res["note"] is None

    before = calls["n"]
    G._chunked_timeline("q", "TimelineTone", 540, "tone")
    assert calls["n"] == before                          # ครบแล้วไม่ยิงซ้ำอีก


def test_long_timespan_routes_to_chunking_not_single_request(monkeypatch):
    """ขอ 540 วัน ต้องไปทางแบ่งยิง ไม่ใช่ยิงรวดเดียวแล้วโดน 429"""
    used = {}
    monkeypatch.setattr(G, "_chunked_timeline",
                        lambda q, m, d, t: used.update(days=d, mode=m) or {"series": {}, "ok": True})
    G.tone_timeline("q", timespan="540d")
    assert used == {"days": 540, "mode": "TimelineTone"}


def test_short_timespan_still_single_request(monkeypatch):
    """ขอสั้น ๆ ต้องยิงรวดเดียวเหมือนเดิม (ไม่เสียเวลาแบ่ง)"""
    seen = {}

    def fake_fetch(path, params, retries=2):
        seen.update(params)
        return {"timeline": [{"series": "Average Tone",
                              "data": [{"date": "20260726T000000Z", "value": 2.0}]}]}

    monkeypatch.setattr(G, "_fetch_json", fake_fetch)
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: None)

    res = G.tone_timeline("q", timespan="30d")
    assert res["ok"] and seen.get("timespan") == "30d"
    assert "startdatetime" not in seen


def test_backfill_rotates_themes_and_stays_gentle(monkeypatch):
    """ตัวเก็บเบื้องหลังต้องทำทีละ 2 ธีม แล้ววนไปธีมถัดไปในรอบหน้า"""
    seen = []

    def fake_chunked(q, mode, days, tag):
        seen.append(q)
        return {"series": {}, "ok": True,
                "chunks": {"total": 7, "ready": 2, "pending": 5}}

    monkeypatch.setattr(G, "_chunked_timeline", fake_chunked)
    G._backfill_cursor[0] = 0

    r1 = G.backfill(days=540, themes_per_run=2)
    assert r1["themes"] == 2 and r1["pending"] == 10
    r2 = G.backfill(days=540, themes_per_run=2)
    assert r2["themes"] == 2
    assert len(set(seen)) == 4          # รอบสองไปธีมใหม่ ไม่ซ้ำรอบแรก


def test_backfill_survives_no_themes(monkeypatch):
    monkeypatch.setattr(G.Config, "WORLD_THEMES", {})
    assert G.backfill()["themes"] == 0


# ---------------------------------------------------------------------------
# 6) ล้มครั้งเดียวห้ามทำให้ทั้งระบบหยุด + ต้องมีของสำรองแสดงแทนหน้าว่าง
#    (บั๊กจริงจากเครื่องผู้ใช้: ธีมแรกโดน 429 -> พัก 45 วิ -> อีก 8 ธีมถูกข้าม
#     ลูกโลกจึงว่างเปล่าทั้งที่ GDELT แค่งอแงชั่วคราว)
# ---------------------------------------------------------------------------
def test_single_failure_does_not_freeze_everything(monkeypatch):
    calls = {"n": 0}

    class Resp429:
        status_code = 429
        text = "rate limited"
        def json(self): return {}

    class RespOK:
        status_code = 200
        text = "{}"
        def json(self): return {"ok": True}

    def fake_get(url, params=None, timeout=None, headers=None):
        calls["n"] += 1
        return Resp429() if calls["n"] == 1 else RespOK()

    monkeypatch.setattr(G.requests, "get", fake_get)
    monkeypatch.setattr(G.time, "sleep", lambda s: None)
    monkeypatch.setattr(G, "_throttle", _REAL_THROTTLE)
    G._cooldown_until[0] = 0.0
    G._fail_streak[0] = 0

    assert G._fetch_json("doc/doc", {"query": "a"}, retries=0) is None   # ล้มครั้งที่ 1
    assert G.in_cooldown() is False, "ล้มครั้งเดียวต้องยังไม่พัก"
    assert G._fetch_json("doc/doc", {"query": "b"}, retries=0) == {"ok": True}
    assert G._fail_streak[0] == 0, "สำเร็จแล้วต้องรีเซ็ตตัวนับ"


def test_cooldown_only_after_repeated_failures(monkeypatch):
    class Resp429:
        status_code = 429
        text = "rate limited"
        def json(self): return {}

    monkeypatch.setattr(G.requests, "get", lambda *a, **k: Resp429())
    monkeypatch.setattr(G.time, "sleep", lambda s: None)
    monkeypatch.setattr(G, "_throttle", _REAL_THROTTLE)
    G._cooldown_until[0] = 0.0
    G._fail_streak[0] = 0

    for i in range(G._FAILS_BEFORE_COOLDOWN - 1):
        G._fetch_json("doc/doc", {"query": f"q{i}"}, retries=0)
        assert G.in_cooldown() is False, f"ล้ม {i+1} ครั้งยังไม่ควรพัก"
    G._fetch_json("doc/doc", {"query": "last"}, retries=0)
    assert G.in_cooldown() is True, "ล้มครบเกณฑ์แล้วต้องพัก"
    G._cooldown_until[0] = 0.0
    G._fail_streak[0] = 0


def test_globe_still_reports_error_when_nothing_cached(monkeypatch):
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: None)
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: None)
    res = G.world_points(theme="market")
    assert res["ok"] is False and res.get("error") and not res.get("stale")


def test_timeline_falls_back_to_last_good(monkeypatch):
    store = {}
    monkeypatch.setattr(G, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: {
        "timeline": [{"series": "Average Tone",
                      "data": [{"date": "20260730T000000Z", "value": -1.2}]}]})

    a = G.tone_timeline("q", timespan="30d")
    assert a["ok"] and a["series"]

    store.pop("gdelt:tone:q:30d", None)
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: None)
    b = G.tone_timeline("q", timespan="30d")
    assert b["series"] == a["series"] and b["stale"] is True




def test_untitled_theme_falls_back_to_search_word(monkeypatch):
    """
    พาดหัวที่ไม่มีคำอังกฤษให้แยกธีม (เช่นข่าวจีน/ญี่ปุ่น) ต้องไม่ถูกทิ้ง

    วัดจริงจาก GDELT: ข่าว 149 ชิ้นแยกธีมจากพาดหัวได้แค่ 24 ชิ้น
    ที่เหลือหายไปจากลูกโลกทั้งที่เรารู้ว่าค้นมาด้วยคำอะไร
    """
    arts = [{"title": "存储芯片短缺波及产业链", "url": "http://cn1",
             "sourcecountry": "China"}]
    _fake_gdelt(monkeypatch, per_call=lambda w, n: list(arts))
    G.refill_pool(1)                     # คำแรกใน WORLD_FETCH_WORDS
    word = G.Config.WORLD_FETCH_WORDS[0]
    expect = G.Config.WORLD_WORD_THEME[word.lower()]

    snap = G.world_snapshot("24h")
    got = {t["key"]: t["count"] for t in snap["themes"]}
    assert got[expect] == 1, f"ข่าวที่ค้นด้วย '{word}' ควรเข้าธีม {expect}"
    assert snap["unclassified"] == 0


def test_every_fetch_word_maps_to_a_real_theme():
    """ทุกคำที่ยิงต้องรู้ว่าเป็นธีมไหน ไม่งั้นข่าวจะหล่นหายเงียบ ๆ"""
    for w in G.Config.WORLD_FETCH_WORDS:
        key = G.Config.WORLD_WORD_THEME.get(w.lower())
        assert key in G.Config.WORLD_THEMES, f"คำ '{w}' ยังไม่ได้จับคู่ธีม"


@pytest.mark.parametrize("title,should_be_conflict", [
    ("Local bakery wins award", False),          # award มี war อยู่ข้างใน
    ("Company issues profit warning", False),    # warning ก็มี war
    ("New warehouse opens in Ohio", False),
    ("War escalates near the border", True),
    ("Postwar reconstruction begins", False),    # จับทั้งคำเท่านั้น
])
def test_theme_keywords_match_whole_words_only(title, should_be_conflict):
    """
    จับคำต้องเป็น "ทั้งคำ" ไม่ใช่ substring
    (บั๊กจริง: ข่าวร้านเบเกอรี่ชนะรางวัลถูกปักเป็นข่าวสงครามบนลูกโลก)
    """
    got = G._classify_articles([{"title": title, "url": "http://t",
                                 "sourcecountry": "France"}])
    assert ("conflict" in got) is should_be_conflict
