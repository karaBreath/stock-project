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


def test_no_thai_inside_powershell_workflow_steps():
    """
    เคยพลาดมาแล้วจริง ๆ: GitHub เขียน step เป็นไฟล์ .ps1 แบบ UTF-8 ไม่มี BOM
    แต่ PowerShell 5.1 อ่านไฟล์ .ps1 เป็น ANSI ข้อความไทยเลยเพี้ยน
    และไบต์ที่เพี้ยนบางตัวไปปิด string ก่อนกำหนด = ทั้ง step พังด้วย syntax error

    ชื่อ step (name:) เป็นไทยได้ เพราะไม่ได้ถูกรัน — ห้ามเฉพาะใน run:
    """
    wf_dir = os.path.join(BASE, ".github", "workflows")
    problems = []

    for fn in sorted(os.listdir(wf_dir)):
        if not fn.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(wf_dir, fn), encoding="utf-8") as f:
            lines = f.readlines()

        in_ps_run = False
        run_indent = 0
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("shell:"):
                # ตัดคอมเมนต์ท้ายบรรทัดออกก่อน ไม่งั้นคำว่า powershell
                # ที่อยู่ในคอมเมนต์ของ step ที่ใช้ bash จะถูกนับผิด
                value = stripped.split(":", 1)[1].split("#")[0].strip()
                in_ps_run = value in ("powershell", "pwsh")
                continue
            if in_ps_run and stripped.startswith("run:"):
                run_indent = len(line) - len(line.lstrip())
                continue
            if run_indent:
                indent = len(line) - len(line.lstrip())
                if stripped and indent <= run_indent:
                    run_indent, in_ps_run = 0, False
                elif any(ord(c) > 127 for c in line):
                    problems.append(f"{fn}:{i}: {stripped[:60]}")

    assert not problems, (
        "มีอักขระที่ไม่ใช่ ASCII ในเนื้อ step ของ PowerShell:\n  "
        + "\n  ".join(problems))


def _guide_text():
    with open(os.path.join(BASE, "เริ่มตรงนี้.md"), encoding="utf-8") as f:
        return f.read()


def _one_liner():
    """บรรทัดคำสั่งใน code block ของคู่มือ (บรรทัดที่ขึ้นต้นด้วย powershell)"""
    for line in _guide_text().splitlines():
        if line.startswith("powershell "):
            return line
    return None


def test_one_line_command_in_the_guide_matches_this_file():
    """
    ถ้าลิงก์ในคู่มือกับชื่อไฟล์จริงไม่ตรงกัน ผู้ใช้จะได้ 404
    และนั่นคืออาการ 'หาไม่เจอ เปิดไม่ได้' ที่พยายามแก้อยู่พอดี
    """
    line = _one_liner()
    assert line, "คู่มือต้องมีคำสั่งบรรทัดเดียว"

    m = re.search(r"raw\.githubusercontent\.com/([^\s)}|]+)", line)
    assert m, "คำสั่งบรรทัดเดียวต้องชี้ไปที่ raw.githubusercontent.com"
    url_path = m.group(1)
    assert url_path.endswith("setup.ps1")
    assert url_path.startswith("karaBreath/stock-project/main/")


def test_one_line_command_has_no_double_quotes():
    """
    เกิดขึ้นจริงกับผู้ใช้: ก๊อปคำสั่งจากแชท แล้ว " ถูกเปลี่ยนเป็นอัญประกาศโค้ง
    PowerShell parse ไม่ผ่าน หน้าต่างเด้งแวบเดียวแล้วปิด = 'ใช้ไม่ได้'
    ทางแก้คือคำสั่งต้องไม่มี " เลย จะได้ไม่มีอะไรให้ก๊อปเพี้ยน
    """
    line = _one_liner()
    assert line, "คู่มือต้องมีคำสั่งบรรทัดเดียว"
    for ch in ('"', "“", "”"):
        assert ch not in line, f"คำสั่งบรรทัดเดียวห้ามมี {ch!r}"


