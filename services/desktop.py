"""
สร้างไอคอนบนหน้าจอ Windows ให้เปิดโปรแกรมได้ด้วยการดับเบิลคลิก

แยกตรรกะออกมาจากหน้าต่างโปรแกรม (gui.py) เพื่อให้ทดสอบได้โดยไม่ต้องมีจอ
"""
import os
import platform
import struct
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
IS_WIN = platform.system() == "Windows"

APP_NAME = "เทรดข่าวโลก"
ICON_SOURCE = BASE / "static" / "icons" / "icon-192.png"
ICON_PATH = BASE / "static" / "icons" / "app.ico"


# ---------------------------------------------------------------------------
# ไอคอน
# ---------------------------------------------------------------------------
def ico_from_png(png: bytes) -> bytes:
    """
    ห่อไฟล์ PNG ให้เป็น .ico โดยไม่ต้องพึ่งไลบรารีเพิ่ม

    ไฟล์ .ico ตั้งแต่ Windows Vista เก็บ PNG ไว้ข้างในได้ตรง ๆ
    จึงไม่ต้องแปลงเป็น bitmap เอง (ซึ่งต้องเขียน encoder ทั้งตัว)
    ใช้ไอคอนตัวเดียวกับที่แอปใช้อยู่แล้ว หน้าจอกับในเว็บจะได้เป็นรูปเดียวกัน
    """
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("ไฟล์ต้นทางไม่ใช่ PNG")
    w, h = struct.unpack(">II", png[16:24])
    if w > 256 or h > 256:
        raise ValueError(f"ไอคอนใหญ่เกินไป ({w}x{h}) — .ico รับได้ไม่เกิน 256")

    header = struct.pack("<HHH", 0, 1, 1)          # reserved, type=icon, จำนวน 1 รูป
    entry = struct.pack(
        "<BBBBHHII",
        0 if w == 256 else w,                      # 0 หมายถึง 256 ตามสเปค
        0 if h == 256 else h,
        0,                                          # จำนวนสี (0 = ทรูคัลเลอร์)
        0,                                          # reserved
        1,                                          # color planes
        32,                                         # bits per pixel
        len(png),
        len(header) + 16,                           # ตำแหน่งที่ข้อมูลรูปเริ่ม
    )
    return header + entry + png


def ensure_icon() -> Path:
    """สร้าง app.ico จากไอคอนของแอปถ้ายังไม่มี"""
    if ICON_PATH.exists() and ICON_PATH.stat().st_size > 0:
        return ICON_PATH
    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    ICON_PATH.write_bytes(ico_from_png(ICON_SOURCE.read_bytes()))
    return ICON_PATH


# ---------------------------------------------------------------------------
# ทางลัดบนหน้าจอ
# ---------------------------------------------------------------------------
UTF8_PREFIX = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"


def _dec(b) -> str:
    if b is None:
        return ""
    if isinstance(b, str):            # เผื่อถูก monkeypatch ในเทสต์
        return b
    return b.decode("utf-8", "replace")


def ps_run(ps: str, timeout: int = 60):
    """
    เรียก PowerShell แล้วอ่านผลกลับมาโดยไม่พังเรื่อง encoding

    บทเรียนสองข้อที่ CI ของ Windows จริงสอนมา — ห้ามลืม:

    1) ห้ามส่งสคริปต์ที่มีภาษาไทยผ่าน -Command เด็ดขาด
       ตัวอักษรไทยจะกลายเป็น "?" ทั้งหมดก่อนถึง PowerShell
       (เครื่องที่ระบบเป็นอังกฤษ code page ไม่มีตัวอักษรไทย)
       ผลคือไปสั่งบันทึกไฟล์ชื่อ "???????????.lnk" ซึ่ง Windows ปฏิเสธ
       ขึ้นว่า "Unable to save shortcut"
       ทางแก้: เขียนสคริปต์ลงไฟล์ .ps1 แบบ UTF-8 ที่มี BOM แล้วสั่ง -File
       PowerShell 5.1 อ่านไฟล์ที่ไม่มี BOM เป็น ANSI — BOM จึงจำเป็น ไม่ใช่ทางเลือก

    2) ห้ามใช้ text=True
       Python จะถอดรหัสผลลัพธ์ด้วย code page ของเครื่อง (เช่น cp1252)
       พอเจอไบต์ที่ถอดไม่ได้ เธรดที่อ่านผลจะตายทั้งเธรด ผลกลายเป็นค่าว่าง
       แล้วเราจะสรุปผิดว่า "สร้างไอคอนไม่สำเร็จ" ทั้งที่แค่อ่านคำตอบไม่ออก
    """
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    try:
        # utf-8-sig = UTF-8 พร้อม BOM ซึ่งเป็นสัญญาณเดียวที่ PowerShell 5.1
        # ใช้ตัดสินว่าไฟล์นี้เป็น Unicode
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(UTF8_PREFIX + "\n" + ps)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", path],
            capture_output=True, timeout=timeout)
        return (getattr(r, "returncode", 0), _dec(getattr(r, "stdout", b"")),
                _dec(getattr(r, "stderr", b"")))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def desktop_dir() -> Path:
    """
    หาโฟลเดอร์หน้าจอจริง ๆ

    ⚠️ ห้ามเดาว่าเป็น %USERPROFILE%\\Desktop เสมอ — เครื่องที่เปิด OneDrive
    หน้าจอจะย้ายไปอยู่ใต้ OneDrive ถ้าเดาผิดจะสร้างไอคอนลงโฟลเดอร์ที่
    ผู้ใช้มองไม่เห็น แล้วคิดว่าโปรแกรมทำงานไม่สำเร็จ
    """
    if IS_WIN:
        try:
            _, out, _ = ps_run("[Environment]::GetFolderPath('Desktop')",
                               timeout=20)
            path = out.strip().splitlines()[0].strip() if out.strip() else ""
            if path:
                return Path(path)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / "Desktop"


