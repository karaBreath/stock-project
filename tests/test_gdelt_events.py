"""
ทดสอบชั้นอ่านไฟล์ Events 2.0 ของ GDELT — แหล่งข่าว "ทั่วโลก" พร้อมพิกัดที่เกิดเหตุ

หลักฐานที่วัดจากเซิร์ฟเวอร์จริง (2026-07-30, GitHub runner):
  lastupdate.txt   -> HTTP 200 ใน 0.2s (ชี้ไฟล์ export / mentions / gkg)
  export.CSV.zip   -> HTTP 200 · 54 KB · 832 เหตุการณ์ · 61 คอลัมน์
  ยิงซ้ำ 3 ครั้ง    -> HTTP 200 ทุกครั้ง (ไม่ติดโควตาแบบ DOC API)
  พิกัด            -> ~65% ของแถว · 38 ประเทศในไฟล์เดียว

เทสพวกนี้ล็อกไว้ว่า "ต้องอ่านคอลัมน์ ActionGeo (ที่เกิดเหตุ) ไม่ใช่ Actor1Geo"
ซึ่งเป็นบั๊กที่ probe จับได้ก่อนเขียนโค้ดจริง (ต่างกัน 16 คอลัมน์)
"""
import io
import os
import sys
import time
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")

from database import init_db  # noqa: E402
from services import gdelt_events as E  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _clean_store(monkeypatch):
    """ให้แต่ละเทสมีคลังของตัวเอง ไม่ปนกัน"""
    store = {}
    monkeypatch.setattr(E, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(E, "cache_set", lambda k, v, ttl: store.__setitem__(k, v))
    yield store


def _row(**kw):
    """สร้างแถว Events 61 คอลัมน์ ใส่ค่าเฉพาะช่องที่เราสนใจ"""
    r = [""] * E.N_COLS
    r[E.C_ID] = kw.get("id", "1001")
    r[E.C_DATE] = "20260730"
    r[E.C_ROOT] = kw.get("root", "19")
    r[E.C_GOLD] = "-10.0"
    r[E.C_MENTIONS] = str(kw.get("mentions", 10))
    r[E.C_SOURCES] = "3"
    r[E.C_ARTICLES] = "8"
    r[E.C_TONE] = str(kw.get("tone", -5.0))
    # ตัวหลอก: ใส่ค่าที่ Actor1Geo ให้ผิดจากที่เกิดเหตุ เพื่อจับว่าอ่านคอลัมน์ถูก
    r[36] = "Washington, District of Columbia, United States"
    r[37] = "US"
    r[40] = "38.8951"
    r[41] = "-77.0364"
    r[E.C_GEO_TYPE] = "4"
    r[E.C_GEO_NAME] = kw.get("place", "Jerusalem, Israel (general), Israel")
    r[E.C_GEO_CC] = kw.get("cc", "IS")
    r[E.C_LAT] = kw.get("lat", "31.7667")
    r[E.C_LON] = kw.get("lon", "35.2333")
    r[E.C_URL] = kw.get("url", "https://news.example.com/2026/07/30/strikes-continue-overnight")
    return r


def _zip_of(rows) -> bytes:
    tsv = "\n".join("\t".join(r) for r in rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("20260730090000.export.CSV", tsv)
    return buf.getvalue()


class FakeResp:
    def __init__(self, content=b"", text="", code=200):
        self.status_code = code
        self.content = content
        self.text = text


def _fake_net(monkeypatch, rows, last_text=None):
    """ปลอมชั้น HTTP ทั้งหมด + นับคำขอ"""
    calls = {"n": 0, "urls": []}
    latest = ("54988 abc http://data.gdeltproject.org/gdeltv2/"
              "20260730090000.export.CSV.zip\n"
              "73650 def http://data.gdeltproject.org/gdeltv2/"
              "20260730090000.mentions.CSV.zip\n")

    class FakeSession:
        headers = {}

        def get(self, url, timeout=None, **kw):
            calls["n"] += 1
            calls["urls"].append(url)
            if url.endswith("lastupdate.txt"):
                return FakeResp(text=last_text if last_text is not None else latest)
            return FakeResp(content=_zip_of(rows))

    monkeypatch.setattr(E, "_session", lambda: FakeSession())
    monkeypatch.setattr(E, "_REQ_OK", True)
    return calls


# ---------------------------------------------------------------------------
# 1) อ่านคอลัมน์ถูกช่อง — บั๊กที่ probe จับได้
# ---------------------------------------------------------------------------
def test_reads_action_geo_not_actor_geo(monkeypatch):
    """
    ต้องใช้พิกัด "ที่เกิดเหตุ" (ActionGeo คอลัมน์ 52-57)
    ไม่ใช่พิกัดของผู้เล่นคนแรก (Actor1Geo คอลัมน์ 36-41)

    แถวทดสอบตั้งใจให้ Actor1Geo = วอชิงตัน แต่ที่เกิดเหตุ = เยรูซาเลม
    ถ้าอ่านผิดช่อง จุดจะไปโผล่ที่อเมริกาทั้งที่เรื่องอยู่ตะวันออกกลาง
    """
    _fake_net(monkeypatch, [_row()])
    rows = E.fetch_slice("http://x/20260730090000.export.CSV.zip")
    assert len(rows) == 1
    e = rows[0]
    assert e["lat"] == 31.767 and e["lon"] == 35.233, "ต้องเป็นพิกัดเยรูซาเลม"
    assert e["cc"] == "IS"
    assert "Jerusalem" in e["place"]


def test_skips_rows_without_coordinates_or_link(monkeypatch):
    """แถวที่ไม่มีพิกัดหรือไม่มีลิงก์ ใช้วาดจุดไม่ได้ ต้องข้าม ไม่ใช่เดาพิกัดให้"""
    good = _row(id="1")
    no_geo = _row(id="2", lat="", lon="")
    no_url = _row(id="3", url="")
    _fake_net(monkeypatch, [good, no_geo, no_url])
    rows = E.fetch_slice("http://x/a.export.CSV.zip")
    assert [r["id"] for r in rows] == ["1"]


def test_short_row_is_ignored(monkeypatch):
    """แถวที่คอลัมน์ไม่ครบ (ไฟล์เสีย) ต้องไม่ทำให้ทั้งไฟล์พัง"""
    _fake_net(monkeypatch, [["a", "b", "c"], _row(id="9")])
    rows = E.fetch_slice("http://x/a.export.CSV.zip")
    assert [r["id"] for r in rows] == ["9"]


# ---------------------------------------------------------------------------
# 2) จัดธีม
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("root,url,expect", [
    ("19", "https://x.com/news/border-clash", "conflict"),      # CAMEO สู้รบ
    ("20", "https://x.com/news/attack", "conflict"),
    ("05", "https://x.com/news/summit-talks", "geopolitics"),   # การทูต
    ("01", "https://x.com/news/statement", "geopolitics"),
    ("11", "https://x.com/news/condemns-move", "geopolitics"),  # ไม่ใช่ "การค้า"
    # ลิงก์ชนะรหัส CAMEO เพราะบอกเรื่องได้ตรงกว่า
    ("01", "https://x.com/2026/oil-prices-surge-opec", "energy"),
    ("19", "https://x.com/2026/earthquake-hits-coast", "disaster"),
    ("01", "https://x.com/2026/inflation-cools-rate-cut", "inflation"),
    ("01", "https://x.com/2026/nvidia-chip-demand", "tech"),
    ("01", "https://x.com/2026/thailand-set-index", "thailand"),
])
def test_theme_from_cameo_and_url(root, url, expect):
    assert E._theme_of(root, url) == expect


def test_every_cameo_root_maps_to_a_real_theme():
    """รหัส CAMEO 01-20 ต้องมีธีมรองรับครบ ไม่มีเหตุการณ์หล่นหาย"""
    from config import Config
    for i in range(1, 21):
        theme = E._theme_of(f"{i:02d}", "https://x.com/plain")
        assert theme in Config.WORLD_THEMES, f"root {i:02d} -> {theme} ไม่มีในธีม"


# ---------------------------------------------------------------------------
# 3) คลังสะสม
# ---------------------------------------------------------------------------
def test_collect_accumulates_and_dedupes(monkeypatch):
    calls = _fake_net(monkeypatch, [_row(id="1"), _row(id="2")])
    first = E.collect(max_slices=1)
    assert first["ok"] and first["added"] == 2

    # ไฟล์ช่วงเดิมต้องไม่ถูกดึงซ้ำ และเหตุการณ์ id เดิมต้องไม่นับซ้ำ
    before = calls["n"]
    second = E.collect(max_slices=1)
    assert E.status()["events"] == 2, "id เดิมต้องไม่นับซ้ำ"
    assert calls["n"] > before, "ยังต้องเช็ค lastupdate เพื่อดูว่ามีไฟล์ใหม่ไหม"
    assert second["slices"] == 0, "ไฟล์ช่วงเดิมต้องไม่โหลดซ้ำ"


def test_collect_backfills_when_store_is_empty(monkeypatch):
    """
    คลังว่าง = ต้องไล่ย้อนไฟล์ก่อนหน้าให้ทันที ไม่ปล่อยให้ลูกโลกว่าง
    รอสะสมทีละ 15 นาทีต่อไฟล์ช้าเกินไปสำหรับคนที่เพิ่งเปิดแอป
    """
    calls = _fake_net(monkeypatch, [_row(id="1")])
    E.collect(max_slices=3)
    exports = [u for u in calls["urls"] if ".export." in u]
    assert len(exports) == 3, f"ควรดึงย้อนหลังหลายไฟล์ แต่ได้ {exports}"
    # ต้องเป็นช่วงเวลาก่อนหน้าไฟล์ล่าสุด ห่างกัน 15 นาที
    assert "20260730084500" in " ".join(exports)
    assert "20260730083000" in " ".join(exports)


def test_prune_drops_old_events():
    old = {"id": "old", "_t": time.time() - (E.EVENTS_HOURS + 2) * 3600,
           "mentions": 99}
    new = {"id": "new", "_t": time.time(), "mentions": 1}
    kept = {e["id"] for e in E._prune([old, new])}
    assert kept == {"new"}


def test_prune_keeps_most_reported_when_over_limit(monkeypatch):
    """คลังเต็ม ต้องเก็บข่าวที่ 'โลกรายงานหนักที่สุด' ไว้ก่อน ไม่ใช่ตัดสุ่ม"""
    monkeypatch.setattr(E, "EVENTS_MAX", 3)
    now = time.time()
    events = [{"id": str(i), "_t": now, "mentions": i} for i in range(10)]
    kept = sorted(int(e["id"]) for e in E._prune(events))
    assert kept == [7, 8, 9]


def test_network_failure_leaves_store_usable(monkeypatch):
    """lastupdate.txt ล้ม ต้องไม่ทำให้คลังที่มีอยู่เสีย"""
    _fake_net(monkeypatch, [_row(id="1")])
    E.collect(max_slices=1)
    have = E.status()["events"]

    monkeypatch.setattr(E, "latest_export_urls", lambda sess=None: [])
    res = E.collect()
    assert res["ok"] is False and res.get("error")
    assert E.status()["events"] == have, "ของเดิมต้องยังอยู่"


# ---------------------------------------------------------------------------
# 4) จุดบนลูกโลก
# ---------------------------------------------------------------------------
def test_points_group_by_location_and_rank_by_world_attention(monkeypatch):
    """
    เรียงจุดตาม NumMentions = โลกรายงานเรื่องนั้นหนักแค่ไหน (ไม่ใช่เราเดาว่าสำคัญ)
    และเหตุการณ์ที่พิกัดเดียวกันต้องรวมเป็นจุดเดียว
    """
    rows = [
        _row(id="1", place="Jerusalem, Israel (general), Israel",
             lat="31.7667", lon="35.2333", mentions=5),
        _row(id="2", place="Jerusalem, Israel (general), Israel",
             lat="31.7690", lon="35.2350", mentions=7),      # ใกล้กัน -> จุดเดียว
        _row(id="3", place="Kyiv, Kyyiv, Ukraine", cc="UP",
             lat="50.4500", lon="30.5233", mentions=40),
    ]
    _fake_net(monkeypatch, rows)
    E.collect(max_slices=1)

    res = E.points()
    assert res["events"] == 3
    names = [p["name"] for p in res["points"]]
    assert names[0].startswith("Kyiv"), f"ข่าวที่ถูกรายงาน 40 ครั้งต้องมาก่อน: {names}"
    jeru = [p for p in res["points"] if p["name"].startswith("Jerusalem")][0]
    assert jeru["count"] == 2 and jeru["mentions"] == 12


def test_points_shortens_long_place_names(monkeypatch):
    _fake_net(monkeypatch, [_row(place="Sydney, New South Wales, Australia",
                                 lat="-33.8833", lon="151.217")])
    E.collect(max_slices=1)
    assert E.points()["points"][0]["name"] == "Sydney, Australia"


def test_points_filters_by_theme(monkeypatch):
    rows = [
        _row(id="1", root="19", url="https://x.com/border-clash"),
        _row(id="2", root="01", url="https://x.com/oil-prices-surge-opec",
             lat="26.6", lon="56.3", place="Strait Of Hormuz, Iran"),
    ]
    _fake_net(monkeypatch, rows)
    E.collect(max_slices=1)
    assert len(E.points(theme="conflict")["points"]) == 1
    energy = E.points(theme="energy")["points"]
    assert len(energy) == 1 and "Hormuz" in energy[0]["full_name"]


def test_points_never_touches_network(monkeypatch):
    """หน้าเว็บเรียก points() — ห้ามยิงเน็ตเด็ดขาด (ต้องอ่านคลังเท่านั้น)"""
    calls = _fake_net(monkeypatch, [_row()])
    E.collect(max_slices=1)
    before = calls["n"]
    for _ in range(5):
        E.points()
    assert calls["n"] == before, "points() ต้องไม่ยิงเน็ต"


@pytest.mark.parametrize("url,expect_in", [
    ("https://site.com/2026/07/30/oil-prices-surge-after-opec-cut",
     "Oil prices surge after opec cut"),
    ("https://site.com/news/border-clash-kills-three.html",
     "Border clash kills three"),
    ("https://site.com/", "site.com"),          # ถอดไม่ได้ -> ใช้ชื่อเว็บ ไม่แต่งเอง
    ("https://site.com/12345", "site.com"),
])
def test_title_from_url(url, expect_in):
    assert expect_in in E._title_from_url(url)


def test_status_reports_coverage(monkeypatch):
    rows = [_row(id="1", cc="IS"), _row(id="2", cc="UP", lat="50.45", lon="30.52"),
            _row(id="3", cc="US", lat="38.9", lon="-77.0")]
    _fake_net(monkeypatch, rows)
    E.collect(max_slices=1)
    st = E.status()
    assert st["events"] == 3 and st["countries"] == 3
    assert st["source"] == "gdelt-events-2.0"
