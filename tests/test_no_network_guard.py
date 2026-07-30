"""
เทสของ "ตัวกันเน็ต" เอง — ถ้ากติกานี้พังเงียบ ๆ เทสทั้งชุดจะเชื่อไม่ได้

เจอจริงบน CI: เทสลูกโลกผ่านในเครื่องที่ไม่มีเน็ต แต่ตกบน GitHub Actions
เพราะเธรดเบื้องหลังไปโหลดข่าวจริงมาแทรกระหว่างรัน ผลเทสจึงขึ้นกับเน็ต
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import NetworkUsedInTest  # noqa: E402


def test_requests_get_is_blocked():
    import requests
    with pytest.raises(NetworkUsedInTest):
        requests.get("https://example.com", timeout=1)


def test_session_request_is_blocked():
    import requests
    with pytest.raises(NetworkUsedInTest):
        requests.Session().get("https://example.com", timeout=1)


def test_raw_socket_is_blocked():
    import socket
    with pytest.raises(NetworkUsedInTest):
        socket.create_connection(("example.com", 80), timeout=1)


def test_background_filler_never_starts_during_tests():
    """เธรดเก็บข่าวต้องไม่ถูกปลุกโดยอัตโนมัติ (ไม่งั้นเทสอื่นเจอข้อมูลแทรก)"""
    from services import gdelt
    assert gdelt.ensure_filling() is False
    assert not any(t.name == "gdelt-filler" for t in __import__("threading").enumerate())
