"""
ชุดทดสอบสะพานเชื่อม NEBULA ↔ volume-edge (ระบบเทรด MT5 ที่บ้าน)

สิ่งที่ต้องพิสูจน์
---------------
1. ไม่ได้ตั้งค่า -> ปิดเงียบ ไม่พังและไม่ยิงเน็ต
2. เครื่องที่บ้านปิด/ตอบผิดพลาด -> ข้อความไทยที่เข้าใจได้ ไม่ใช่ stack trace
3. ส่งกุญแจไปด้วยทุกครั้ง และเรียกเฉพาะคำสั่งอ่าน (ห้ามมีทางสั่งซื้อขาย)
4. ไม้เปิดต้องถูกต่อยอดด้วยมุมมองข่าวโลกของ NEBULA (จุดที่สองระบบมาบรรจบ)

(ไม่ต้องต่อเน็ต — ปลอมชั้น HTTP ทั้งหมด)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")

from database import init_db  # noqa: E402
from services import volume_edge as VE  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    monkeypatch.setattr(VE, "cache_get", lambda k: None)
    monkeypatch.setattr(VE, "cache_set", lambda k, v, ttl: None)
    yield


def _configure(monkeypatch, url="https://volume.example.com", key="secret123"):
    monkeypatch.setattr(VE.Config, "VE_BASE_URL", url)
    monkeypatch.setattr(VE.Config, "VE_AUTH_KEY", key)


class Resp:
    def __init__(self, code=200, payload=None, bad_json=False):
        self.status_code = code
        self._payload = payload
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._payload


# ---------------------------------------------------------------------------
# 1) ยังไม่ได้ตั้งค่า = ปิดเงียบ ห้ามยิงเน็ต
# ---------------------------------------------------------------------------
def test_disabled_when_not_configured(monkeypatch):
    monkeypatch.setattr(VE.Config, "VE_BASE_URL", "")
    called = {"n": 0}
    monkeypatch.setattr(VE.requests, "get",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1))

    assert VE.configured() is False
    ov = VE.overview()
    assert ov["ok"] is False and ov["configured"] is False and ov.get("error")
    assert called["n"] == 0                  # ต้องไม่ยิงเน็ตเลย


# ---------------------------------------------------------------------------
# 2) ปลายทางมีปัญหา -> ข้อความไทยที่ใช้งานได้ ไม่ใช่ระเบิด
# ---------------------------------------------------------------------------
def test_home_pc_offline_gives_thai_message(monkeypatch):
    _configure(monkeypatch)

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(VE.requests, "get", boom)
    st = VE.status()
    assert st["ok"] is False and st["online"] is False
    assert "เครื่อง" in st["error"]          # บอกเป็นภาษาคน


@pytest.mark.parametrize("code,keyword", [
    (401, "กุญแจ"),
    (403, "ภายนอก"),
    (500, "HTTP 500"),
])
def test_http_errors_are_explained(monkeypatch, code, keyword):
    _configure(monkeypatch)
    monkeypatch.setattr(VE.requests, "get", lambda *a, **k: Resp(code))
    data, err = VE._get("/api/system/status")
    assert data is None and keyword in err


def test_non_json_response_handled(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(VE.requests, "get", lambda *a, **k: Resp(200, bad_json=True))
    data, err = VE._get("/api/system/status")
    assert data is None and "JSON" in err


# ---------------------------------------------------------------------------
# 3) ต้องส่งกุญแจ และเรียกเฉพาะคำสั่งอ่าน
# ---------------------------------------------------------------------------
def test_auth_key_always_sent(monkeypatch):
    _configure(monkeypatch, key="my-secret")
    seen = {}

    def fake_get(url, params=None, timeout=None, headers=None):
        seen["url"] = url
        seen["params"] = params or {}
        return Resp(200, {"ok": 1})

    monkeypatch.setattr(VE.requests, "get", fake_get)
    VE._get("/api/positions", {"a": 1})
    assert seen["params"]["key"] == "my-secret"
    assert seen["url"] == "https://volume.example.com/api/positions"


def test_bridge_is_read_only(monkeypatch):
    """สะพานนี้ต้องไม่มีทางส่งคำสั่งเปลี่ยนแปลง — ห้ามมี requests.post/put/delete"""
    src = open(VE.__file__, encoding="utf-8").read()
    for verb in ("requests.post", "requests.put", "requests.delete", "requests.patch"):
        assert verb not in src, f"พบการเรียก {verb} — สะพานต้องอ่านอย่างเดียว"


def test_base_url_trailing_slash_ok(monkeypatch):
    _configure(monkeypatch, url="https://volume.example.com/")
    seen = {}
    monkeypatch.setattr(VE.requests, "get",
                        lambda url, **k: seen.update(url=url) or Resp(200, {}))
    VE._get("/api/signals")
    assert seen["url"] == "https://volume.example.com/api/signals"   # ไม่มี // ซ้อน


# ---------------------------------------------------------------------------
# 4) จุดที่สองระบบมาบรรจบ: ไม้จริง + ข่าวโลกที่เรียนรู้มา
# ---------------------------------------------------------------------------
def test_positions_enriched_with_news_view(monkeypatch):
    _configure(monkeypatch)
    payload = {
        "positions": [
            {"symbol": "AAPL", "volume": 10, "entry": 200.0, "current": 210.0,
             "profit": 100.0, "setup_code": "VAB", "reason_th": "เบรกขอบบน"},
            {"symbol": "XOM", "volume": 5, "entry": 100.0, "current": 98.0,
             "profit": -10.0, "setup_code": "VAR", "reason_th": "เด้งจากขอบล่าง"},
        ],
        "summary": {"equity": 10000, "currency": "USD"},
        "total_pnl": 90.0,
    }
    monkeypatch.setattr(VE.requests, "get", lambda *a, **k: Resp(200, payload))

    from services import correlation
    monkeypatch.setattr(correlation, "catalyst_signal", lambda t: (
        {"ok": True, "adjust": 4.0, "label": "ข่าวโลกหนุน",
         "reasons": [{"text": "ข่าวเทคดีขึ้น → หนุน AAPL"}]}
        if t == "AAPL" else
        {"ok": False, "adjust": 0, "hint": "ยังไม่ได้เรียนรู้หุ้นตัวนี้", "reasons": []}))

    res = VE.positions()
    assert res["ok"] and res["count"] == 2
    a, x = res["positions"]
    assert a["news"]["learned"] is True and a["news"]["adjust"] == 4.0
    assert "หนุน" in a["news"]["reasons"][0]
    assert x["news"]["learned"] is False            # ตัวที่ยังไม่เรียนรู้ต้องบอกตรง ๆ
    assert x["news"]["adjust"] == 0                 # ไม่เดาคะแนนให้


def test_catalyst_failure_does_not_break_positions(monkeypatch):
    """เครื่องเรียนรู้ล้ม ต้องไม่ทำให้ไม้จริงหายไปจากหน้าจอ"""
    _configure(monkeypatch)
    monkeypatch.setattr(VE.requests, "get", lambda *a, **k: Resp(
        200, {"positions": [{"symbol": "AAPL", "profit": 1.0}], "summary": {}}))

    from services import correlation

    def boom(t):
        raise RuntimeError("db down")

    monkeypatch.setattr(correlation, "catalyst_signal", boom)
    res = VE.positions()
    assert res["ok"] and len(res["positions"]) == 1
    assert "news" not in res["positions"][0]        # ไม่มีข้อมูลก็ไม่ใส่ ไม่ใช่ใส่ค่าปลอม


def test_overview_reports_offline_without_crashing(monkeypatch):
    _configure(monkeypatch)

    def boom(*a, **k):
        raise OSError("down")

    monkeypatch.setattr(VE.requests, "get", boom)
    ov = VE.overview()
    assert ov["configured"] is True and ov["ok"] is False
    assert ov["status"]["online"] is False
    assert ov["positions"]["positions"] == []       # โครงสร้างครบ หน้าเว็บวาดได้ไม่พัง