STAGING_NAME = "nebula-shortcut.lnk"   # ASCII ล้วนโดยตั้งใจ · ดู create_shortcut


def ansi_safe(text: str) -> bool:
    """
    เขียนเป็น code page ของระบบได้ไหม

    WScript.Shell เป็นของเก่าที่แปลงพาธเป็น ANSI ก่อนบันทึกเสมอ
    ถ้าพาธมีตัวอักษรที่ code page ของระบบไม่มี มันจะบันทึกไม่สำเร็จ
    (บนเครื่องที่ไม่ได้ตั้งภาษาไทย ชื่อไทยจะกลายเป็น ??? แล้ว Windows ปฏิเสธ)
    """
    try:
        text.encode("mbcs")
        return True
    except UnicodeEncodeError:
        return False
    except LookupError:
        return True        # ไม่ใช่ Windows — ไม่ต้องกังวลเรื่องนี้


def short_path(p: Path) -> Path:
    """
    ขอชื่อพาธแบบสั้น (8.3) จาก Windows ซึ่งเป็น ASCII เสมอ

    ใช้ตอนที่ชื่อผู้ใช้เป็นภาษาไทย ทำให้แม้แต่โฟลเดอร์ปลายทางก็เขียนเป็น
    ANSI ไม่ได้ ถ้าระบบปิดการสร้างชื่อสั้นไว้ จะได้พาธเดิมกลับมา
    """
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 1024):
            return Path(buf.value)
    except Exception:
        pass
    return p


def _ps_quote(s) -> str:
    """ใส่ค่าเป็นสตริงของ PowerShell อย่างปลอดภัย (ครอบ single quote)"""
    return "'" + str(s).replace("'", "''") + "'"


def shortcut_script(link: Path, target: Path, args: str, workdir: Path,
                    icon: Path) -> str:
    """
    สคริปต์ PowerShell ที่สร้างไฟล์ .lnk — ไม่ต้องลงไลบรารีเสริมใด ๆ

    ห่อด้วย try/catch แล้วพ่นข้อความจริงออกมา ไม่งั้นเวลาพังจะได้แค่
    exit code เปล่า ๆ ซึ่งบอกอะไรไม่ได้เลยว่าติดตรงไหน
    """
    return (
        "$ErrorActionPreference='Stop';"
        "try {"
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut("
        f"{_ps_quote(link)});"
        f"$s.TargetPath = {_ps_quote(target)};"
        f"$s.Arguments = {_ps_quote(args)};"
        f"$s.WorkingDirectory = {_ps_quote(workdir)};"
        f"$s.IconLocation = {_ps_quote(icon)};"
        f"$s.Description = {_ps_quote(APP_NAME)};"
        "$s.Save();"
        "Write-Output 'SAVED'"
        "} catch { Write-Output ('FAILED: ' + $_.Exception.Message); exit 1 }"
    )


def shortcut_command(link: Path, target: Path, args: str, workdir: Path,
                     icon: Path) -> list:
    """
    คำสั่งเต็มสำหรับเรียก PowerShell — เก็บไว้เพื่อความเข้ากันได้เท่านั้น

    ⚠️ อย่าใช้เส้นทางนี้กับชื่อที่เป็นภาษาไทย ตัวอักษรจะหายกลายเป็น "?"
    ของจริงใช้ ps_run() ซึ่งเขียนลงไฟล์ก่อน
    """
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-Command",
            UTF8_PREFIX + shortcut_script(link, target, args, workdir, icon)]


