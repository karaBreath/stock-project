"""
ทดสอบตัวกันคนแปลกหน้าตอนเปิดเว็บออกเน็ตผ่าน Cloudflare Tunnel

ความเสี่ยงจริงที่ต้องกัน: เปิด tunnel แล้วใครได้ลิงก์ไปจะเห็นพอร์ตหุ้น
ไม้ที่ถืออยู่ใน MT5 และยอดเงินในบัญชีทันที เทสชุดนี้ล็อกไว้ว่า
"ไม่มีกุญแจ = ไม่เห็นข้อมูลอะไรเลย" และกันประตูหลังที่พลาดกันบ่อย
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")

from config import Config  # noqa: E402
from services import access_guard  # noqa: E402

KEY = "test-key-abcdef123456"


@pytest.fixture
def client(monkeypatch):
    """แอปที่ล็อกกุญแจไว้ + จำลองว่าคำขอมาจากอินเทอร์เน็ต (ไม่ใช่ localhost)"""
    monkeypatch.setattr(Config, "SHARE_TOKEN", KEY)
    monkeypatch.setattr(Config, "LEARN_AUTO", False)
    import app as app_module
    flask_app = app_module.create_app()
    flask_app.config["SERVER_NAME"] = None
    c = flask_app.test_client()
    c.environ_base["REMOTE_ADDR"] = "203.0.113.9"        # ไอพีจากข้างนอก
    return c


@pytest.fixture
def local_client(monkeypatch):
    """คำขอจากเครื่องเดียวกัน — ต้องใช้งานได้ตามปกติโดยไม่ต้องใส่กุญแจ"""
    monkeypatch.setattr(Config, "SHARE_TOKEN", KEY)
    monkeypatch.setattr(Config, "LEARN_AUTO", False)
    import app as app_module
    c = app_module.create_app().test_client()
    c.environ_base["REMOTE_ADDR"] = "127.0.0.1"
    return c


# ---------------------------------------------------------------------------
# 1) ไม่มีกุญแจ = ไม่เห็นข้อมูล
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/", "/api/portfolio", "/api/mt5/overview", "/api/world/points",
    "/api/learn/status", "/api/watchlist",
])
def test_outsider_without_key_is_blocked(client, path):
    r = client.get(path)
    assert r.status_code == 401, f"{path} ต้องถูกบล็อก แต่ได้ {r.status_code}"
    body = r.get_data(as_text=True)
    assert "กุญแจ" in body


def test_blocked_page_leaks_nothing(client):
    """หน้าที่บล็อกต้องไม่หลุดข้อมูลอะไรออกไป แม้แต่ชื่อหุ้นที่ถืออยู่"""
    body = client.get("/api/portfolio").get_data(as_text=True)
    for leak in ("ticker", "shares", "balance", "equity", "profit"):
        assert leak not in body.lower()


# ---------------------------------------------------------------------------
# 2) มีกุญแจถูก = ผ่าน และไม่ต้องใส่ซ้ำ
# ---------------------------------------------------------------------------
def test_key_in_url_sets_cookie_and_redirects_to_clean_url(client):
    r = client.get(f"/?k={KEY}")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")
    assert "nebula_key" in r.headers.get("Set-Cookie", "")
    # กุญแจต้องไม่ค้างอยู่ใน URL ปลายทาง (กันหลุดทาง Referer/ประวัติ)
    assert "k=" not in r.headers["Location"]


def test_cookie_alone_is_enough_afterwards(client):
    client.get(f"/?k={KEY}")
    assert client.get("/").status_code == 200


def test_header_key_works_for_api_clients(client):
    r = client.get("/api/world/themes", headers={"X-Nebula-Key": KEY})
    assert r.status_code == 200


def test_wrong_key_is_rejected(client):
    assert client.get("/?k=wrong-key").status_code == 401
    assert client.get("/", headers={"X-Nebula-Key": "wrong"}).status_code == 401


def test_cookie_is_httponly_so_scripts_cannot_steal_it(client):
    cookie = client.get(f"/?k={KEY}").headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie


# ---------------------------------------------------------------------------
# 3) ประตูหลังที่พลาดกันบ่อย — ต้องปิดให้สนิท
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP",
                                    "CF-Connecting-IP", "X-Client-IP"])
def test_spoofed_local_ip_headers_do_not_grant_access(client, header):
    """
    cloudflared ใส่ header บอกไอพีต้นทางมาจากอินเทอร์เน็ต ใครก็ปลอมได้
    ถ้าเราเชื่อ header พวกนี้ = เปิดประตูหลังทิ้งไว้ ต้องดู remote_addr เท่านั้น
    """
    r = client.get("/api/portfolio", headers={header: "127.0.0.1"})
    assert r.status_code == 401, f"ปลอม {header} ไม่ควรผ่านได้"


def test_local_machine_never_needs_a_key(local_client):
    """เจ้าของเครื่องต้องใช้งานได้เหมือนเดิม ไม่ต้องพิมพ์กุญแจทุกครั้ง"""
    assert local_client.get("/").status_code == 200
    assert local_client.get("/api/world/themes").status_code == 200


def test_health_stays_open_for_monitoring(client):
    """ตัวตรวจสุขภาพต้องเรียกได้ และต้องไม่มีข้อมูลลับอยู่ในนั้น"""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_static_files_open_so_the_login_page_renders(client):
    for path in ["/static/css/style.css", "/sw.js"]:
        assert access_guard._is_open_path(path) is True


def test_no_token_means_no_lock_at_all(monkeypatch):
    """ใช้ในเครื่องตัวเองโดยไม่ตั้งกุญแจ ต้องไม่มีอะไรเปลี่ยน"""
    monkeypatch.setattr(Config, "SHARE_TOKEN", "")
    monkeypatch.setattr(Config, "LEARN_AUTO", False)
    import app as app_module
    c = app_module.create_app().test_client()
    c.environ_base["REMOTE_ADDR"] = "203.0.113.9"
    assert c.get("/").status_code == 200
