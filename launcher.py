"""
ตัวเปิดแอปแบบครบวงจร — เรียกจาก start.bat (Windows) หรือรันตรง ๆ ก็ได้

ทำอะไร
------
1. สร้าง virtual environment (ถ้ายังไม่มี)
2. ติดตั้ง/ตรวจ dependencies
3. สร้างไฟล์ .env จาก .env.example (ถ้ายังไม่มี)
4. เปิดเบราว์เซอร์ให้เอง
5. รันแอป

ทำไมไม่เขียนทั้งหมดใน .bat
-------------------------
ไฟล์ .bat ที่มีข้อความภาษาไทย + สั่ง chcp ข้างใน ทำให้ cmd.exe อ่านไฟล์หลุด
กลางทางและปิดตัวเองได้ (ปัญหาที่พบบ่อยบน Windows) จึงย้ายงานจริงมาไว้ที่ Python
ซึ่งพิมพ์ไทยได้ถูกต้องและบอก error ได้ละเอียดกว่า ส่วน .bat เหลือแค่หา Python

รันเองก็ได้:  python launcher.py            (ทำทุกขั้นแล้วเปิดแอป)
              python launcher.py --check    (ตรวจความพร้อมอย่างเดียว ไม่เปิดแอป)
              python launcher.py --no-browser
"""
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"
VENV = BASE / "venv"
VENV_PY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
PORT = int(os.environ.get("PORT", "5000"))
URL = f"http://127.0.0.1:{PORT}"


def say(msg=""):
    """พิมพ์ให้อ่านออกแน่นอน ไม่ว่า console จะตั้ง encoding อะไรไว้"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", "replace").decode("ascii", "replace"), flush=True)


def die(title, *lines):
    say()
    say("  " + "=" * 56)
    say(f"  [!] {title}")
    say("  " + "=" * 56)
    for ln in lines:
        say("  " + ln)
    say()
    if IS_WIN:
        try:
            input("  กด Enter เพื่อปิดหน้าต่างนี้ ...")
        except EOFError:
            pass
    sys.exit(1)


# ---------------------------------------------------------------------------
def ensure_venv():
    if VENV_PY.exists():
        say("[1/4] พบ virtual environment แล้ว")
        return
    say("[1/4] สร้าง virtual environment ... (ครั้งแรกใช้เวลาสักครู่)")
    r = subprocess.run([sys.executable, "-m", "venv", str(VENV)],
                       capture_output=True, text=True)
    if not VENV_PY.exists():
        die("สร้าง virtual environment ไม่สำเร็จ",
            "ข้อความจากระบบ:",
            (r.stderr or r.stdout or "(ไม่มีรายละเอียด)").strip()[:600],
            "",
            "ทางแก้: ลองรันคำสั่งนี้เองในหน้าต่างนี้เพื่อดู error เต็ม ๆ",
            f'  "{sys.executable}" -m venv venv')


def ensure_deps():
    say("[2/4] ตรวจ/ติดตั้ง dependencies ...")
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True, text=True)
    r = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-r",
                        str(BASE / "requirements.txt")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die("ติดตั้ง dependencies ไม่สำเร็จ",
            "ข้อความจากระบบ (ท้ายสุด):",
            (r.stderr or r.stdout).strip()[-900:],
            "",
            "สาเหตุที่พบบ่อย: อินเทอร์เน็ตหลุด / บริษัทบล็อก pypi.org",
            "ลองรันเองเพื่อดูรายละเอียด:",
            f'  "{VENV_PY}" -m pip install -r requirements.txt')

    # ยืนยันว่าของที่ต้องใช้ import ได้จริง (ลงผ่านแต่พังตอน import ก็มี)
    check = subprocess.run(
        [str(VENV_PY), "-c",
         "import flask, yfinance, pandas, numpy, requests, feedparser, dotenv; print('ok')"],
        capture_output=True, text=True)
    if "ok" not in check.stdout:
        die("ติดตั้งแล้วแต่เรียกใช้ไม่ได้",
            (check.stderr or "").strip()[-700:],
            "",
            "ทางแก้ที่มักได้ผล: ลบโฟลเดอร์ venv ทิ้งแล้วเปิด start.bat อีกครั้ง")


def ensure_env():
    env, example = BASE / ".env", BASE / ".env.example"
    if env.exists():
        say("[3/4] พบไฟล์ .env อยู่แล้ว — ใช้ค่าเดิม")
        return
    if example.exists():
        shutil.copyfile(example, env)
        say("[3/4] สร้างไฟล์ .env ให้อัตโนมัติ")
        say("      ตั้งให้เชื่อมระบบเทรด MT5 ที่ 127.0.0.1:8641 ไว้แล้ว")
    else:
        say("[3/4] ไม่มี .env.example — ใช้ค่าเริ่มต้นในโค้ด (ยังรันได้ปกติ)")


def open_browser_when_ready():
    """รอให้เซิร์ฟเวอร์ตอบก่อนแล้วค่อยเปิดเบราว์เซอร์ (ไม่เดาเวลา)"""
    import urllib.request
    for _ in range(60):
        time.sleep(1)
        try:
            with urllib.request.urlopen(URL + "/health", timeout=2) as r:
                if r.status == 200:
                    webbrowser.open(URL)
                    return
        except Exception:
            continue


def run_app():
    say("[4/4] เปิดแอป ...")
    say()
    say("  " + "=" * 56)
    say(f"    NEBULA พร้อมใช้งานที่   {URL}")
    say("    เบราว์เซอร์จะเปิดให้เองเมื่อแอปพร้อม")
    say("    ปิดโปรแกรม: กด Ctrl+C ในหน้าต่างนี้")
    say("  " + "=" * 56)
    say()
    say('  เมนู "พอร์ต MT5" จะมีข้อมูลเมื่อ volume-edge เปิดอยู่ที่ port 8641')
    say()
    try:
        subprocess.run([str(VENV_PY), str(BASE / "app.py")])
    except KeyboardInterrupt:
        pass
    say()
    say("แอปหยุดทำงานแล้ว")


def main():
    args = set(sys.argv[1:])
    say()
    say("  NEBULA — Mr.ARM STOCK SEEKER")
    say(f"  โฟลเดอร์: {BASE}")
    say(f"  Python:  {sys.version.split()[0]}  ({sys.executable})")
    say()

    if sys.version_info < (3, 9):
        die(f"Python เก่าเกินไป (ตอนนี้ {sys.version.split()[0]})",
            "ต้องใช้ 3.9 ขึ้นไป — ติดตั้งใหม่จาก https://www.python.org/downloads/")

    ensure_venv()
    ensure_deps()
    ensure_env()

    if "--check" in args:
        say()
        say("✅ ตรวจแล้วพร้อมใช้งานทุกอย่าง — เปิดได้ด้วย start.bat")
        if IS_WIN:
            try:
                input("  กด Enter เพื่อปิด ...")
            except EOFError:
                pass
        return

    if "--no-browser" not in args:
        threading.Thread(target=open_browser_when_ready, daemon=True).start()
    run_app()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        die(f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {type(e).__name__}",
            str(e)[:600],
            "",
            "ช่วยแคปหน้าต่างนี้ส่งให้ผมดูได้เลย")
