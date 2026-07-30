"""
กติกากลางของชุดทดสอบ: **เทสห้ามแตะอินเทอร์เน็ตเด็ดขาด**

ทำไมต้องมีไฟล์นี้ (เจอจริงบน CI ไม่ได้คิดเผื่อไว้ล่วงหน้า)
---------------------------------------------------------
เทสชุดลูกโลกผ่านหมดในเครื่องที่ไม่มีเน็ต แต่ตกบน GitHub Actions ที่มีเน็ต
สาเหตุ: การเปิดหน้าลูกโลกจะ "ปลุกเธรดเก็บข่าวเบื้องหลัง" ซึ่งบน CI วิ่งไป
ดาวน์โหลดข่าวจริงจาก GDELT เข้าฐานข้อมูลระหว่างที่เทสตัวอื่นกำลังรันอยู่
เทสที่ตั้งใจตรวจ "กรณีไม่มีข้อมูลเลย" จึงเจอข้อมูลจริงโผล่มา แล้วตกแบบสุ่ม

บทเรียน: เทสที่ผลลัพธ์ขึ้นกับเน็ต = เทสที่เชื่อไม่ได้ ไม่ว่าจะเขียวหรือแดง
ไฟล์นี้จึงตัดขาการต่อเน็ตจริงทั้งหมดออก แล้วบังคับให้ทุกเทสปลอม HTTP เอง
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LEARN_AUTO", "0")
os.environ.setdefault("DB_PATH", "/tmp/nebula_test.db")


class NetworkUsedInTest(RuntimeError):
    """เทสพยายามต่อเน็ตจริง — ให้ดังตรงนั้นเลย จะได้รู้ว่าลืมปลอมชั้น HTTP"""


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """
    ปิดทางออกเน็ตจริงทุกทาง (requests + urllib + socket)

    เทสที่ต้องการจำลอง HTTP ให้ปลอมที่ระดับฟังก์ชันของ service เอง
    เช่น monkeypatch ที่ gdelt._fetch_json หรือ gdelt_events._session
    ซึ่งไม่ถูกกติกานี้ขวาง เพราะไม่ได้เรียกของจริง
    """
    def boom(*a, **k):
        raise NetworkUsedInTest(
            "เทสนี้พยายามต่อเน็ตจริง — ต้องปลอมชั้น HTTP ก่อน "
            "(ดู tests/conftest.py ว่าทำไมถึงห้าม)")

    try:
        import requests
        monkeypatch.setattr(requests.sessions.Session, "request", boom)
        for name in ("get", "post", "put", "delete", "head", "patch", "request"):
            if hasattr(requests, name):
                monkeypatch.setattr(requests, name, boom)
    except ImportError:                                   # pragma: no cover
        pass

    import socket
    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    yield


@pytest.fixture(autouse=True)
def _no_background_filler(monkeypatch):
    """
    ห้ามเทสปลุกเธรดเก็บข่าวเบื้องหลัง

    เธรดนั้นเขียนฐานข้อมูลไปเรื่อย ๆ ขนานกับเทสตัวอื่น ผลเทสจึงขึ้นกับจังหวะ
    เทสที่ต้องการตรวจพฤติกรรมการปลุกเธรด จะ monkeypatch ทับเองอยู่แล้ว
    """
    try:
        from services import gdelt
        monkeypatch.setattr(gdelt, "ensure_filling", lambda: False)
    except ImportError:                                   # pragma: no cover
        pass
    yield
