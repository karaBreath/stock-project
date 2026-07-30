"""
เทรดข่าวโลก — หน้าต่างควบคุมทุกอย่างในที่เดียว

เปิดด้วยการดับเบิลคลิกไอคอนบนหน้าจอ ไม่ต้องพิมพ์คำสั่งใด ๆ
    เปิดโปรแกรม · เปิดให้ดูจากมือถือ · อัปเดต · ตั้งโดเมน · ตรวจระบบ

ออกแบบตามปัญหาที่เจอจริงกับผู้ใช้:
  - หน้าต่างดำที่เด้งแล้วหายไปทำให้ไม่รู้ว่าเกิดอะไรขึ้น -> ที่นี่ทุกอย่างมีสถานะ
    และมีบันทึกให้อ่านย้อนได้ตลอด
  - ต้องพิมพ์คำสั่งใน cmd เป็นด่านที่ผ่านยาก -> เหลือแค่กดปุ่ม
  - ลิงก์ที่ได้จาก tunnel ยาวและคัดลอกยากบนหน้าต่างดำ -> มีปุ่มคัดลอกให้
"""
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

IS_WIN = platform.system() == "Windows"
VENV_PY = BASE / "venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
APP_TITLE = "เทรดข่าวโลก"

BG = "#0b0d1a"
CARD = "#141834"
LINE = "#2a3160"
FG = "#e8ecff"
MUTED = "#98a0c8"
ACCENT = "#4dd4ff"
OK = "#63e6be"
WARN = "#ffd43b"
BAD = "#ff6b81"


def read_env() -> dict:
    out = {}
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def app_port() -> int:
    try:
        return int(read_env().get("PORT") or os.environ.get("PORT") or 5000)
    except ValueError:
        return 5000


