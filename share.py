"""
เปิดเว็บ NEBULA ออกอินเทอร์เน็ตจากเครื่องตัวเอง ผ่าน Cloudflare Tunnel

ใช้แทน Render: ไม่มีค่าใช้จ่าย ไม่หลับ ไม่ต้องรอ build และข้อมูลทั้งหมด
(พอร์ต ฐานข้อมูล การเชื่อม MT5) อยู่บนเครื่องคุณเหมือนเดิม
Cloudflare แค่ส่งต่อคำขอเข้ามา

    python share.py                 เปิดแบบลิงก์สุ่ม (ไม่ต้องมีบัญชี Cloudflare)
    python share.py --tunnel ชื่อ    ใช้ tunnel ที่ตั้งชื่อไว้ (โดเมนตัวเอง)
    python share.py --no-lock       ปิดกุญแจ (อันตราย — ใครมีลิงก์ก็เข้าได้)

⚠️ ความปลอดภัย: เปิด tunnel = ทุกคนที่ได้ลิงก์เห็นพอร์ตและ MT5 ของคุณ
สคริปต์นี้จึงสุ่ม "กุญแจ" ให้อัตโนมัติและบังคับใช้เสมอ เว้นแต่สั่ง --no-lock เอง
เครื่องตัวเอง (127.0.0.1) ยังเข้าได้ตามปกติโดยไม่ต้องใส่กุญแจ
"""
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
IS_WIN = platform.system() == "Windows"
VENV_PY = BASE / "venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
TOOLS = BASE / "tools"
CF_EXE = TOOLS / ("cloudflared.exe" if IS_WIN else "cloudflared")
ENV_FILE = BASE / ".env"

DOWNLOAD = {
    ("Windows", "AMD64"): "cloudflared-windows-amd64.exe",
    ("Windows", "ARM64"): "cloudflared-windows-arm64.exe",
    ("Linux", "x86_64"): "cloudflared-linux-amd64",
    ("Linux", "aarch64"): "cloudflared-linux-arm64",
    ("Darwin", "arm64"): "cloudflared-darwin-arm64.tgz",
    ("Darwin", "x86_64"): "cloudflared-darwin-amd64.tgz",
}
RELEASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def say(msg=""):
    print(msg, flush=True)


def die(title, *lines):
    say()
    say(f"  [!] {title}")
    for l in lines:
        say(f"      {l}")
    say()
    if IS_WIN:
        try:
            input("  กด Enter เพื่อปิด ...")
        except EOFError:
            pass
    sys.exit(1)


# ---------------------------------------------------------------------------
# กุญแจ
# ---------------------------------------------------------------------------
def read_env() -> dict:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def ensure_token(disabled: bool) -> str:
    """
    หากุญแจจาก .env ถ้าไม่มีก็สุ่มให้แล้วเขียนกลับ — ผู้ใช้ไม่ต้องคิดเอง
    กุญแจอยู่ใน .env ซึ่ง .gitignore กันไม่ให้ขึ้น git อยู่แล้ว
    """
    if disabled:
        return ""
    env = read_env()
    token = env.get("SHARE_TOKEN", "")
    if token:
        return token

    token = secrets.token_urlsafe(24)
    with ENV_FILE.open("a", encoding="utf-8") as f:
        f.write(f"\n# กุญแจสำหรับเปิดเว็บออกเน็ต (สุ่มให้อัตโนมัติ ห้ามแชร์ให้คนอื่น)\n")
        f.write(f"SHARE_TOKEN={token}\n")
    say("  สร้างกุญแจใหม่ให้แล้ว (เก็บไว้ใน .env)")
    return token


# ---------------------------------------------------------------------------
# cloudflared
# ---------------------------------------------------------------------------
def find_cloudflared() -> str:
    on_path = shutil.which("cloudflared")
    if on_path:
        return on_path
    if CF_EXE.exists():
        return str(CF_EXE)
    return ""


def download_cloudflared() -> str:
    key = (platform.system(), platform.machine())
    name = DOWNLOAD.get(key)
    if not name:
        die(f"ไม่รู้จักเครื่องรุ่นนี้ ({key})",
            "ติดตั้ง cloudflared เองจาก https://developers.cloudflare.com/"
            "cloudflare-one/connections/connect-networks/downloads/")
    if name.endswith(".tgz"):
        die("เครื่อง Mac ต้องติดตั้ง cloudflared เอง",
            "ใช้คำสั่ง:  brew install cloudflared")

    TOOLS.mkdir(exist_ok=True)
    say("  กำลังโหลด cloudflared (ครั้งเดียว ~35 MB) ...")
    try:
        urllib.request.urlretrieve(RELEASE + name, CF_EXE)
    except Exception as e:
        die("โหลด cloudflared ไม่สำเร็จ", str(e)[:300],
            "ตรวจว่าเน็ตใช้ได้ แล้วลองใหม่")
    if not IS_WIN:
        CF_EXE.chmod(0o755)
    say("  โหลดเสร็จแล้ว")
    return str(CF_EXE)


