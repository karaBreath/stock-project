"""
ทดสอบการสร้างไอคอนบนหน้าจอ Windows

จุดที่พลาดแล้วผู้ใช้จะคิดว่า "โปรแกรมไม่ทำงาน":
  1. เดาว่าหน้าจออยู่ที่ %USERPROFILE%\\Desktop เสมอ — เครื่องที่เปิด OneDrive
     หน้าจอย้ายไปอยู่ใต้ OneDrive ไอคอนจะไปโผล่ในที่ที่มองไม่เห็น
  2. ไฟล์ .ico ผิดรูป — Windows จะไม่แสดงรูป กลายเป็นไอคอนขาว
  3. ชื่อไฟล์/พาธมีเครื่องหมายพิเศษแล้วคำสั่ง PowerShell พัง
"""
import os
import re
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

    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "ps_run", lambda ps, **kw: (
        seen.update(ps=ps), (0, "C:\\Users\\arm\\OneDrive\\Desktop\n", ""))[1])
    got = D.desktop_dir()
    assert "GetFolderPath" in seen["ps"]
    assert "OneDrive" in str(got)


def test_falls_back_to_home_desktop_if_windows_does_not_answer(monkeypatch):
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "ps_run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no ps")))
    assert str(D.desktop_dir()).endswith("Desktop")


# ---------------------------------------------------------------------------
# 2.5) อ่านผลจาก PowerShell โดยไม่พังเรื่อง encoding
#
# บั๊กจริงที่ CI ของ Windows จับได้:
#   subprocess.run(..., text=True) ถอดรหัสด้วย code page ของเครื่อง (cp1252)
#   พอเจอไบต์ 0x81 ที่ code page ไม่รู้จัก เธรดอ่านผลตายทั้งเธรด
#   ผลลัพธ์เป็นค่าว่าง แล้วโปรแกรมสรุปว่า "สร้างไอคอนไม่สำเร็จ"
#   ผู้ใช้เห็นแค่ว่ากดแล้วไม่มีอะไรเกิดขึ้น
# ---------------------------------------------------------------------------
def test_survives_output_the_windows_code_page_cannot_decode(monkeypatch):
    class R:
        returncode = 0
        stdout = b"C:\\Users\\\x81\x9d\\Desktop"   # ไบต์ที่ cp1252 ถอดไม่ได้
        stderr = b""

    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    code, out, err = D.ps_run("whatever")          # ต้องไม่โยน
    assert code == 0 and "Desktop" in out


def test_never_hands_decoding_to_the_locale_code_page(monkeypatch):
    """
    ถ้าเผลอใส่ text=True กลับเข้ามาอีก บั๊กเดิมจะกลับมาทันที
    ต้องรับเป็นไบต์แล้วถอดเป็น UTF-8 เองเสมอ
    """
    seen = {}

    class R:
        returncode = 0
        stdout = b""
        stderr = b""

    monkeypatch.setattr(D.subprocess, "run",
                        lambda cmd, **kw: (seen.update(kw=kw, cmd=cmd), R())[1])
    D.ps_run("x")
    assert not seen["kw"].get("text"), "ห้ามใช้ text=True กับ PowerShell"
    assert seen["kw"].get("capture_output") is True


def test_sends_the_script_as_a_utf8_bom_file_not_on_the_command_line(monkeypatch):
    """
    บั๊กจริงจาก CI ของ Windows: ชื่อ "เทรดข่าวโลก" ที่ส่งผ่าน -Command
    กลายเป็น "???????????" ทั้งหมด แล้ว Windows ปฏิเสธการบันทึกไฟล์
    ขึ้นว่า "Unable to save shortcut" — ไอคอนจึงไม่เกิดขึ้นเลย

    ต้องเขียนลงไฟล์ .ps1 ที่มี BOM แล้วใช้ -File เท่านั้น
    (PowerShell 5.1 อ่านไฟล์ที่ไม่มี BOM เป็น ANSI ตัวอักษรไทยจะเพี้ยนอีกแบบ)
    """
    seen = {}

    class R:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        path = cmd[cmd.index("-File") + 1]
        seen["raw"] = open(path, "rb").read()
        return R()

    monkeypatch.setattr(D.subprocess, "run", fake_run)
    D.ps_run(f"$name = '{D.APP_NAME}'")

    assert "-File" in seen["cmd"], "ต้องใช้ -File ไม่ใช่ -Command"
    assert "-Command" not in seen["cmd"]
    assert seen["raw"].startswith(b"\xef\xbb\xbf"), "ไฟล์ต้องมี UTF-8 BOM"
    assert D.APP_NAME.encode("utf-8") in seen["raw"], \
        "ชื่อภาษาไทยต้องอยู่ในไฟล์ครบ ไม่ถูกแปลงเป็น ?"
    assert b"OutputEncoding" in seen["raw"]


def test_cleans_up_its_temp_script(monkeypatch):
    """ไม่งั้นโฟลเดอร์ temp จะมีขยะเพิ่มทุกครั้งที่กดปุ่ม"""
    seen = {}

    class R:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, **kw):
        seen["path"] = cmd[cmd.index("-File") + 1]
        return R()

    monkeypatch.setattr(D.subprocess, "run", fake_run)
    D.ps_run("x")
    assert not os.path.exists(seen["path"])