def is_up(port: int, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",
                                    timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


class App:
    def __init__(self, root):
        import tkinter as tk
        self.tk = tk
        self.root = root
        self.q = queue.Queue()
        self.procs = {}          # ชื่อกระบวนการ -> Popen
        self.link = ""
        self.port = app_port()

        root.title(APP_TITLE)
        root.configure(bg=BG)
        root.geometry("880x620")
        root.minsize(760, 560)
        self._set_window_icon()

        self._build()
        self.root.after(200, self._drain)
        self.root.after(400, self._tick)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- หน้าตา ----------------
    def _set_window_icon(self):
        try:
            from services import desktop
            ico = desktop.ensure_icon()
            if IS_WIN:
                self.root.iconbitmap(str(ico))
        except Exception:
            pass                                  # ไอคอนไม่ขึ้นไม่ใช่เรื่องคอขาดบาดตาย

    def _card(self, parent, pady=(0, 10)):
        f = self.tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                          highlightthickness=1)
        f.pack(fill="x", padx=14, pady=pady)
        return f

    def _button(self, parent, text, cmd, primary=False, side="left"):
        b = self.tk.Button(
            parent, text=text, command=cmd, relief="flat", cursor="hand2",
            bg=ACCENT if primary else CARD, fg="#04121a" if primary else FG,
            activebackground=ACCENT if primary else LINE,
            font=("Segoe UI", 11, "bold" if primary else "normal"),
            padx=16, pady=9, highlightbackground=LINE, highlightthickness=1)
        b.pack(side=side, padx=5, pady=8)
        return b

    def _build(self):
        tk = self.tk
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(head, text="เทรดข่าวโลก", bg=BG, fg=FG,
                 font=("Segoe UI", 20, "bold")).pack(side="left")
        self.status = tk.Label(head, text="กำลังตรวจสอบ…", bg=BG, fg=MUTED,
                               font=("Segoe UI", 11))
        self.status.pack(side="right")

        row = self._card(self.root)
        self.btn_start = self._button(row, "▶  เปิดโปรแกรม", self.do_start, True)
        self.btn_open = self._button(row, "🌐  เปิดหน้าเว็บ", self.do_open)
        self.btn_stop = self._button(row, "■  ปิดโปรแกรม", self.do_stop)

        row2 = self._card(self.root)
        self._button(row2, "📱  เปิดให้ดูจากมือถือ", self.do_share)
        self._button(row2, "🔗  ตั้งโดเมนตัวเอง", self.do_setup_domain)
        self._button(row2, "⬇  อัปเดตโปรแกรม", self.do_update)
        self._button(row2, "🩺  ตรวจระบบ", self.do_check)
        self._button(row2, "🖥  สร้างไอคอนบนหน้าจอ", self.do_shortcut)

        self.link_card = self._card(self.root)
        self.link_label = tk.Label(
            self.link_card, text="ยังไม่ได้เปิดให้ดูจากมือถือ", bg=CARD, fg=MUTED,
            font=("Consolas", 10), anchor="w", justify="left", wraplength=780)
        self.link_label.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        self.btn_copy = self._button(self.link_card, "คัดลอกลิงก์", self.do_copy,
                                     side="right")
        self.btn_copy.configure(state="disabled")

        logbox = tk.Frame(self.root, bg=CARD, highlightbackground=LINE,
                          highlightthickness=1)
        logbox.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        tk.Label(logbox, text="บันทึกการทำงาน", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=12, pady=(8, 0))
        self.log = tk.Text(logbox, bg="#0a0c18", fg=FG, insertbackground=FG,
                           relief="flat", font=("Consolas", 10), wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=10)
        self.log.configure(state="disabled")

        tk.Label(self.root,
                 text="ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน · "
                      "โปรแกรมทำงานบนเครื่องนี้ ไม่ส่งข้อมูลพอร์ตออกไปไหน",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(pady=(0, 10))

    # ---------------- ระบบข้อความ ----------------
    def say(self, text, tag=""):
        self.q.put(("log", f"{text}\n"))

    def _drain(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log.configure(state="normal")
                    self.log.insert("end", payload)
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "link":
                    self.link = payload
                    self.link_label.configure(text=payload, fg=OK)
                    self.btn_copy.configure(state="normal")
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    def _tick(self):
        """อัปเดตสถานะจริงทุกวินาที ไม่ให้ผู้ใช้ต้องเดาว่าเปิดอยู่ไหม"""
        def check():
            up = is_up(self.port)
            self.root.after(0, lambda: self._set_status(up))
        threading.Thread(target=check, daemon=True).start()
        self.root.after(3000, self._tick)

    def _set_status(self, up):
        if up:
            self.status.configure(text=f"● กำลังทำงาน  ·  127.0.0.1:{self.port}",
                                  fg=OK)
        else:
            self.status.configure(text="○ ยังไม่ได้เปิด", fg=MUTED)

    # ---------------- ตัวช่วยรันคำสั่ง ----------------
    def run_bg(self, name, cmd, on_line=None, cwd=None):
        """รันคำสั่งเบื้องหลังแล้วส่งข้อความออกมาที่บันทึก ไม่ทำให้หน้าต่างค้าง"""
        if name in self.procs and self.procs[name].poll() is None:
            self.say(f"[{name}] กำลังทำงานอยู่แล้ว")
            return
        self.say(f"$ {' '.join(str(c) for c in cmd)}")

        def worker():
            try:
                p = subprocess.Popen(
                    cmd, cwd=str(cwd or BASE), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                    errors="replace", bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if IS_WIN else 0)
            except Exception as e:
                self.say(f"[{name}] เปิดไม่สำเร็จ: {e}")
                return
            self.procs[name] = p
            for line in p.stdout:
                line = line.rstrip()
                if line:
                    self.say(line)
                    if on_line:
                        on_line(line)
            code = p.wait()
            self.say(f"[{name}] จบการทำงาน (code {code})")

        threading.Thread(target=worker, daemon=True).start()

    def py(self):
        return str(VENV_PY) if VENV_PY.exists() else sys.executable

    # ---------------- ปุ่มต่าง ๆ ----------------
    def do_start(self):
        self.say("กำลังเปิดโปรแกรม… (ครั้งแรกอาจใช้เวลา 2-5 นาที)")
        self.run_bg("app", [sys.executable, str(BASE / "launcher.py"),
                            "--no-browser"])
        threading.Thread(target=self._open_when_ready, daemon=True).start()

    def _open_when_ready(self):
        for _ in range(240):
            time.sleep(1)
            if is_up(self.port):
                self.say(f"พร้อมแล้ว — เปิดหน้าเว็บที่ 127.0.0.1:{self.port}")
                webbrowser.open(f"http://127.0.0.1:{self.port}")
                return
        self.say("รอ 4 นาทีแล้วยังไม่พร้อม — ลองกด 'ตรวจระบบ' ดูว่าอะไรขาด")

    def do_open(self):
        if not is_up(self.port):
            self.say("ยังไม่ได้เปิดโปรแกรม — กด 'เปิดโปรแกรม' ก่อน")
            return
        webbrowser.open(f"http://127.0.0.1:{self.port}")

    def do_stop(self):
        stopped = 0
        for name, p in list(self.procs.items()):
            if p.poll() is None:
                try:
                    p.terminate()
                    stopped += 1
                except Exception:
                    pass
        self.say(f"ปิดแล้ว {stopped} กระบวนการ" if stopped
                 else "ไม่มีอะไรทำงานอยู่")
        self.link = ""
        self.link_label.configure(text="ยังไม่ได้เปิดให้ดูจากมือถือ", fg=MUTED)
        self.btn_copy.configure(state="disabled")

    def do_share(self):
        self.say("กำลังเปิดให้ดูจากมือถือ… (ครั้งแรกจะโหลดตัวเชื่อมประมาณ 35 MB)")

        def catch(line):
            if "http" in line and ("/?k=" in line or "trycloudflare" in line
                                   or "https://" in line):
                for token in line.split():
                    if token.startswith("https://"):
                        self.q.put(("link", token))
                        break

        self.run_bg("share", [self.py(), str(BASE / "share.py")], on_line=catch)

    def do_setup_domain(self):
        import tkinter.simpledialog as sd
        host = sd.askstring(APP_TITLE,
                            "อยากให้ลิงก์เป็นอะไร\n(เช่น nebula.twinpatta.com)",
                            parent=self.root)
        if not host:
            return
        self.say(f"กำลังตั้งโดเมน {host}")
        self.say("เบราว์เซอร์จะเปิดหน้า Cloudflare — เลือกโดเมนแล้วกด Authorize")
        self.run_bg("domain", [self.py(), str(BASE / "share.py"),
                               "--setup-domain", host])

    def do_update(self):
        self.say("กำลังดึงโค้ดใหม่จาก GitHub…")
        branch = "claude/stock-trading-project-zjrrcz"
        self.run_bg("update", ["git", "pull", "origin", branch])

    def do_check(self):
        self.say("กำลังตรวจระบบ…")
        self.run_bg("check", [sys.executable, str(BASE / "launcher.py"), "--check"])

    def do_shortcut(self):
        def worker():
            try:
                from services import desktop
                res = desktop.create_shortcut()
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            self.say(res.get("note") if res.get("ok")
                     else f"สร้างไอคอนไม่สำเร็จ: {res.get('error')}")
            if res.get("ok"):
                self.say(f"ไฟล์: {res['path']}")
        threading.Thread(target=worker, daemon=True).start()

    def do_copy(self):
        if not self.link:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.link)
        self.say("คัดลอกลิงก์แล้ว — วางในมือถือได้เลย")

    def on_close(self):
        running = [n for n, p in self.procs.items() if p.poll() is None]
        if running:
            import tkinter.messagebox as mb
            if not mb.askyesno(APP_TITLE,
                               "ยังมีโปรแกรมทำงานอยู่ ปิดทั้งหมดเลยไหม",
                               parent=self.root):
                return
            self.do_stop()
        self.root.destroy()


def main():
    try:
        import tkinter as tk
    except Exception:
        print("เครื่องนี้ไม่มี tkinter — เปิดด้วย start.bat แทนได้")
        return 1
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