# ---------------------------------------------------------------------------
# แอป
# ---------------------------------------------------------------------------
def start_app(port: int, token: str):
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    env = dict(os.environ, PORT=str(port))
    if token:
        env["SHARE_TOKEN"] = token
    return subprocess.Popen([py, str(BASE / "app.py")], env=env)


def wait_until_up(port: int, seconds: int = 90) -> bool:
    for _ in range(seconds):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                        timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            continue
    return False


def run_tunnel(exe: str, port: int, name: str, on_url):
    """
    เปิด tunnel แล้วอ่านลิงก์จากข้อความที่ cloudflared พิมพ์ออกมา
    (ลิงก์แบบสุ่มจะโผล่ในบรรทัดที่มี trycloudflare.com)
    """
    if name:
        cmd = [exe, "tunnel", "run", "--url", f"http://127.0.0.1:{port}", name]
    else:
        cmd = [exe, "tunnel", "--url", f"http://127.0.0.1:{port}"]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", bufsize=1)
    found = [False]

    def pump():
        for line in proc.stdout:
            m = URL_RE.search(line)
            if m and not found[0]:
                found[0] = True
                on_url(m.group(0))
            elif "failed" in line.lower() or "error" in line.lower():
                say(f"  cloudflared: {line.strip()[:160]}")

    threading.Thread(target=pump, daemon=True).start()
    return proc


def banner(url: str, token: str, port: int):
    link = f"{url}/?k={token}" if token else url
    say()
    say("  " + "=" * 64)
    say("    เปิดเว็บออกอินเทอร์เน็ตเรียบร้อย")
    say("  " + "-" * 64)
    say(f"    ลิงก์สำหรับเปิดจากมือถือ/ที่อื่น:")
    say(f"    {link}")
    say()
    if token:
        say(f"    กุญแจ: {token}")
        say("    เปิดด้วยลิงก์ข้างบนครั้งเดียว เครื่องนั้นจะจำไว้ 30 วัน")
        say("    ⚠️ ห้ามส่งลิงก์นี้ให้ใคร = ให้สิทธิ์ดูพอร์ตและ MT5 ทั้งหมด")
    else:
        say("    ⚠️ โหมดไม่ล็อกกุญแจ — ใครมีลิงก์ก็เข้าได้ทันที")
    say()
    say(f"    ในเครื่องนี้ใช้ได้ตามปกติที่  http://127.0.0.1:{port}")
    say("    ปิดทั้งหมด: กด Ctrl+C ในหน้าต่างนี้")
    say("  " + "=" * 64)
    say()


def main():
    args = sys.argv[1:]
    no_lock = "--no-lock" in args
    name = ""
    if "--tunnel" in args:
        i = args.index("--tunnel")
        if i + 1 < len(args):
            name = args[i + 1]

    port = int(read_env().get("PORT") or os.environ.get("PORT") or 5000)

    say()
    say("  NEBULA — เปิดเว็บออกอินเทอร์เน็ตผ่าน Cloudflare")
    say(f"  โฟลเดอร์: {BASE}")
    say()

    if not VENV_PY.exists():
        die("ยังไม่ได้ติดตั้งระบบ",
            "เปิด start.bat หนึ่งครั้งก่อน (มันจะติดตั้งให้เอง) แล้วค่อยเปิด share.bat")

    token = ensure_token(no_lock)
    exe = find_cloudflared() or download_cloudflared()

    say("  เปิดแอปในเครื่อง ...")
    app_proc = start_app(port, token)
    if not wait_until_up(port):
        app_proc.terminate()
        die("แอปไม่ตอบภายใน 90 วินาที",
            "ลองเปิด start.bat ดูก่อนว่ามีข้อความผิดพลาดอะไรไหม")
    say(f"  แอปพร้อมแล้วที่ http://127.0.0.1:{port}")

    say("  กำลังเปิด tunnel ...")
    tun = run_tunnel(exe, port, name, lambda u: banner(u, token, port))
    if name:
        banner(f"(โดเมนของ tunnel '{name}')", token, port)

    try:
        while True:
            time.sleep(1)
            if app_proc.poll() is not None:
                say("  แอปหยุดทำงาน — ปิด tunnel ด้วย")
                break
            if tun.poll() is not None:
                say("  tunnel หลุด — ปิดแอปด้วย")
                break
    except KeyboardInterrupt:
        pass
    finally:
        for p in (tun, app_proc):
            try:
                p.terminate()
            except Exception:
                pass
        say()
        say("  ปิดเรียบร้อย เว็บไม่เปิดออกเน็ตแล้ว")


if __name__ == "__main__":
    main()
