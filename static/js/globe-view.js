/* ============================================================
   globe-view.js — NEBULA
   · routes.globe : ลูกโลก 3D แสดงข่าวทั่วโลกจาก GDELT
   · routes.learn : เครื่องเรียนรู้ หาจุดเชื่อม ข่าวโลก ↔ ราคาหุ้น
   ============================================================ */

// ---------- lazy loader ของ globe.gl (มี CDN สำรอง) ----------
const GLOBE_CDNS = [
  'https://unpkg.com/globe.gl',
  'https://cdn.jsdelivr.net/npm/globe.gl/dist/globe.gl.min.js',
];

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.onload = resolve;
    s.onerror = () => reject(new Error('load failed: ' + src));
    document.head.appendChild(s);
  });
}

let _globeLibPromise = null;
function ensureGlobeLib() {
  if (window.Globe) return Promise.resolve(true);
  if (_globeLibPromise) return _globeLibPromise;
  _globeLibPromise = (async () => {
    for (const url of GLOBE_CDNS) {
      try {
        await loadScript(url);
        if (window.Globe) return true;
      } catch (e) { /* ลองตัวถัดไป */ }
    }
    return false;
  })();
  return _globeLibPromise;
}

// ============================================================
//  VIEW: ลูกโลกข่าวโลก
// ============================================================
routes.globe = async (app) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">ลูกโลกข่าวโลก 🌍</div>
      <div class="page-sub">ข่าวทั่วโลกจาก GDELT (65 ภาษา) · จุดยิ่งใหญ่ = ข่าวยิ่งเยอะ · คลิกจุดเพื่อดูข่าว</div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">กรองตามธีมข่าว
          <span class="chips" style="margin:0" id="spanChips">
            <span class="chip active" data-span="24h">24 ชม.</span>
            <span class="chip" data-span="3d">3 วัน</span>
            <span class="chip" data-span="7d">7 วัน</span>
          </span>
        </div>
        <div class="chips" id="themeChips">${loader('')}</div>
      </div>

      <div class="grid cols-3" style="margin-bottom:14px">
        <div class="card span-2" style="padding:0;overflow:hidden">
          <div id="globeBox" class="globe-box">${loader('กำลังโหลดลูกโลก…')}</div>
        </div>
        <div class="card">
          <div class="card-title">อุณหภูมิข่าวโลก (Tone)</div>
          <div class="small muted" style="margin-bottom:8px">ติดลบ = ข่าวร้าย · เทียบกับค่าเฉลี่ย 7 วัน</div>
          <div id="signalBox">${loader('')}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-title" id="newsTitle">ข่าวล่าสุดทั่วโลก</div>
        <div id="worldNews">${loader('')}</div>
      </div>
    </div>`;

  let timespan = '24h';
  let activeTheme = '';       // '' = ทุกธีม
  let pointsCache = [];
  let globe = null;

  $$('.chip[data-span]').forEach(c => c.onclick = () => {
    $$('.chip[data-span]').forEach(x => x.classList.remove('active'));
    c.classList.add('active');
    timespan = c.dataset.span;
    loadPoints();
    loadNews();
  });

  // ---- ธีม ----
  const themesRes = await api('/world/themes');
  const themes = themesRes.themes || [];
  $('#themeChips').innerHTML =
    `<span class="chip active" data-theme="">ทั้งหมด</span>` +
    themes.map(t => `<span class="chip" data-theme="${t.key}">
        <span class="dot" style="background:${t.color}"></span>${t.label}</span>`).join('');

  $$('.chip[data-theme]').forEach(c => c.onclick = () => {
    $$('.chip[data-theme]').forEach(x => x.classList.remove('active'));
    c.classList.add('active');
    activeTheme = c.dataset.theme;
    renderPoints();
    loadNews();
  });

  // ---- tone signals ----
  api(`/world/signals?timespan=7d`).then(sig => {
    const rows = sig.rows || [];
    if (!rows.length) { $('#signalBox').innerHTML = emptyState('📡', 'ยังดึงข้อมูล GDELT ไม่ได้'); return; }
    $('#signalBox').innerHTML = rows.map(r => {
      const dev = r.deviation;
      const c = dev === null || dev === undefined ? '' : (dev > 0 ? 'up' : 'down');
      return `<div class="stat-row">
        <span><span class="dot" style="background:${r.color}"></span>${r.label}</span>
        <span class="${c}">${r.tone === null ? '—' : nf(r.tone, 2)}
          <span class="small muted">(${dev === null || dev === undefined ? '—' : (dev > 0 ? '+' : '') + nf(dev, 2)})</span>
        </span>
      </div>`;
    }).join('');
  });

  // ---- points ----
  async function loadPoints() {
    const res = await api(`/world/points?timespan=${timespan}`);
    pointsCache = res.points || [];
    if (!pointsCache.length) {
      $('#globeBox').innerHTML = emptyState('🌐',
        'ยังดึงข้อมูลข่าวจาก GDELT ไม่ได้<br><span class="small">ตรวจสอบอินเทอร์เน็ต แล้วลองใหม่</span>');
      return;
    }
    renderPoints();
  }

  async function renderPoints() {
    const pts = activeTheme ? pointsCache.filter(p => p.theme === activeTheme) : pointsCache;
    const ok = await ensureGlobeLib();

    if (!ok) { renderFallback(pts); return; }

    const box = $('#globeBox');
    if (!globe) {
      box.innerHTML = '';
      globe = Globe()(box)
        .backgroundColor('rgba(0,0,0,0)')
        .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg')
        .showAtmosphere(true)
        .atmosphereColor('#4dd4ff')
        .atmosphereAltitude(0.18)
        .pointAltitude(d => Math.min(0.35, 0.02 + Math.log10(1 + d.count) * 0.06))
        .pointColor(d => d.color)
        .pointRadius(d => Math.min(1.1, 0.18 + Math.log10(1 + d.count) * 0.22))
        .pointLabel(d => `<div class="globe-tip"><b>${d.name || '—'}</b><br>${d.count} ข่าว</div>`)
        .onPointClick(d => showPointNews(d));
      globe.controls().autoRotate = true;
      globe.controls().autoRotateSpeed = 0.45;
      sizeGlobe();
      window.addEventListener('resize', sizeGlobe);
      window._viewCleanup = () => {
        window.removeEventListener('resize', sizeGlobe);
        try { globe._destructor && globe._destructor(); } catch (e) {}
        globe = null;
      };
    }
    globe.pointsData(pts.map(p => ({ ...p, lng: p.lon })));
  }

  function sizeGlobe() {
    const box = $('#globeBox');
    if (!box || !globe) return;
    const w = box.clientWidth || 600;
    globe.width(w).height(Math.max(360, Math.min(520, Math.round(w * 0.72))));
  }

  // fallback เมื่อโหลด globe.gl ไม่ได้ (เช่น ออฟไลน์) — แสดงเป็นรายการจุดร้อน
  function renderFallback(pts) {
    const top = [...pts].sort((a, b) => b.count - a.count).slice(0, 25);
    $('#globeBox').innerHTML = `
      <div style="padding:16px">
        <div class="small muted" style="margin-bottom:10px">
          โหลดลูกโลก 3D ไม่ได้ (ต้องต่อเน็ตเพื่อดึง globe.gl) — แสดงเป็นรายการจุดข่าวแทน
        </div>
        ${top.map(p => `<div class="stat-row">
            <span><span class="dot" style="background:${p.color}"></span>${p.name || '—'}</span>
            <span class="mono">${p.count}</span></div>`).join('') || emptyState('🌐', 'ไม่มีข้อมูล')}
      </div>`;
  }

  function showPointNews(d) {
    $('#newsTitle').textContent = `ข่าวจาก ${d.name || 'จุดที่เลือก'}`;
    const arts = d.articles || [];
    $('#worldNews').innerHTML = arts.length
      ? arts.map(a => `<div class="news-item"><a href="${a.url}" target="_blank" rel="noopener">${a.title}</a></div>`).join('')
      : emptyState('📰', 'ไม่มีลิงก์ข่าวสำหรับจุดนี้');
  }

  // ---- world news list ----
  async function loadNews() {
    $('#worldNews').innerHTML = loader('');
    const qs = activeTheme ? `theme=${activeTheme}&` : '';
    const res = await api(`/world/news?${qs}timespan=${timespan}&limit=15`);
    const items = res.items || [];
    $('#newsTitle').textContent = activeTheme
      ? `ข่าว: ${(themes.find(t => t.key === activeTheme) || {}).label || ''}`
      : 'ข่าวล่าสุดทั่วโลก';
    $('#worldNews').innerHTML = items.length
      ? items.map(a => `<div class="news-item">
          <a href="${a.link}" target="_blank" rel="noopener">${a.title}</a>
          <div class="small muted">${a.source || ''} ${a.country ? '· ' + a.country : ''}</div>
        </div>`).join('')
      : emptyState('📰', 'ยังดึงข่าวไม่ได้');
  }

  loadPoints();
  loadNews();
};


// ============================================================
//  VIEW: เครื่องเรียนรู้ (ข่าวโลก ↔ ราคาหุ้น)
// ============================================================
routes.learn = async (app, ticker) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">เครื่องเรียนรู้ 🧠</div>
      <div class="page-sub">เฝ้าดูข่าวทั่วโลก + ราคาหุ้น แล้วหาว่าอะไรสัมพันธ์กัน · ยิ่งเก็บนาน ยิ่งแม่น</div>

      <div class="grid cols-4" style="margin-bottom:14px" id="statBox">${loader('')}</div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">วิเคราะห์หุ้น</div>
        <div class="form-grid">
          <div>
            <label class="small muted">สัญลักษณ์หุ้น</label>
            <input id="lnTicker" type="text" placeholder="เช่น PTT.BK, AAPL" value="${ticker || ''}" />
          </div>
          <div>
            <label class="small muted">ช่วงข้อมูลย้อนหลัง (วัน)</label>
            <input id="lnDays" type="number" value="180" min="30" max="365" />
          </div>
          <div style="display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap">
            <button class="btn" id="lnRun">ค้นหาความสัมพันธ์</button>
            <button class="btn ghost" id="lnAll">เรียนรู้ทั้ง watchlist</button>
            <button class="btn ghost" id="lnSnap">เก็บข้อมูลเดี๋ยวนี้</button>
          </div>
        </div>
      </div>

      <div id="lnResult"></div>

      <div class="card">
        <div class="card-title">ความสัมพันธ์ที่เรียนรู้ไว้แล้วทั้งหมด</div>
        <div id="lnLearned">${loader('')}</div>
      </div>
    </div>`;

  loadStatus();
  loadLearned();

  $('#lnRun').onclick = runAnalyze;
  $('#lnTicker').onkeydown = (e) => { if (e.key === 'Enter') runAnalyze(); };
  $('#lnSnap').onclick = async () => {
    toast('กำลังเก็บข้อมูล…');
    const r = await api('/learn/snapshot', { method: 'POST' });
    toast(r.ok ? `เก็บแล้ว: ข่าว ${r.saved.news} · มหภาค ${r.saved.macro} · ราคา ${r.saved.price}` : 'เก็บไม่สำเร็จ');
    loadStatus();
  };

  $('#lnAll').onclick = async () => {
    const btn = $('#lnAll');
    btn.disabled = true;
    btn.textContent = 'กำลังเรียนรู้…';
    toast('กำลังเรียนรู้ทุกตัวใน watchlist (อาจใช้เวลาหลายนาที)', 6000);
    const days = parseInt($('#lnDays').value || '180', 10);
    const r = await api('/learn/watchlist', { method: 'POST', body: { days } });
    btn.disabled = false;
    btn.textContent = 'เรียนรู้ทั้ง watchlist';
    toast(r.ok ? `เรียนรู้แล้ว ${r.count} ตัว — คะแนนรวมจะเริ่มใช้สัญญาณข่าวโลก` : 'เรียนรู้ไม่สำเร็จ', 5000);
    loadStatus();
    loadLearned();
  };

  if (ticker) runAnalyze();

  async function loadStatus() {
    const s = await api('/learn/status');
    const o = s.observations || {};
    const card = (t, v, sub) => `<div class="card"><div class="card-title">${t}</div>
        <div class="stat-big">${v}</div><div class="small muted">${sub}</div></div>`;
    $('#statBox').innerHTML =
      card('วันที่เก็บข้อมูล', o.days || 0, o.first_day ? `ตั้งแต่ ${o.first_day}` : 'ยังไม่เริ่มเก็บ') +
      card('จุดข้อมูลสะสม', bigNum(o.rows || 0), `${o.series || 0} ชุดข้อมูล`) +
      card('ความสัมพันธ์ที่พบ', s.correlations || 0, `เข้าเกณฑ์ ${s.strong_links || 0} รายการ`) +
      card('เก็บอัตโนมัติ', s.auto ? 'เปิด' : 'ปิด', `ทุก ${Math.round((s.interval_sec || 3600) / 60)} นาที`);
  }

  async function runAnalyze() {
    const t = ($('#lnTicker').value || '').trim().toUpperCase();
    if (!t) { toast('ใส่สัญลักษณ์หุ้นก่อน'); return; }
    const days = parseInt($('#lnDays').value || '180', 10);
    $('#lnResult').innerHTML = `<div class="card">${loader('กำลังเทียบข่าวโลกกับราคา… (อาจใช้เวลาสักครู่)')}</div>`;

    const res = await api(`/learn/analyze/${encodeURIComponent(t)}?days=${days}`);
    if (!res.ok) {
      $('#lnResult').innerHTML = `<div class="card">${emptyState('⚠️', res.error || 'วิเคราะห์ไม่สำเร็จ')}</div>`;
      return;
    }

    $('#lnResult').innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="card-title">สิ่งที่พบสำหรับ ${res.ticker}</div>
        ${(res.insights || []).map(i => `<div class="sig-item">${i}</div>`).join('')}
        <div class="small muted" style="margin-top:10px">⚠️ ${res.warning}</div>
      </div>
      <div class="card" style="margin-bottom:14px">
        <div class="card-title">ตารางความสัมพันธ์ (เรียงตามความแรง)</div>
        ${linkTable(res.links || [])}
      </div>`;
    loadLearned();
  }

  function linkTable(rows) {
    if (!rows.length) return emptyState('🔍', 'ยังไม่พบความสัมพันธ์');
    return `<div class="table-scroll"><table class="tbl">
      <thead><tr>
        <th>สัญญาณ</th><th>ล่วงหน้า</th><th>r</th><th>n</th><th>แม่น %</th><th>ระดับ</th>
      </tr></thead><tbody>
      ${rows.map(L => `<tr>
        <td>${L.label}</td>
        <td>${L.lag === 0 ? 'วันเดียวกัน' : L.lag + ' วัน'}</td>
        <td class="mono ${cls(L.r)}">${nf(L.r, 3)}</td>
        <td class="mono">${L.n}</td>
        <td class="mono">${L.hit_rate === null || L.hit_rate === undefined ? '—' : nf(L.hit_rate, 1)}</td>
        <td>${L.enough_data ? L.strength : '<span class="muted small">ข้อมูลยังน้อย</span>'}</td>
      </tr>`).join('')}
      </tbody></table></div>`;
  }

  async function loadLearned() {
    const res = await api('/learn/links?limit=40');
    const rows = res.rows || [];
    $('#lnLearned').innerHTML = rows.length ? `
      <div class="table-scroll"><table class="tbl">
        <thead><tr><th>หุ้น</th><th>สัญญาณ</th><th>ล่วงหน้า</th><th>r</th><th>n</th><th>ระดับ</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td><a href="#learn/${encodeURIComponent(r.target)}">${r.target}</a></td>
          <td>${r.label}</td>
          <td>${r.lag === 0 ? 'วันเดียวกัน' : r.lag + ' วัน'}</td>
          <td class="mono ${cls(r.r)}">${nf(r.r, 3)}</td>
          <td class="mono">${r.n}</td>
          <td>${r.strength}</td>
        </tr>`).join('')}</tbody></table></div>`
      : emptyState('🧠', 'ยังไม่มีความสัมพันธ์ที่เก็บไว้ — ลองวิเคราะห์หุ้นสักตัวด้านบน');
  }
};
