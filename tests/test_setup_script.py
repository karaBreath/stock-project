"""
ทดสอบตัวติดตั้งบรรทัดเดียว (setup.ps1)

ไฟล์นี้ถูกดึงผ่านเน็ตแล้วรันทันที (irm ... | iex) จึงไม่มีใครเปิดอ่านก่อน
ถ้าพังจะพังแบบเงียบ ๆ ที่เครื่องผู้ใช้ ตรวจสามเรื่องที่พังแล้วไม่รู้ตัว:

  1. ไฟล์ต้องเป็น ASCII ล้วน — คอนโซล Windows ใช้ code page 874/437
     ข้อความไทยจะกลายเป็นกล่องสี่เหลี่ยม ดูเหมือนโปรแกรมพัง
  2. พาธที่อ้างถึงต้องมีอยู่จริง — พิมพ์ชื่อไฟล์ผิดตัวเดียวก็เปิดไม่ขึ้น
  3. ต้องไม่ลบงานของผู้ใช้ทิ้ง (ห้าม reset --hard / clean -fd)
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = os.path.join(BASE, "setup.ps1")


@pytest.fixture(scope="module")
def script():
    with open(SETUP, "rb") as f:
        return f.read()


def test_setup_script_exists():
    assert os.path.exists(SETUP), "ไม่มี setup.ps1 = ลิงก์บรรทัดเดียวที่บอกผู้ใช้จะ 404"


def test_is_pure_ascii_so_the_console_can_render_it(script):
    """
    PowerShell รุ่นเก่าเดา encoding เอง และคอนโซลไม่มีฟอนต์ไทย
    ถ้ามีอักษรไทยหลุดเข้ามา ผู้ใช้จะเห็นกล่องสี่เหลี่ยมแล้วคิดว่าพัง
    """
    bad = [(i + 1, ln) for i, ln in enumerate(script.split(b"\n"))
           if any(b > 127 for b in ln)]
    assert not bad, f"มีอักขระที่ไม่ใช่ ASCII ที่บรรทัด {[b[0] for b in bad]}"


def test_points_at_files_that_really_exist(script):
    """พิมพ์ชื่อไฟล์ผิดตัวเดียว = ผู้ใช้กดแล้วไม่มีอะไรเกิดขึ้น"""
    text = script.decode("ascii")
    for rel in ("requirements.txt", "launcher.py", "gui.py",
                "services\\desktop.py"):
        assert rel in text, f"สคริปต์ไม่ได้อ้างถึง {rel}"
        assert os.path.exists(os.path.join(BASE, rel.replace("\\", os.sep))), \
            f"สคริปต์อ้างถึง {rel} แต่ไฟล์ไม่มีอยู่จริง"


def test_downloads_from_the_branch_that_is_actually_published(script):
    """
    ลิงก์ที่บอกผู้ใช้ชี้ที่ main — ถ้าสคริปต์ไปดึง branch อื่นจะได้โค้ดคนละตัว
    """
    text = script.decode("ascii")
    assert "karaBreath/stock-project" in text
    assert "refs/heads/main" in text, "zip fallback ต้องดึงจาก main"
    assert "origin/main" in text, "ต้องอัปเดตจาก main"


def test_never_throws_away_the_users_own_edits(script):
    """
    ผู้ใช้อาจมีไฟล์ที่แก้ค้างไว้ ตัวติดตั้งต้อง stash ไม่ใช่ลบทิ้ง
    คำสั่งพวกนี้กู้คืนไม่ได้ ห้ามมีเด็ดขาด
    """
    text = script.decode("ascii")
    for danger in ("reset --hard", "clean -fd", "checkout -f",
                   "Remove-Item $root", "rm -rf"):
        assert danger not in text, f"ห้ามใช้ {danger} กับโฟลเดอร์ของผู้ใช้"


def test_asks_windows_where_the_desktop_is(script):
    """เดา %USERPROFILE%\\Desktop อย่างเดียวไม่ได้ — เครื่องที่เปิด OneDrive หน้าจอย้ายที่"""
    text = script.decode("ascii")
    assert "GetFolderPath('Desktop')" in text


def test_handles_a_machine_with_no_python(script):
    """ถ้าไม่มี Python ต้องบอกให้ชัดและพาไปหน้าโหลด ไม่ใช่เงียบหาย"""
    text = script.decode("ascii")
    assert "python.org/downloads" in text
    assert "Add python.exe to PATH" in text


def test_handles_a_machine_with_no_git(script):
    """คนที่ยังไม่มี git ต้องติดตั้งได้อยู่ดี ไม่งั้นต้องไปลงเครื่องมืออีกตัวก่อน"""
    text = script.decode("ascii")
    assert "codeload.github.com" in text and "Expand-Archive" in text


def test_prefers_pythonw_so_no_black_window_appears(script):
    text = script.decode("ascii")
    assert "pythonw.exe" in text


# ---------------------------------------------------------------------------
# ทางเข้าแบบสั่งตรงของ services/desktop.py (setup.ps1 เรียกตัวนี้)
# ---------------------------------------------------------------------------
def test_desktop_cli_prints_ascii_only(monkeypatch, capsys):
    """
    ข้อความผลลัพธ์เป็นภาษาไทย ถ้าพิมพ์ตรง ๆ ลงคอนโซล cp874 จะเกิด
    UnicodeEncodeError แล้วดูเหมือนโปรแกรมพัง ทั้งที่ไอคอนสร้างสำเร็จ
    """
    import runpy
    from services import desktop as D

    monkeypatch.setattr(D, "IS_WIN", False)   # จะได้ error ที่เป็นภาษาไทย
    monkeypatch.setattr(sys, "argv", ["desktop.py"])
    runpy.run_path(os.path.join(BASE, "services", "desktop.py"),
                   run_name="__main__")

    out = capsys.readouterr().out
    assert out.strip(), "ต้องพิมพ์อะไรออกมาบ้าง ไม่ใช่เงียบ"
    out.encode("ascii")   # จะโยน UnicodeEncodeError ถ้ามีอักษรไทยหลุด


def test_one_line_command_in_the_guide_matches_this_file():
    """
    ถ้าลิงก์ในคู่มือกับชื่อไฟล์จริงไม่ตรงกัน ผู้ใช้จะได้ 404
    และนั่นคืออาการ 'หาไม่เจอ เปิดไม่ได้' ที่พยายามแก้อยู่พอดี
    """
    guide = os.path.join(BASE, "เริ่มตรงนี้.md")
    with open(guide, encoding="utf-8") as f:
        text = f.read()

    m = re.search(r"raw\.githubusercontent\.com/(\S+?)\s*\|", text)
    assert m, "คู่มือต้องมีคำสั่งบรรทัดเดียว"
    url_path = m.group(1)
    assert url_path.endswith("setup.ps1")
    assert url_path.startswith("karaBreath/stock-project/main/")
