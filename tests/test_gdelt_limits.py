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


def test_429_triggers_cooldown_and_stops_hammering(monkeypatch):
    """โดน 429 จนหมดโควตาลองใหม่ -> ต้องเข้าโหมดพัก ไม่ยิงซ้ำทันที"""
    calls = {"n": 0}

    class Resp429:
        status_code = 429
        text = "rate limited"
        def json(self): return {}

    def fake_get(url, params=None, timeout=None, headers=None):
        calls["n"] += 1
        return Resp429()

    monkeypatch.setattr(G.requests, "get", fake_get)
    monkeypatch.setattr(G.time, "sleep", lambda s: None)   # ไม่ต้องรอจริง
    monkeypatch.setattr(G, "_throttle", _REAL_THROTTLE)    # ใช้ของจริงเพื่อทดสอบคูลดาวน์
    G._cooldown_until[0] = 0.0

    assert G._fetch_json("doc/doc", {"query": "x"}, retries=1) is None
    assert calls["n"] == 2                                  # ลอง 2 ครั้งแล้วหยุด
    assert G._cooldown_until[0] > 0                         # เข้าโหมดพักแล้ว

    before = calls["n"]
    assert G._fetch_json("doc/doc", {"query": "x"}) is None  # ระหว่างพัก
    assert calls["n"] == before                             # ต้องไม่ยิงเพิ่มเลย
    G._cooldown_until[0] = 0.0


# ---------------------------------------------------------------------------
# 2) จุดบนลูกโลกต้องมาจาก ArtList + ประเทศ (ไม่ใช่ GEO ที่ตายแล้ว)
# ---------------------------------------------------------------------------
def test_world_points_uses_artlist_not_dead_geo_endpoint(monkeypatch):
    used = {}

    def fake_fetch(path, params, retries=2):
        used["path"] = path
        used["mode"] = params.get("mode")
        return {"articles": [
            {"title": "A", "url": "http://a", "sourcecountry": "United States"},
            {"title": "B", "url": "http://b", "sourcecountry": "United States"},
            {"title": "C", "url": "http://c", "sourcecountry": "Thailand"},
            {"title": "D", "url": "http://d", "sourcecountry": "Neverland"},  # ไม่รู้จัก
        ]}

    monkeypatch.setattr(G, "_fetch_json", fake_fetch)
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: None)

    res = G.world_points(theme="market", timespan="24h")

    assert used["path"] == "doc/doc"          # ไม่ใช่ "geo/geo" ที่ตอบ 404
    assert used["mode"] == "ArtList"
    assert res["ok"] and len(res["points"]) == 2       # ประเทศที่ไม่รู้จักถูกข้าม
    top = res["points"][0]
    assert top["name"] == "United States" and top["count"] == 2   # เรียงตามจำนวนข่าว
    assert top["articles"][0]["url"] == "http://a"


def test_world_points_reports_failure_instead_of_pretending(monkeypatch):
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: None)
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    res = G.world_points(theme="market")
    assert res["ok"] is False and res["points"] == [] and res.get("error")


def test_theme_points_offset_so_bars_do_not_overlap(monkeypatch):
    """สองธีมที่มีข่าวจากประเทศเดียวกัน ต้องไม่วางแท่งทับกันสนิท"""
    arts = [{"title": "T", "url": "http://t", "sourcecountry": "Japan"}]
    monkeypatch.setattr(G, "_fetch_json", lambda *a, **k: {"articles": arts})
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: None)

    a = G.world_points(theme="conflict")["points"][0]
    b = G.world_points(theme="tech")["points"][0]
    assert (a["lat"], a["lon"]) != (b["lat"], b["lon"])
    assert abs(a["lat"] - b["lat"]) < 6 and abs(a["lon"] - b["lon"]) < 6   # ยังอยู่ประเทศเดิม


def test_all_theme_points_survives_partial_failure(monkeypatch):
    """บางธีมโดนจำกัดอัตรา -> ต้องคืนของที่ได้ พร้อมบอกว่าขาดกี่ธีม"""
    state = {"n": 0}

    def flaky(path, params, retries=2):
        state["n"] += 1
        if state["n"] % 2:
            return None
        return {"articles": [{"title": "x", "url": "http://x",
                              "sourcecountry": "France"}]}

    monkeypatch.setattr(G, "_fetch_json", flaky)
    monkeypatch.setattr(G, "cache_get", lambda k: None)
    monkeypatch.setattr(G, "cache_set", lambda k, v, ttl: None)

    res = G.all_theme_points()
    assert res["skipped_themes"] > 0
    assert res["points"] and res.get("note")


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
