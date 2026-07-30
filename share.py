"""
เปิดเว็บ NEBULA ออกอินเทอร์เน็ตจากเครื่องตัวเอง ผ่าน Cloudflare Tunnel

ใช้แทน Render: ไม่มีค่าใช้จ่าย ไม่หลับ ไม่ต้องรอ build และข้อมูลทั้งหมด
(พอร์ต ฐานข้อมูล การเชื่อม MT5) อยู่บนเครื่องคุณเหมือนเดิม
Cloudflare แค่ส่งต่อคำขอเข้ามา

    python share.py                        เปิดแบบลิงก์สุ่ม (ไม่ต้องมีบัญชี)
    python share.py --setup-domain <โดเมน>  ตั้งโดเมนตัวเองครั้งแรก (ทำครั้งเดียว)
    python share.py --tunnel <ชื่อ>          ใช้ tunnel ที่ตั้งชื่อไว้
    python share.py --no-lock              ปิดกุญแจ (อันตราย)

ลิงก์สุ่มจะเปลี่ยนทุกครั้งที่เปิด ทำให้ต้องส่งลิงก์ใหม่เข้ามือถือตลอด
ตั้งโดเมนตัวเองครั้งเดียวแล้วลิงก์จะคงที่ตลอดไป (เช่น https://nebula.example.com)

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


def set_env(pairs: dict):
    """เขียนค่าลง .env — ทับของเดิมถ้ามีคีย์นั้นอยู่แล้ว ไม่ให้ซ้ำซ้อน"""
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    left = dict(pairs)
    out = []
    for line in lines:
        k = line.split("=", 1)[0].strip() if "=" in line else ""
        if k in left:
            out.append(f"{k}={left.pop(k)}")
        else:
            out.append(line)
    for k, v in left.items():
        out.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


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
# ตั้งโดเมนตัวเอง (ทำครั้งเดียว)
# ---------------------------------------------------------------------------
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?"
                     r"(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def _step(n, total, text):
    say()
    say(f"  [{n}/{total}] {text}")


def setup_domain(hostname: str, exe: str) -> bool:
    """
    พาตั้งโดเมนตัวเองทีละขั้น แล้วจำค่าไว้ให้ครั้งต่อไปเปิดได้เลย

    ทำ 3 อย่างผ่าน cloudflared:
      1. login   — เปิดเบราว์เซอร์ให้เลือกโดเมนในบัญชี Cloudflare ของคุณ
      2. create  — สร้าง tunnel พร้อมไฟล์กุญแจของมันเอง (เก็บในเครื่องคุณ)
      3. route   — ชี้ชื่อโดเมนย่อยมาที่ tunnel นี้ (สร้าง DNS record ให้อัตโนมัติ)

    เงื่อนไขเดียวที่ข้ามไม่ได้: โดเมนหลักต้องอยู่ในบัญชี Cloudflare
    (แผนฟรีพอ ไม่ต้องเสียเงิน) เพราะ Cloudflare ต้องมีสิทธิ์แก้ DNS ให้
    """
    hostname = (hostname or "").strip().lower().rstrip(".")
    if not HOST_RE.match(hostname):
        die(f"ชื่อโดเมนไม่ถูกรูปแบบ: {hostname or '(ว่าง)'}",
            "ต้องเป็นแบบเต็ม เช่น  nebula.example.com")

    name = hostname.split(".")[0] or "nebula"
    say()
    say("  " + "=" * 64)
    say(f"    ตั้งโดเมนตัวเอง: {hostname}")
    say(f"    ชื่อ tunnel ที่จะสร้าง: {name}")
    say("  " + "-" * 64)
    say("    ต้องมี: บัญชี Cloudflare (ฟรี) และโดเมนหลักอยู่ในบัญชีนั้นแล้ว")
    say("    ทำครั้งเดียวจบ ครั้งต่อไปเปิด share.bat ได้เลย")
    say("  " + "=" * 64)

    _step(1, 3, "เข้าสู่ระบบ Cloudflare")
    say("      กำลังจะเกิดอะไรขึ้น:")
    say("        · เบราว์เซอร์จะเปิดหน้า Cloudflare ขึ้นมาเอง")
    say("        · ถ้ายังไม่ได้ล็อกอิน ให้ล็อกอินก่อน (สมัครฟรีได้ที่หน้านั้นเลย)")
    say(f"        · จะมีรายชื่อโดเมนให้เลือก — กดเลือก '{'.'.join(hostname.split('.')[-2:])}'")
    say("        · แล้วกดปุ่ม Authorize สีฟ้า")
    say("      ทำเสร็จแล้วกลับมาที่หน้าต่างนี้ มันจะไปต่อเอง")
    say()
    if subprocess.run([exe, "tunnel", "login"]).returncode != 0:
        die("เข้าสู่ระบบ Cloudflare ไม่สำเร็จ",
            "ถ้าเบราว์เซอร์ไม่เปิดเอง ให้คัดลอกลิงก์ยาว ๆ ที่ขึ้นในหน้าต่างนี้",
            "ไปวางในเบราว์เซอร์เอง แล้วรันไฟล์นี้ใหม่อีกครั้ง")

    _step(2, 3, f"สร้าง tunnel ชื่อ '{name}' (ไม่ต้องทำอะไร รอสักครู่)")
    r = subprocess.run([exe, "tunnel", "create", name],
                       capture_output=True, text=True)
    blob = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and "already exists" not in blob.lower():
        die("สร้าง tunnel ไม่สำเร็จ", blob.strip()[-400:])
    if "already exists" in blob.lower():
        say(f"      มี tunnel ชื่อ '{name}' อยู่แล้ว — ใช้ตัวเดิม")

    _step(3, 3, f"ชี้ {hostname} มาที่ tunnel นี้ (ไม่ต้องทำอะไร รอสักครู่)")
    r = subprocess.run([exe, "tunnel", "route", "dns", name, hostname],
                       capture_output=True, text=True)
    blob = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and "already exists" not in blob.lower():
        die(f"ชี้โดเมน {hostname} ไม่สำเร็จ", blob.strip()[-400:],
            "",
            "สาเหตุที่พบบ่อย: โดเมนหลักยังไม่ได้อยู่ในบัญชี Cloudflare นี้",
            "ต้องเพิ่มโดเมนเข้า Cloudflare และย้าย nameserver ให้เรียบร้อยก่อน")

    set_env({"SHARE_TUNNEL": name, "SHARE_HOSTNAME": hostname})
    say()
    say("  " + "=" * 64)
    say("    ตั้งโดเมนเรียบร้อย")
    say(f"    ต่อไปเปิด share.bat เฉย ๆ จะได้ลิงก์คงที่:  https://{hostname}")
    say("    (ถ้าเปิดแล้วยังไม่ขึ้น รออีก 2-3 นาที ระบบ DNS กำลังกระจายข้อมูล)")
    say("  " + "=" * 64)
    say()
    return True


# ---------------------------------------------------------------------------
# แอป
# ---------------------------------------------------------------------------
def start_app(port: int, token: str):
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    env = dict(os.environ, PORT=str(port))
    if token:
        env["SHARE_TOKEN"] = token
    return subprocess.Popen([py, str(BASE / "app.py")], env=env)


def wait_until_up(port: int, proc=None, seconds: int = 90) -> bool:
    """
    รอจน "แอปที่เราเพิ่งเปิด" พร้อมใช้งาน

    ⚠️ ต้องเช็คด้วยว่า process ยังอยู่ไหม ไม่ใช่ดูแค่ /health ตอบ
    เจอจริงตอนทดสอบ: มีแอปเก่าค้างอยู่ที่พอร์ตเดิม ตัวใหม่จึงเปิดไม่ขึ้น
    ("Address already in use") แต่ /health ยังตอบ 200 เพราะเป็นของตัวเก่า
    ระบบเลยบอกว่า "แอปพร้อมแล้ว" ทั้งที่ตัวที่เราเปิดตายไปแล้ว
    แถวนั้นอันตราย เพราะตัวเก่าอาจ "ไม่ได้ล็อกกุญแจ" แล้วเราเอาไปเปิดออกเน็ต
    """
    for _ in range(seconds):
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                        timeout=2) as r:
                if r.status == 200:
                    return proc is None or proc.poll() is None
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


def banner(url: str, token: str, port: int, fixed: bool = False):
    link = f"{url}/?k={token}" if token else url
    say()
    say("  " + "=" * 64)
    say("    เปิดเว็บออกอินเทอร์เน็ตเรียบร้อย")
    say("  " + "-" * 64)
    say(f"    ลิงก์สำหรับเปิดจากมือถือ/ที่อื่น:")
    say(f"    {link}")
    if fixed:
        say("    (ลิงก์นี้คงที่ ไม่เปลี่ยนทุกครั้งที่เปิด — บันทึกไว้ในมือถือได้เลย)")
    else:
        say("    ⚠️ ลิงก์สุ่มนี้จะเปลี่ยนทุกครั้งที่เปิดใหม่")
        say("       อยากได้ลิงก์คงที่: share.bat --setup-domain nebula.โดเมนคุณ")
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


def _arg_after(args, flag):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return ""


def main():
    args = sys.argv[1:]
    no_lock = "--no-lock" in args
    env = read_env()

    # ชื่อ tunnel: จากคำสั่ง > ที่เคยตั้งไว้ใน .env > ไม่มี (ใช้ลิงก์สุ่ม)
    name = _arg_after(args, "--tunnel") or env.get("SHARE_TUNNEL", "")
    hostname = env.get("SHARE_HOSTNAME", "")
    port = int(env.get("PORT") or os.environ.get("PORT") or 5000)

    say()
    say("  NEBULA — เปิดเว็บออกอินเทอร์เน็ตผ่าน Cloudflare")
    say(f"  โฟลเดอร์: {BASE}")
    say()

    if not VENV_PY.exists():
        die("ยังไม่ได้ติดตั้งระบบ",
            "เปิด start.bat หนึ่งครั้งก่อน (มันจะติดตั้งให้เอง) แล้วค่อยเปิด share.bat")

    exe = find_cloudflared() or download_cloudflared()

    if "--setup-domain" in args:
        host = _arg_after(args, "--setup-domain")
        setup_domain(host, exe)
        say("  รัน share.bat อีกครั้งเพื่อเปิดใช้งานด้วยโดเมนนี้")
        return

    token = ensure_token(no_lock)
    say("  เปิดแอปในเครื่อง ...")
    app_proc = start_app(port, token)
    if not wait_until_up(port, app_proc):
        try:
            app_proc.terminate()
        except Exception:
            pass
        die(f"เปิดแอปที่พอร์ต {port} ไม่สำเร็จ",
            f"สาเหตุที่พบบ่อยที่สุด: มีแอปเปิดค้างอยู่แล้วที่พอร์ต {port}",
            "",
            "วิธีแก้: ปิดหน้าต่าง start.bat / share.bat อันเก่าให้หมดก่อน",
            f"        หรือเปลี่ยนพอร์ตในไฟล์ .env เป็นเลขอื่น เช่น PORT={port + 1}",
            "",
            "⚠️ ระบบไม่เปิด tunnel ให้ เพราะแอปที่ค้างอยู่นั้นอาจไม่ได้ล็อกกุญแจ",
            "   ถ้าเปิดออกเน็ตไปเลยจะกลายเป็นเปิดพอร์ตและ MT5 ให้คนอื่นดู")
    say(f"  แอปพร้อมแล้วที่ http://127.0.0.1:{port}")

    say("  กำลังเปิด tunnel ...")
    tun = run_tunnel(exe, port, name, lambda u: banner(u, token, port))
    if name:
        # tunnel ที่ตั้งชื่อไว้ไม่พิมพ์ลิงก์ออกมา เพราะโดเมนถูกกำหนดไว้แล้ว
        banner(f"https://{hostname}" if hostname else f"(tunnel '{name}')",
               token, port, fixed=bool(hostname))

    try:
        while True:
            time.sleep(1)
            if app_proc.poll() is not None:
                say("  แอปหยุดทำงาน — ปิด tunnel ด้วย")
                break
            if tun.poll() is not None:
                say("  tunnel หลุด — ปิดแอปด้วย")
                say("  ถ้าเห็นข้อความ 'Host not in allowlist' ด้านบน แปลว่าเครือข่าย")
                say("  ที่ใช้อยู่บล็อก Cloudflare ไว้ ลองเปลี่ยนเน็ต/ปิด VPN แล้วรันใหม่")
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
