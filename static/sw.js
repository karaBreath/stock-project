/* Service worker แบบเรียบง่าย — network-first เสมอ
   เว็บออนไลน์ทำงานเหมือนเดิมทุกอย่าง (ไม่มีปัญหา cache ค้างหลัง deploy ใหม่
   เพราะทุก request ลองเน็ตก่อน แล้วค่อยอัปเดต cache)
   cache ใช้เฉพาะตอนออฟไลน์ เพื่อให้เปิดแอปแล้วเห็นหน้าเดิมแทนจอขาว */
const CACHE = "nebula-shell-v2";

// ไฟล์แกนหลักของแอป — เก็บล่วงหน้าตอนติดตั้ง เพื่อให้ออฟไลน์ครั้งแรกก็เปิดได้
const CORE = [
  "/",
  "/static/css/style.css",
  "/static/js/charts.js",
  "/static/js/app.js",
  "/static/js/chart-view.js",
  "/static/js/globe-view.js",
  "/static/js/crisis-view.js",
  "/static/js/lab-view.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;      // CDN/ฟอนต์ ปล่อยตามปกติ
  if (url.pathname.startsWith("/api/")) return;    // ข้อมูลสด ห้าม cache

  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: url.pathname === "/" }))
  );
});
