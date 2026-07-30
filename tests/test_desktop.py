"""
ทดสอบการสร้างไอคอนบนหน้าจอ Windows

จุดที่พลาดแล้วผู้ใช้จะคิดว่า "โปรแกรมไม่ทำงาน":
  1. เดาว่าหน้าจออยู่ที่ %USERPROFILE%\\Desktop เสมอ — เครื่องที่เปิด OneDrive
     หน้าจอย้ายไปอยู่ใต้ OneDrive ไอคอนจะไปโผล่ในที่ที่มองไม่เห็น
  2. ไฟล์ .ico ผิดรูป — Windows จะไม่แสดงรูป กลายเป็นไอคอนขาว
  3. ชื่อไฟล์/พาธมีเครื่องหมายพิเศษแล้วคำสั่ง PowerShell พัง
"""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import desktop as D  # noqa: E402


# ---------------------------------------------------------------------------
# 1) ไฟล์ไอคอน
# ---------------------------------------------------------------------------
def test_ico_header_is_valid_so_windows_can_read_it():
    png = D.ICON_SOURCE.read_bytes()
    ico = D.ico_from_png(png)

    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind, count) == (0, 1, 1), "หัวไฟล์ .ico ต้องถูกตามสเปค"

    w, h, colors, _res, planes, bpp, size, offset = struct.unpack("<BBBBHHII",
                                                                  ico[6:22])
    assert (w, h) == (192, 192)
    assert (planes, bpp) == (1, 32)
    assert size == len(png)
    assert offset == 22
    assert ico[offset:offset + 8] == b"\x89PNG\r\n\x1a\n", "ข้อมูลรูปต้องต่อจากหัวพอดี"


def test_ico_embeds_the_same_icon_the_app_uses():
    """ไอคอนบนหน้าจอกับในเว็บควรเป็นรูปเดียวกัน ไม่งั้นดูเหมือนคนละโปรแกรม"""
    png = D.ICON_SOURCE.read_bytes()
    assert D.ico_from_png(png).endswith(png)


def test_rejects_a_file_that_is_not_png():
    with pytest.raises(ValueError):
        D.ico_from_png(b"not a png at all")


def test_rejects_oversized_icons():
    """.ico เก็บได้ไม่เกิน 256 พิกเซล ถ้าปล่อยผ่านจะได้ไฟล์เสียที่ Windows ไม่อ่าน"""
    fake = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 512, 512)
    with pytest.raises(ValueError):
        D.ico_from_png(fake)


def test_ensure_icon_writes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ICON_PATH", tmp_path / "app.ico")
    p = D.ensure_icon()
    assert p.exists() and p.stat().st_size > 1000


def test_ensure_icon_does_not_rewrite_every_time(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ICON_PATH", tmp_path / "app.ico")
    first = D.ensure_icon()
    stamp = first.stat().st_mtime_ns
    assert D.ensure_icon().stat().st_mtime_ns == stamp


# ---------------------------------------------------------------------------
# 2) หาโฟลเดอร์หน้าจอ
# ---------------------------------------------------------------------------
def test_asks_windows_where_the_desktop_really_is(monkeypatch):
    """
    ต้องถาม Windows ไม่ใช่เดา — เครื่องที่เปิด OneDrive หน้าจอย้ายที่
    ถ้าเดาผิด ไอคอนจะไปอยู่ในโฟลเดอร์ที่ผู้ใช้มองไม่เห็น
    """
    seen = {}

    class R:
        stdout = "C:\\Users\\arm\\OneDrive\\Desktop\n"

    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D.subprocess, "run",
                        lambda cmd, **kw: (seen.update(cmd=cmd), R())[1])
    got = D.desktop_dir()
    assert "GetFolderPath" in " ".join(seen["cmd"])
    assert "OneDrive" in str(got)


def test_falls_back_to_home_desktop_if_windows_does_not_answer(monkeypatch):
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no ps")))
    assert str(D.desktop_dir()).endswith("Desktop")


# ---------------------------------------------------------------------------
# 3) คำสั่งสร้างทางลัด
# ---------------------------------------------------------------------------
def test_shortcut_command_has_every_field_windows_needs(tmp_path):
    cmd = D.shortcut_command(tmp_path / "เทรดข่าวโลก.lnk",
                             tmp_path / "pythonw.exe", '"gui.py"',
                             tmp_path, tmp_path / "app.ico")
    joined = " ".join(cmd)
    assert cmd[0] == "powershell"
    for field in ("TargetPath", "Arguments", "WorkingDirectory",
                  "IconLocation", "Save()"):
        assert field in joined, f"ขาด {field}"


def test_quotes_are_escaped_so_odd_paths_do_not_break_powershell():
    """ชื่อผู้ใช้ที่มีเครื่องหมาย ' อยู่ (เช่น O'Brien) ต้องไม่ทำให้คำสั่งพัง"""
    out = D._ps_quote("C:\\Users\\O'Brien\\Desktop")
    assert out == "'C:\\Users\\O''Brien\\Desktop'"


def test_shortcut_is_named_in_thai_as_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "ensure_icon", lambda: tmp_path / "app.ico")
    seen = {}

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        (tmp_path / f"{D.APP_NAME}.lnk").write_text("x")
        return R()

    monkeypatch.setattr(D.subprocess, "run", fake_run)
    res = D.create_shortcut()
    assert res["ok"] and res["name"] == "เทรดข่าวโลก"
    assert res["path"].endswith("เทรดข่าวโลก.lnk")


def test_prefers_pythonw_so_no_black_window_pops_up(monkeypatch, tmp_path):
    """
    ต้องใช้ pythonw ถ้ามี ไม่งั้นจะมีหน้าต่างดำเด้งคู่กับหน้าต่างโปรแกรมทุกครั้ง
    ซึ่งเป็นสิ่งที่ผู้ใช้บ่นมาตั้งแต่แรก
    """
    fake_venv = tmp_path / "venv" / "Scripts"
    fake_venv.mkdir(parents=True)
    (fake_venv / "pythonw.exe").write_text("")
    monkeypatch.setattr(D, "BASE", tmp_path)
    target, quiet = D.python_target()
    assert quiet is True and target.name == "pythonw.exe"


def test_reports_failure_clearly_instead_of_pretending_it_worked(monkeypatch, tmp_path):
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "ensure_icon", lambda: tmp_path / "app.ico")

    class R:
        returncode = 1
        stdout = ""
        stderr = "Access is denied"

    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    res = D.create_shortcut()
    assert res["ok"] is False and "denied" in res["error"]


def test_says_so_on_non_windows_rather_than_failing_silently(monkeypatch):
    monkeypatch.setattr(D, "IS_WIN", False)
    res = D.create_shortcut()
    assert res["ok"] is False and "Windows" in res["error"]
