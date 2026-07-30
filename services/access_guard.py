"""
ตัวกันคนแปลกหน้าตอนเปิดเว็บออกอินเทอร์เน็ต (Cloudflare Tunnel)

ทำไมต้องมี
----------
เปิด tunnel = ใครก็ตามที่ได้ลิงก์ไป จะเห็น "พอร์ตหุ้น + ไม้ที่ถืออยู่ใน MT5 +
เงินในบัญชี" ของเจ้าของเครื่องทันที ลิงก์ trycloudflare เดาไม่ได้ก็จริง
แต่มันไปโผล่ในประวัติเบราว์เซอร์ แชท และ log ของตัวกลางได้ง่ายมาก
จึงต้องมีกุญแจ ไม่ใช่หวังว่าจะไม่มีใครเดาลิงก์เจอ

กติกาที่ใช้
-----------
- ไม่ตั้ง SHARE_TOKEN = ไม่ล็อกอะไรเลย (ใช้ในเครื่องตัวเองตามปกติ)
- ตั้งแล้ว: คำขอที่มาจากเครื่องตัวเอง (127.0.0.1) ผ่านได้เสมอ ไม่ต้องใส่กุญแจ
  ส่วนคำขอจากข้างนอกต้องมีกุญแจ ผ่าน ?k=... หรือ cookie หรือ header
- ใส่กุญแจถูกครั้งเดียว ระบบจะฝัง cookie ให้ ใช้ต่อได้ทั้งเครื่องนั้น
- /health ปล่อยผ่านเสมอ (ตัวตรวจสุขภาพต้องเรียกได้) แต่ไม่บอกอะไรที่เป็นความลับ
"""
import hmac

from flask import request, redirect, make_response

COOKIE = "nebula_key"
OPEN_PATHS = ("/health",)
# ไฟล์หน้าตาเว็บปล่อยผ่านได้ ไม่มีข้อมูลส่วนตัว และ PWA ต้องโหลดได้ก่อนล็อกอิน
OPEN_PREFIXES = ("/static/", "/sw.js", "/manifest.json", "/favicon")


def _client_is_local() -> bool:
    """
    คำขอนี้มาจากเครื่องเดียวกันไหม

    ⚠️ ห้ามเชื่อ X-Forwarded-For — cloudflared ใส่ค่านี้มาจากอินเทอร์เน็ต
    ใครก็ปลอมได้ ถ้าเชื่อจะกลายเป็นประตูหลังที่เปิดทิ้งไว้
    ดูจาก remote_addr ซึ่งเป็นปลายทางจริงของ socket เท่านั้น
    """
    addr = (request.remote_addr or "").strip()
    return addr in ("127.0.0.1", "::1", "localhost")


def _is_open_path(path: str) -> bool:
    return path in OPEN_PATHS or any(path.startswith(p) for p in OPEN_PREFIXES)


def _given_key() -> str:
    return (request.args.get("k")
            or request.headers.get("X-Nebula-Key")
            or request.cookies.get(COOKIE)
            or "")


def check(token: str):
    """
    คืน None ถ้าให้ผ่าน · คืน response ถ้าต้องบล็อกหรือต้องตั้ง cookie
    เรียกจาก before_request ของแอป
    """
    if not token:
        return None
    if _is_open_path(request.path):
        return None
    if _client_is_local():
        return None

    given = _given_key()
    # เทียบแบบ constant-time กันการเดาทีละตัวอักษรด้วยการจับเวลา
    if given and hmac.compare_digest(given, token):
        if request.args.get("k"):
            # ใส่กุญแจมาทาง URL -> ฝัง cookie แล้วพาไปหน้าสะอาด
            # จะได้ไม่ค้างอยู่ในแถบที่อยู่ ประวัติ หรือ Referer ที่ส่งต่อไปเว็บอื่น
            clean = request.path or "/"
            resp = make_response(redirect(clean))
            resp.set_cookie(COOKIE, token, httponly=True, samesite="Lax",
                            secure=request.is_secure, max_age=60 * 60 * 24 * 30)
            return resp
        return None

    return _locked_response()


def _locked_response():
    html = """<!doctype html>
<html lang="th"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ต้องใช้กุญแจ</title>
<style>
 body{background:#0b0d1a;color:#e8ecff;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
 .box{max-width:420px;padding:32px;text-align:center;background:#141834;border-radius:16px;
      border:1px solid #2a3160}
 h1{font-size:20px;margin:0 0 12px} p{color:#98a0c8;line-height:1.7;margin:0 0 20px}
 input{width:100%;padding:12px;border-radius:10px;border:1px solid #2a3160;background:#0b0d1a;
       color:#e8ecff;font-size:16px;box-sizing:border-box}
 button{margin-top:12px;width:100%;padding:12px;border:0;border-radius:10px;font-size:16px;
        background:#4dd4ff;color:#04121a;font-weight:600;cursor:pointer}
</style>
<div class="box">
  <h1>🔒 หน้านี้ต้องใช้กุญแจ</h1>
  <p>เว็บนี้เปิดจากเครื่องส่วนตัวและมีข้อมูลพอร์ตอยู่ข้างใน<br>ใส่กุญแจที่ได้ตอนเปิด tunnel</p>
  <form method="get"><input name="k" placeholder="วางกุญแจตรงนี้" autofocus>
  <button type="submit">เข้าใช้งาน</button></form>
</div></html>"""
    resp = make_response(html, 401)
    resp.headers["Cache-Control"] = "no-store"
    return resp