def test_one_line_command_forces_tls12_and_shows_errors():
    """
    PowerShell 5.1 ต่อ TLS 1.0 ก่อน แต่ GitHub ไม่รับ -> โหลดไม่ผ่านตั้งแต่แรก
    และถ้าไม่ดัก error หน้าต่างจะปิดทิ้งจนไม่มีอะไรให้อ่าน
    """
    line = _one_liner()
    assert line, "คู่มือต้องมีคำสั่งบรรทัดเดียว"
    assert "SecurityProtocol" in line, "ต้องบังคับ TLS ก่อนโหลด"
    # 3072 คือค่าตัวเลขของ Tls12 — ใช้เลขเพื่อให้บรรทัดสั้นพอลงช่อง Run
    assert ("3072" in line or "Tls12" in line), "ต้องตั้งเป็น TLS 1.2"
    assert "catch" in line, "ต้องดัก error ไว้"
    assert "Read-Host" in line, "ต้องค้างหน้าต่างไว้ให้ผู้ใช้อ่าน error"


def test_one_line_command_fits_the_windows_run_box():
    """
    ช่อง Windows + R รับได้ 259 ตัวอักษร เกินกว่านั้นจะถูกตัดท้ายทิ้งเงียบ ๆ
    ผู้ใช้จะวางแล้วกด Enter ได้ตามปกติ แต่คำสั่งที่รันจริงขาดไปครึ่งท่อน
    """
    line = _one_liner()
    assert line, "คู่มือต้องมีคำสั่งบรรทัดเดียว"
    assert len(line) <= 259, f"คำสั่งยาว {len(line)} ตัวอักษร เกินช่อง Run"


def test_setup_script_holds_the_window_open_on_failure(script):
    """
    สคริปต์ถูกเปิดจากช่อง Run พอ throw หน้าต่างหายไปพร้อมกัน
    ผู้ใช้เลยเห็นแค่ไฟแวบ ต้องมี trap ที่ค้างหน้าต่างไว้เสมอ
    """
    text = script.decode("ascii")
    assert "trap {" in text, "ต้องมี trap ครอบ ไม่งั้น error จะหายไปกับหน้าต่าง"
    assert "Tls12" in text, "ต้องบังคับ TLS 1.2 ก่อนโหลด zip"


# ---------------------------------------------------------------------------
# install.bat — ทางเลือกแบบไม่ต้องพิมพ์อะไรเลย (ดับเบิลคลิกอย่างเดียว)
# ---------------------------------------------------------------------------
INSTALL_BAT = os.path.join(BASE, "install.bat")


def test_install_bat_exists():
    """คู่มือบอกให้โหลดไฟล์นี้ ถ้าไม่มีจริงผู้ใช้จะได้ 404 ซ้ำอาการเดิม"""
    assert os.path.exists(INSTALL_BAT)
    assert "install.bat" in _guide_text(), "คู่มือต้องบอกทางเลือกนี้ด้วย"


def test_install_bat_is_pure_ascii():
    """คอนโซล Windows ไม่มีฟอนต์ไทย ข้อความไทยจะกลายเป็นกล่องสี่เหลี่ยม"""
    with open(INSTALL_BAT, "rb") as f:
        raw = f.read()
    bad = [i + 1 for i, ln in enumerate(raw.split(b"\n"))
           if any(b > 127 for b in ln)]
    assert not bad, f"install.bat มีอักขระที่ไม่ใช่ ASCII ที่บรรทัด {bad}"


def test_install_bat_pauses_so_errors_stay_readable():
    """เหตุผลเดียวที่ไฟล์นี้มีอยู่: หน้าต่างต้องไม่ปิดเองก่อนได้อ่าน"""
    with open(INSTALL_BAT, encoding="ascii") as f:
        text = f.read()
    assert "pause" in text
    assert "Tls12" in text, "ต้องบังคับ TLS 1.2 ไม่งั้นโหลดไม่ผ่านบน PS 5.1"
    assert "main/setup.ps1" in text, "ต้องดึง setup.ps1 จาก main"
