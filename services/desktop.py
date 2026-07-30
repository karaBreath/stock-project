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
def desktop_dir() -> Path:
    """
    หาโฟลเดอร์หน้าจอจริง ๆ

    ⚠️ ห้ามเดาว่าเป็น %USERPROFILE%\\Desktop เสมอ — เครื่องที่เปิด OneDrive
    หน้าจอจะย้ายไปอยู่ใต้ OneDrive ถ้าเดาผิดจะสร้างไอคอนลงโฟลเดอร์ที่
    ผู้ใช้มองไม่เห็น แล้วคิดว่าโปรแกรมทำงานไม่สำเร็จ
    """
    if IS_WIN:
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Environment]::GetFolderPath('Desktop')"],
                capture_output=True, text=True, timeout=20)
            path = (r.stdout or "").strip()
            if path:
                return Path(path)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / "Desktop"


def _ps_quote(s) -> str:
    """ใส่ค่าเป็นสตริงของ PowerShell อย่างปลอดภัย (ครอบ single quote)"""
    return "'" + str(s).replace("'", "''") + "'"


def shortcut_command(link: Path, target: Path, args: str, workdir: Path,
                     icon: Path) -> list:
    """
    คำสั่งสร้างไฟล์ .lnk ผ่าน PowerShell — ไม่ต้องลงไลบรารีเสริมใด ๆ
    """
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut("
        f"{_ps_quote(link)});"
        f"$s.TargetPath = {_ps_quote(target)};"
        f"$s.Arguments = {_ps_quote(args)};"
        f"$s.WorkingDirectory = {_ps_quote(workdir)};"
        f"$s.IconLocation = {_ps_quote(icon)};"
        f"$s.Description = {_ps_quote(APP_NAME)};"
        "$s.Save()"
    )
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps]


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
    link = desktop_dir() / f"{APP_NAME}.lnk"
    cmd = shortcut_command(link, target, f'"{BASE / "gui.py"}"', BASE, icon)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        return {"ok": False, "error": f"เรียก PowerShell ไม่สำเร็จ: {e}"}

    if r.returncode != 0 or not link.exists():
        return {"ok": False,
                "error": ((r.stderr or r.stdout or "").strip()[-300:]
                          or "สร้างไฟล์ทางลัดไม่สำเร็จ")}
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
