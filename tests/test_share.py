"""
ทดสอบตัวเปิดเว็บออกอินเทอร์เน็ตผ่าน Cloudflare Tunnel (share.py)

จุดที่พลาดแล้วอันตราย และเทสชุดนี้ล็อกไว้:
  - ลืมสร้างกุญแจ / สร้างกุญแจที่เดาง่าย -> พอร์ตกับ MT5 เปิดโล่งบนเน็ต
  - เขียนกุญแจทับของเดิมทุกครั้ง -> ลิงก์ที่เคยส่งไว้ใช้ไม่ได้
  - กุญแจหลุดขึ้น git
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import share  # noqa: E402


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("PORT=5000\nLEARN_AUTO=1\n", encoding="utf-8")
    monkeypatch.setattr(share, "ENV_FILE", f)
    return f


# ---------------------------------------------------------------------------
# กุญแจ
# ---------------------------------------------------------------------------
def test_creates_a_strong_key_when_missing(env_file):
    token = share.ensure_token(disabled=False)
    assert len(token) >= 24, "กุญแจต้องยาวพอจนเดาไม่ได้"
    assert f"SHARE_TOKEN={token}" in env_file.read_text(encoding="utf-8")


def test_keeps_the_same_key_on_next_run(env_file):
    """กุญแจต้องคงเดิม ไม่งั้นลิงก์ที่ส่งไว้ในมือถือจะใช้ไม่ได้ทุกครั้งที่เปิดใหม่"""
    first = share.ensure_token(disabled=False)
    second = share.ensure_token(disabled=False)
    assert first == second
    assert env_file.read_text(encoding="utf-8").count("SHARE_TOKEN=") == 1


def test_two_runs_never_produce_the_same_key(tmp_path, monkeypatch):
    """เครื่องคนละเครื่องต้องไม่ได้กุญแจเดียวกัน (ไม่ใช่ค่าคงที่ใน source)"""
    keys = set()
    for i in range(3):
        f = tmp_path / f"env{i}"
        f.write_text("", encoding="utf-8")
        monkeypatch.setattr(share, "ENV_FILE", f)
        keys.add(share.ensure_token(disabled=False))
    assert len(keys) == 3


def test_no_lock_flag_returns_empty_and_writes_nothing(env_file):
    assert share.ensure_token(disabled=True) == ""
    assert "SHARE_TOKEN" not in env_file.read_text(encoding="utf-8")


def test_key_lives_only_in_env_which_git_ignores():
    """.env ต้องอยู่ใน .gitignore ไม่งั้นกุญแจหลุดขึ้น GitHub"""
    ignore = (share.BASE / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignore


def test_reads_port_from_env(env_file):
    env_file.write_text("PORT=5123\n", encoding="utf-8")
    assert share.read_env().get("PORT") == "5123"


def test_env_parser_ignores_comments(env_file):
    env_file.write_text("# SHARE_TOKEN=ของปลอม\nPORT=5000\n", encoding="utf-8")
    assert "SHARE_TOKEN" not in share.read_env()


# ---------------------------------------------------------------------------
# อ่านลิงก์จาก cloudflared
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("line,expect", [
    ("2026-07-30T16:00:00Z INF |  https://brave-dog-42.trycloudflare.com  |",
     "https://brave-dog-42.trycloudflare.com"),
    ("INF Your quick Tunnel has been created! Visit it at "
     "https://a-b-c-1.trycloudflare.com", "https://a-b-c-1.trycloudflare.com"),
])
def test_finds_the_public_link_in_cloudflared_output(line, expect):
    m = share.URL_RE.search(line)
    assert m and m.group(0) == expect


def test_ignores_lines_without_a_link():
    assert share.URL_RE.search("INF Starting tunnel connection") is None


# ---------------------------------------------------------------------------
# คำสั่งที่ยิงออกไป
# ---------------------------------------------------------------------------
def test_quick_tunnel_points_at_the_local_app(monkeypatch):
    seen = {}

    class FakeProc:
        stdout = iter([])
        def poll(self): return None

    def fake_popen(cmd, **kw):
        seen["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(share.subprocess, "Popen", fake_popen)
    share.run_tunnel("cloudflared", 5000, "", lambda u: None)
    assert seen["cmd"] == ["cloudflared", "tunnel", "--url",
                           "http://127.0.0.1:5000"]


def test_named_tunnel_uses_the_given_name(monkeypatch):
    seen = {}

    class FakeProc:
        stdout = iter([])
        def poll(self): return None

    monkeypatch.setattr(share.subprocess, "Popen",
                        lambda cmd, **kw: (seen.__setitem__("cmd", cmd), FakeProc())[1])
    share.run_tunnel("cloudflared", 5000, "nebula", lambda u: None)
    assert seen["cmd"][:3] == ["cloudflared", "tunnel", "run"]
    assert seen["cmd"][-1] == "nebula"


def test_app_is_started_with_the_key_so_the_lock_is_on(monkeypatch):
    """
    แอปต้องได้รับกุญแจตอนเปิด ไม่งั้น tunnel จะเปิดเว็บที่ไม่ล็อกออกเน็ต
    ซึ่งเป็นความผิดพลาดที่อันตรายที่สุดของฟีเจอร์นี้
    """
    seen = {}
    monkeypatch.setattr(share.subprocess, "Popen",
                        lambda cmd, env=None, **kw: seen.update(cmd=cmd, env=env))
    share.start_app(5000, "my-secret-key")
    assert seen["env"]["SHARE_TOKEN"] == "my-secret-key"
    assert seen["env"]["PORT"] == "5000"


def test_link_shown_to_the_user_contains_the_key(capsys):
    share.banner("https://x.trycloudflare.com", "KEY123", 5000)
    out = capsys.readouterr().out
    assert "https://x.trycloudflare.com/?k=KEY123" in out
    assert "ห้ามส่งลิงก์นี้ให้ใคร" in out


def test_warns_loudly_when_lock_is_disabled(capsys):
    share.banner("https://x.trycloudflare.com", "", 5000)
    out = capsys.readouterr().out
    assert "ไม่ล็อกกุญแจ" in out


# ---------------------------------------------------------------------------
# บั๊กที่เจอตอนเปิดใช้จริง: พอร์ตชนกัน
# ---------------------------------------------------------------------------
class DeadProc:
    """process ที่ตายไปแล้ว (เช่นเปิดไม่ขึ้นเพราะ Address already in use)"""
    def poll(self): return 1


class LiveProc:
    def poll(self): return None


def test_dead_app_is_not_mistaken_for_ready(monkeypatch):
    """
    เจอจริง: มีแอปเก่าค้างที่พอร์ตเดิม ตัวใหม่จึงเปิดไม่ขึ้น แต่ /health ยังตอบ 200
    เพราะเป็นของตัวเก่า ระบบเลยบอก "แอปพร้อมแล้ว" แล้วเปิด tunnel ต่อ
    อันตราย เพราะตัวเก่าอาจไม่ได้ล็อกกุญแจ = เปิดพอร์ตกับ MT5 ให้คนอื่นดู
    """
    monkeypatch.setattr(share.time, "sleep", lambda s: None)
    monkeypatch.setattr(share.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError(
                            "ตายแล้วต้องเลิกทันที ไม่ต้องไปถาม /health")))
    assert share.wait_until_up(5000, DeadProc(), seconds=3) is False


def test_ready_only_when_our_own_process_is_alive(monkeypatch):
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(share.time, "sleep", lambda s: None)
    monkeypatch.setattr(share.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert share.wait_until_up(5000, LiveProc(), seconds=3) is True


def test_gives_up_when_health_never_answers(monkeypatch):
    monkeypatch.setattr(share.time, "sleep", lambda s: None)
    monkeypatch.setattr(share.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    assert share.wait_until_up(5000, LiveProc(), seconds=3) is False