def python_target() -> tuple:
    """
    เลือกตัวรันที่ไม่เปิดหน้าต่างดำ (pythonw) ถ้ามี

    ใช้ของใน venv ก่อน เพราะไลบรารีทั้งหมดถูกติดตั้งไว้ที่นั่น
    ถ้ายังไม่มี venv ค่อยใช้ python ของเครื่อง
    """
    venv_w = BASE / "venv" / "Scripts" / "pythonw.exe"
    venv_p = BASE / "venv" / "Scripts" / "python.exe"
    if venv_w.exists():
        return venv_w, True
    if venv_p.exists():
        return venv_p, False
    import sys
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    if quiet.exists():
        return quiet, True
    return exe, False


def create_shortcut() -> dict:
    """สร้างไอคอน 'เทรดข่าวโลก' บนหน้าจอ · คืนผลลัพธ์แบบอ่านรู้เรื่อง"""
    if not IS_WIN:
        return {"ok": False,
                "error": "สร้างไอคอนบนหน้าจอได้เฉพาะ Windows"}
    try:
        icon = ensure_icon()
    except Exception as e:
        return {"ok": False, "error": f"สร้างไฟล์ไอคอนไม่ได้: {e}"}

    target, quiet = python_target()
    desk = desktop_dir()
    link = desk / f"{APP_NAME}.lnk"

    # ⚠️ ห้ามให้ PowerShell บันทึกไฟล์ชื่อภาษาไทยโดยตรง
    #
    # WScript.Shell แปลงพาธเป็น ANSI ก่อนบันทึก บนเครื่องที่ระบบไม่ใช่ภาษาไทย
    # ชื่อจะกลายเป็น "???????????.lnk" แล้ว Windows ปฏิเสธ
    # ขึ้นว่า "Unable to save shortcut" — วัดมาแล้วบน windows-latest จริง
    #
    # จึงให้มันบันทึกด้วยชื่ออังกฤษก่อน แล้วค่อยให้ Python เปลี่ยนชื่อเป็นไทย
    # เพราะ Python เปลี่ยนชื่อไฟล์ผ่าน API แบบ Unicode ไม่ติดข้อจำกัดนี้
    # (ชื่อไฟล์ไม่ได้ถูกเก็บอยู่ข้างในไฟล์ .lnk การเปลี่ยนชื่อจึงปลอดภัย)
    build_dir = desk if ansi_safe(str(desk)) else short_path(desk)
    staging = build_dir / STAGING_NAME
    try:
        code, out, err = ps_run(
            shortcut_script(staging, target, f'"{BASE / "gui.py"}"',
                            BASE, icon))
    except Exception as e:
        return {"ok": False, "error": f"เรียก PowerShell ไม่สำเร็จ: {e}"}

    if code != 0 or not staging.exists():
        detail = " / ".join(p for p in ((err or "").strip(),
                                        (out or "").strip()) if p)
        return {"ok": False,
                "error": (detail[-400:] if detail
                          else f"สร้างไฟล์ทางลัดไม่สำเร็จ (exit {code}, "
                               f"ไม่พบไฟล์ที่ {staging})")}

    try:
        staging.replace(link)
    except OSError as e:
        return {"ok": False,
                "error": f"เปลี่ยนชื่อไอคอนเป็นภาษาไทยไม่สำเร็จ: {e}"}
    return {
        "ok": True,
        "path": str(link),
        "name": APP_NAME,
        "quiet": quiet,
        "note": ("สร้างไอคอนบนหน้าจอแล้ว — ดับเบิลคลิกเปิดได้เลย"
                 + ("" if quiet else " (จะมีหน้าต่างดำขึ้นมาด้วย)")),
    }


if __name__ == "__main__":
    # เรียกจาก setup.ps1 ได้ตรง ๆ
    #
    # ⚠️ พิมพ์เป็นอังกฤษล้วนตรงนี้ — คอนโซล Windows ใช้ code page 874/437
    # ถ้าพิมพ์ไทยออกไปจะได้ UnicodeEncodeError แล้วดูเหมือนโปรแกรมพัง
    # ทั้งที่ไอคอนสร้างสำเร็จแล้ว ข้อความไทยอยู่ในหน้าต่างโปรแกรมแทน
    _r = create_shortcut()
    if _r["ok"]:
        print("  Desktop icon created.")
    else:
        print("  Could not create the desktop icon: "
              + _r["error"].encode("ascii", "replace").decode("ascii"))
