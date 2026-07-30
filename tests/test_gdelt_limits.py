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
    {"title": "Local bakery wins award", "url": "http://i",          # ไม่เข้าธีมไหน
     "sourcecountry": "France"},
    {"title": "Report from an unmapped place", "url": "http://j",
     "sourcecountry": "Neverland"},                                   # ประเทศไม่รู้จัก
]


def _mock_one_request(monkeypatch, arts=None, store=None):
    """ปลอมชั้น HTTP + นับจำนวนคำขอ เพื่อพิสูจน์ว่ายิงครั้งเดียวจริง"""
    calls = {"n": 0}
    store = store if store is not None else {}

    def fake_fetch(path, params, retries=1, timeout=None):
        calls["n"] += 1
        assert path == "doc/doc", "ต้องไม่ใช้ geo/geo ที่ตอบ 404"
        assert params.get("mode") == "ArtList"
        return {"articles": ARTS if arts is None else arts}

    monkeypatch.setattr(G, "_fetch_json", fake_fetch)
    monkeypatch.setattr(G, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))
    return calls, store


def test_globe_uses_exactly_one_request_for_all_themes(monkeypatch):
    """
    หัวใจของการแก้ลูกโลก: ทุกธีมต้องมาจากคำขอเดียว

    เดิมยิงธีมละครั้ง (9 ครั้ง) พอครั้งแรกโดนปฏิเสธ ที่เหลือล้มตามกันหมด
    ลูกโลกจึงว่างเปล่า — เทสนี้กันไม่ให้กลับไปเป็นแบบนั้นอีก
    """
    calls, _ = _mock_one_request(monkeypatch)
    res = G.all_theme_points(timespan="24h")

    assert calls["n"] == 1, f"ต้องยิงครั้งเดียว แต่ยิง {calls['n']} ครั้ง"
    assert res["ok"] and res["points"], "ต้องได้จุดมาวาด"
    assert len(res["themes"]) == len(G.Config.WORLD_THEMES), "ต้องมีทุกธีมในผล"
    assert res["articles_seen"] == len(ARTS)


def test_articles_are_classified_into_right_themes(monkeypatch):
    _mock_one_request(monkeypatch)
    snap = G.world_snapshot("24h")
    got = {t["key"]: t["count"] for t in snap["themes"]}

    # ธีมที่มีข่าวชัดเจนในชุดทดสอบ ต้องมีจุด
    for key in ("market", "inflation", "tech", "trade", "conflict",
                "energy", "disaster", "thailand", "earnings"):
        assert got.get(key, 0) > 0, f"ธีม {key} ควรมีจุดจากข่าวที่ให้ไป"
    assert snap["unclassified"] >= 1, "ข่าวที่ไม่เข้าธีมต้องถูกนับไว้อย่างซื่อสัตย์"


def test_theme_filter_does_not_fire_extra_requests(monkeypatch):
    """กดกรองธีมบนหน้าเว็บ ต้องไม่ยิง GDELT เพิ่ม"""
    calls, store = _mock_one_request(monkeypatch)
    G.world_snapshot("24h")
    before = calls["n"]

    for key in G.Config.WORLD_THEMES:
        r = G.world_points(theme=key, timespan="24h")
        assert r["theme"] == key
    assert calls["n"] == before, "การกรองธีมต้องใช้ข้อมูลเดิม ไม่ยิงใหม่"


def test_unknown_country_skipped_and_counts_correct(monkeypatch):
    _mock_one_request(monkeypatch)
    snap = G.world_snapshot("24h")
    names = {p["name"] for p in snap["points"]}
    assert "Neverland" not in names, "ประเทศที่ไม่มีพิกัดต้องถูกข้าม"
    assert "United States" in names and "Thailand" in names

    us_market = [p for p in snap["points"]
                 if p["name"] == "United States" and p["theme"] == "market"]
    assert us_market and us_market[0]["count"] >= 1
    assert us_market[0]["articles"], "ต้องมีลิงก์ข่าวให้คลิกดู"


def test_globe_reports_failure_when_no_data_and_no_cache(monkeypatch):
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: None)
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: None)
    res = G.all_theme_points()
    assert res["ok"] is False and res.get("error")
    assert res["points"] == [] and len(res["themes"]) == len(G.Config.WORLD_THEMES)


def test_globe_falls_back_to_last_good_snapshot(monkeypatch):
    """ดึงสดไม่ได้ -> ต้องแสดง snapshot ล่าสุดที่เคยได้ พร้อมบอกว่าเป็นของเก่า"""
    calls, store = _mock_one_request(monkeypatch)
    first = G.all_theme_points("24h")
    assert first["ok"] and not first.get("stale_themes")

    store.pop("gdelt:snap:24h", None)                    # cache สดหมดอายุ
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: None)   # แล้วดึงสดล้ม

    second = G.all_theme_points("24h")
    assert len(second["points"]) == len(first["points"]), "ต้องได้จุดเดิมกลับมา"
    assert second["stale_themes"] > 0 and second.get("note")


def test_theme_points_offset_so_bars_do_not_overlap(monkeypatch):
    """สองธีมที่มีข่าวจากประเทศเดียวกัน ต้องไม่วางแท่งทับกันสนิท"""
    arts = [
        {"title": "War escalates in the region", "url": "http://w",
         "sourcecountry": "Japan"},
        {"title": "Chip maker expands data center", "url": "http://c",
         "sourcecountry": "Japan"},
    ]
    _mock_one_request(monkeypatch, arts=arts)
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


