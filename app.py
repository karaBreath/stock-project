"""
Stock Analysis App — Flask entry point

Local:    python app.py  -> http://127.0.0.1:5000
Railway:  gunicorn ผ่าน Procfile (bind 0.0.0.0:$PORT)
"""
import os
import threading
import time

from flask import Flask, render_template

from config import Config
from database import init_db
from routes.api import api


def _start_collector():
    """
    เธรดเบื้องหลังของ 'ตัวเรียนรู้' — เก็บ snapshot ข่าวโลก + ราคา เป็นระยะ
    ยิ่งแอปรันนาน คลังข้อมูลยิ่งโต ความสัมพันธ์ยิ่งแม่น
    ปิดได้ด้วย env LEARN_AUTO=0
    """
    if not Config.LEARN_AUTO:
        return

    def loop():
        # หน่วงตอนเริ่ม เพื่อไม่ให้แย่ง resource ตอนแอปเพิ่งบูต
        time.sleep(20)
        from services import correlation
        while True:
            try:
                res = correlation.snapshot()
                print(f"[learn] snapshot {res.get('day')} -> {res.get('saved')}", flush=True)
            except Exception as e:  # อย่าให้เธรดตายเพราะ network สะดุด
                print(f"[learn] snapshot failed: {e}", flush=True)
            time.sleep(max(300, Config.LEARN_INTERVAL))

    threading.Thread(target=loop, daemon=True, name="learn-collector").start()


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    init_db()
    app.register_blueprint(api)

    # กัน Flask debug reloader สร้างเธรดซ้ำ (โหมด debug จะบูต 2 รอบ)
    if not Config.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _start_collector()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    # service worker ต้องเสิร์ฟจาก root ถึงจะคุมทั้งเว็บได้ (scope "/")
    @app.route("/sw.js")
    def service_worker():
        from flask import send_from_directory
        return send_from_directory(app.static_folder, "sw.js",
                                   mimetype="application/javascript")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Stock Analysis App running at http://0.0.0.0:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=Config.DEBUG)