def test_reports_the_real_powershell_error_not_a_blank_one(monkeypatch, tmp_path):
    """
    เวลาพัง ต้องได้ข้อความจริงจาก PowerShell ไม่ใช่ประโยคกว้าง ๆ
    ไม่งั้นแก้ปัญหาต่อไม่ได้เลย
    """
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "ensure_icon", lambda: tmp_path / "app.ico")

    class R:
        returncode = 1
        stdout = "FAILED: The system cannot find the path specified.".encode()
        stderr = b""

    monkeypatch.setattr(D.subprocess, "run", lambda *a, **k: R())
    res = D.create_shortcut()
    assert res["ok"] is False
    assert "cannot find the path" in res["error"]


def test_shortcut_script_reports_failures_instead_of_dying_silently():
    ps = D.shortcut_script(__import__("pathlib").Path("a.lnk"),
                           __import__("pathlib").Path("p.exe"), '"g.py"',
                           __import__("pathlib").Path("."),
                           __import__("pathlib").Path("i.ico"))
    assert D.APP_NAME not in ps.split("Description")[1][:80], (
        "คำอธิบายต้องไม่เป็นภาษาไทย — COM แปลงเป็น ANSI แล้วได้ ??? "
        "ซึ่งผู้ใช้เห็นตอนเอาเมาส์ไปชี้แล้วนึกว่าไฟล์เสีย")
    assert D.APP_DESCRIPTION in ps and D.APP_DESCRIPTION.isascii()
    assert "try {" in ps and "catch" in ps
    assert "FAILED" in ps and "SAVED" in ps
    assert "exit 1" in ps, "ต้องคืน exit code ที่ไม่ใช่ 0 เวลาพัง"


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
    """
    PowerShell บันทึกด้วยชื่ออังกฤษก่อน แล้ว Python เปลี่ยนชื่อเป็นไทย
    ผลสุดท้ายที่ผู้ใช้เห็นบนหน้าจอต้องเป็นภาษาไทยเท่านั้น
    """
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "ensure_icon", lambda: tmp_path / "app.ico")

    class R:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, **kw):
        (tmp_path / D.STAGING_NAME).write_text("x")   # ทำเหมือน PowerShell จริง
        return R()

    monkeypatch.setattr(D.subprocess, "run", fake_run)
    res = D.create_shortcut()
    assert res["ok"] and res["name"] == "เทรดข่าวโลก"
    assert res["path"].endswith("เทรดข่าวโลก.lnk")
    assert (tmp_path / "เทรดข่าวโลก.lnk").exists()
    assert not (tmp_path / D.STAGING_NAME).exists(), "ต้องไม่เหลือไฟล์ชั่วคราวค้าง"


def test_never_asks_powershell_to_write_a_thai_filename(tmp_path, monkeypatch):
    """
    บั๊กจริงจาก windows-latest:
      FAILED: Unable to save shortcut "C:\\Users\\...\\???????????.lnk"

    WScript.Shell แปลงพาธเป็น ANSI ก่อนบันทึก เครื่องที่ระบบไม่ใช่ภาษาไทย
    จึงบันทึกไม่ได้เลย ชื่อที่ส่งให้ PowerShell ต้องเป็น ASCII เสมอ
    """
    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "desktop_dir", lambda: tmp_path)
    monkeypatch.setattr(D, "ensure_icon", lambda: tmp_path / "app.ico")
    seen = {}

    class R:
        returncode = 0
        stdout = b""
        stderr = b""

    def fake_run(cmd, **kw):
        seen["script"] = open(cmd[cmd.index("-File") + 1], "rb").read()
        (tmp_path / D.STAGING_NAME).write_text("x")
        return R()

    monkeypatch.setattr(D.subprocess, "run", fake_run)
    D.create_shortcut()

    script = seen["script"].decode("utf-8-sig")
    saved_path = re.search(r"CreateShortcut\('([^']+)'\)", script).group(1)
    assert saved_path.isascii(), f"พาธที่ส่งให้ PowerShell ต้องเป็น ASCII: {saved_path}"
    assert saved_path.endswith(D.STAGING_NAME)


def test_uses_the_short_ascii_path_when_the_username_is_thai(monkeypatch, tmp_path):
    """
    ถ้าชื่อผู้ใช้เป็นภาษาไทย แม้แต่โฟลเดอร์ปลายทางก็เขียนเป็น ANSI ไม่ได้
    ต้องขอชื่อพาธแบบสั้น (8.3) จาก Windows ซึ่งเป็น ASCII เสมอ
    """
    thai_desk = tmp_path / "ผู้ใช้" / "Desktop"
    thai_desk.mkdir(parents=True)
    short = tmp_path / "SHORT"
    short.mkdir()

    monkeypatch.setattr(D, "IS_WIN", True)
    monkeypatch.setattr(D, "desktop_dir", lambda: thai_desk)
    monkeypatch.setattr(D, "ensure_icon", lambda: tmp_path / "app.ico")
    monkeypatch.setattr(D, "ansi_safe", lambda s: s.isascii())
    monkeypatch.setattr(D, "short_path", lambda p: short)

    class R:
        returncode = 0
        stdout = b""
        stderr = b""

    monkeypatch.setattr(D.subprocess, "run",
                        lambda *a, **k: ((short / D.STAGING_NAME).write_text("x"),
                                         R())[1])
    res = D.create_shortcut()
    assert res["ok"], res.get("error")
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
