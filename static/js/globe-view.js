/* ============================================================
   globe-view.js — NEBULA
   · routes.globe : ลูกโลก 3D แสดงข่าวทั่วโลกจาก GDELT
   · routes.learn : เครื่องเรียนรู้ หาจุดเชื่อม ข่าวโลก ↔ ราคาหุ้น
   ============================================================ */

// ---------- ไอคอนประจำธีมข่าว (SVG ฝังในไฟล์ ไม่ต้องโหลดจากเน็ต) ----------
const ICON_SVG = {
  // สงคราม — ลูกไฟระเบิดพวยพุ่งขึ้นจากพื้น (เห็ดระเบิด)
  conflict: '<path d="M12 2.2c2.9 0 5 1.8 5 3.8 1.7.4 2.7 1.5 2.7 2.7 0 1.6-1.6 2.7-3.6 2.7H7.9C5.9 11.4 4.3 10.3 4.3 8.7c0-1.2 1-2.3 2.7-2.7 0-2 2.1-3.8 5-3.8z"/>'
          + '<path d="M10.3 11.4c-.2 3-.8 5.2-1.9 7.1M13.7 11.4c.2 3 .8 5.2 1.9 7.1"/>'
          + '<path d="M7.2 21c1.1-1.7 2.8-2.7 4.8-2.7s3.7 1 4.8 2.7"/>'
          + '<path d="M3 21h18"/>',
  // พลังงาน/น้ำมัน — หยดน้ำมัน
  energy: '<path d="M12 2.5S18 9.5 18 13.5a6 6 0 0 1-12 0C6 9.5 12 2.5 12 2.5z"/>',
  // เงินเฟ้อ/ดอกเบี้ย — แบงก์ + เหรียญ
  inflation: '<rect x="2.2" y="5" width="14" height="8.6" rx="1.3"/>'
           + '<circle cx="9.2" cy="9.3" r="2.2"/>'
           + '<path d="M5 7.2v4.2M13.4 7.2v4.2"/>'
           + '<ellipse cx="16.4" cy="17.2" rx="5.4" ry="2.2"/>'
           + '<path d="M11 17.2v2.4c0 1.2 2.4 2.2 5.4 2.2s5.4-1 5.4-2.2v-2.4"/>',
  // การค้า/ภาษี — เรือขนส่งสินค้า
  trade: '<path d="M2.5 16h19l-2.2 5H4.7z"/><path d="M6 16V9.5h12V16"/><path d="M9.5 9.5V6h5v3.5"/>',
  // เทคโนโลยี/ชิป — ไมโครชิป
  tech: '<rect x="7" y="7" width="10" height="10" rx="1.2"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
  // ตลาดหุ้นโลก — แท่งเทียน
  market: '<rect x="4" y="8.5" width="4" height="8" rx="0.8"/><path d="M6 4.5v4M6 16.5v3"/><rect x="15" y="5.5" width="4" height="9" rx="0.8"/><path d="M17 3v2.5M17 14.5v5"/>',
  // ภัยพิบัติ/โรคระบาด — ไวรัส (หนามมีปุ่มปลาย + จุดข้างใน)
  disaster: '<circle cx="12" cy="12" r="5"/>'
          + '<path d="M12 3.4V7M12 17v3.6M3.4 12H7M17 12h3.6M5.9 5.9l2.5 2.5M15.6 15.6l2.5 2.5M18.1 5.9l-2.5 2.5M8.4 15.6l-2.5 2.5"/>'
          + '<circle cx="12" cy="2.6" r="1.1"/><circle cx="12" cy="21.4" r="1.1"/>'
          + '<circle cx="2.6" cy="12" r="1.1"/><circle cx="21.4" cy="12" r="1.1"/>'
          + '<circle cx="10.3" cy="10.6" r="0.9"/><circle cx="13.6" cy="13.3" r="0.9"/>',
  // ผลประกอบการ — เอกสาร + กราฟ
  earnings: '<path d="M6 2.8h9l3.2 3.2V21H6z"/><path d="M9 14.5l2.2-2.2 2.2 2.2 3-3.8"/>',
  // ข่าวไทย — หมุดปักแผนที่
  thailand: '<path d="M12 21.5s6.8-6.6 6.8-11.6a6.8 6.8 0 1 0-13.6 0c0 5 6.8 11.6 6.8 11.6z"/><circle cx="12" cy="9.6" r="2.4"/>',
};

const ICONS_PER_THEME = 2;    // ปักไอคอนกี่จุดต่อธีม (มากกว่านี้จะรก)
const MIN_ICON_SEP_DEG = 14;  // ระยะห่างขั้นต่ำระหว่างไอคอน (องศา) กันซ้อนทับ

function themeIcon(theme, color) {
  const path = ICON_SVG[theme];
  if (!path) return '';
  return `<svg viewBox="0 0 24 24" fill="none" stroke="${color}"
    stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
}

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
        .pointAltitude(barHeight)
        .pointColor(d => d.color)
        .pointRadius(d => d.flagged
          ? 0.13
          : Math.min(0.42, 0.11 + Math.log10(1 + d.count) * 0.11))
        .pointLabel(d => `<div class="globe-tip"><b>${d.name || '—'}</b><br>${d.count} ข่าว</div>`)
        .onPointClick(d => showPointNews(d))
        // ไอคอนธีมลอยอยู่ปลายแท่ง
        .htmlLat(d => d.lat)
        .htmlLng(d => d.lng)
        .htmlAltitude(d => barHeight(d) + 0.02)
        .htmlElement(makeMarker)
        .htmlTransitionDuration(250)
        // ไอคอนที่อยู่ "หลังโลก" ต้องจางลง ไม่ใช่ทะลุออกมา
        .htmlElementVisibilityModifier((el, isVisible) => {
          el.style.opacity = isVisible ? 1 : 0;
          el.style.pointerEvents = isVisible ? 'auto' : 'none';
        })
        // วงกระเพื่อมเน้นจุดที่ข่าวหนาแน่นที่สุด
        .ringColor(d => () => d.color)
        .ringMaxRadius(d => d.maxR)
        .ringPropagationSpeed(1.6)
        .ringRepeatPeriod(1400)
        .ringAltitude(0.006);
      globe.controls().autoRotate = true;
      globe.controls().autoRotateSpeed = 0.45;
      // เริ่มที่มุมมองเอเชียตะวันออกเฉียงใต้ + ซูมให้ลูกโลกเต็มกรอบ
      globe.pointOfView({ lat: 14, lng: 100, altitude: 2.1 }, 0);
      sizeGlobe();
      window.addEventListener('resize', sizeGlobe);
      window._viewCleanup = () => {
        window.removeEventListener('resize', sizeGlobe);
        try { globe._destructor && globe._destructor(); } catch (e) {}
        globe = null;
      };
    }
    const data = pts.map(p => ({ ...p, lng: p.lon }));
    flagTopPerTheme(data);
    globe.pointsData(data);
    // ไอคอนธีมเฉพาะจุดที่ถูกเลือก (ปลายแท่งที่ยื่นสูงกว่าเพื่อน)
    globe.htmlElementsData(data.filter(d => d.flagged));
    // วงกระเพื่อมเฉพาะ 6 จุดที่ข่าวหนาแน่นสุด (มากกว่านี้จะรก)
    globe.ringsData([...data].sort((a, b) => b.count - a.count).slice(0, 6)
      .map(d => ({ ...d, maxR: 3.5 + Math.log10(1 + d.count) * 1.6 })));
  }

  // เลือกจุดที่ข่าวหนาแน่นสุดของแต่ละธีมมาปักไอคอน
  // ข้ามจุดที่อยู่ใกล้ไอคอนเดิมเกินไป เพื่อไม่ให้ไอคอนซ้อนทับกัน
  function flagTopPerTheme(data) {
    const byTheme = {};
    data.forEach(d => {
      d.flagged = false;
      (byTheme[d.theme || '_'] = byTheme[d.theme || '_'] || []).push(d);
    });
    const chosen = [];
    Object.values(byTheme).forEach(arr => {
      let n = 0;
      for (const d of arr.sort((a, b) => b.count - a.count)) {
        if (n >= ICONS_PER_THEME) break;
        if (chosen.some(c => angularDist(c, d) < MIN_ICON_SEP_DEG)) continue;
        d.flagged = true;
        chosen.push(d);
        n++;
      }
    });
  }

  // ระยะเชิงมุมระหว่าง 2 พิกัดบนทรงกลม (องศา) — สูตร haversine
  function angularDist(a, b) {
    const rad = x => x * Math.PI / 180;
    const dLat = rad(a.lat - b.lat), dLng = rad(a.lng - b.lng);
    const h = Math.sin(dLat / 2) ** 2
      + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * Math.asin(Math.min(1, Math.sqrt(h))) * 180 / Math.PI;
  }

  // ความสูงของแท่ง — จุดที่มีไอคอนยื่นสูงกว่าเพื่อน เพื่อให้ไอคอนแยกออกจากผิวโลก
  function barHeight(d) {
    const base = Math.min(0.14, 0.008 + Math.log10(1 + d.count) * 0.045);
    return d.flagged ? base + 0.22 : base;
  }

  // สร้างป้ายไอคอนที่ปลายแท่ง
  function makeMarker(d) {
    const el = document.createElement('div');
    el.className = 'globe-marker';
    el.innerHTML = `
      <div class="gm-badge" style="border-color:${d.color};box-shadow:0 0 12px ${d.color}66">
        ${themeIcon(d.theme, d.color)}
      </div>
      <div class="gm-cap" style="color:${d.color}">${bigNum(d.count)}</div>`;
    el.title = `${d.name || ''} · ${d.count} ข่าว`;
    el.onclick = (e) => { e.stopPropagation(); showPointNews(d); };
    return el;
  }

  function sizeGlobe() {
    const box = $('#globeBox');
    if (!box || !globe) return;
    const w = box.clientWidth || 600;
    // ให้ลูกโลกเต็มความสูงการ์ด (การ์ดถูกยืดตามแผง Tone ข้าง ๆ)
    const h = Math.max(420, Math.min(660, box.clientHeight || Math.round(w * 0.72)));
    globe.width(w).height(h);
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
            <button class="btn ghost" id="lnBT">ทดสอบย้อนหลัง</button>
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

  $('#lnBT').onclick = runBacktest;

  async function runBacktest() {
    const t = ($('#lnTicker').value || '').trim().toUpperCase();
    if (!t) { toast('ใส่สัญลักษณ์หุ้นก่อน'); return; }
    $('#lnResult').innerHTML = `<div class="card">${loader('กำลังทดสอบย้อนหลัง… (แบ่งข้อมูลเรียนรู้/ทดสอบ)')}</div>`;

    const r = await api(`/learn/backtest/${encodeURIComponent(t)}?days=540`);
    if (!r.ok) {
      $('#lnResult').innerHTML = `<div class="card">${emptyState('⚠️', r.error || 'ทดสอบไม่สำเร็จ')}</div>`;
      return;
    }

    const v = r.verdict || {};
    const vCol = { good: 'var(--up)', weak: 'var(--neon-purple)',
                   bad: 'var(--down)', overfit: 'var(--down)' }[v.level] || 'var(--muted)';

    // ไม่เจอสัญญาณ = ไม่มีอะไรให้เทรด
    if (!r.signal) {
      $('#lnResult').innerHTML = `<div class="card" style="margin-bottom:14px">
        <div class="card-title">ผลทดสอบย้อนหลัง ${r.ticker}</div>
        <div style="color:${vCol};font-weight:600;margin-bottom:8px">${v.text || ''}</div>
        ${splitInfo(r)}</div>`;
      return;
    }

    const s = r.signal, oos = r.out_of_sample, ins = r.in_sample, bh = r.buyhold;
    const cell = (val, suffix = '%') =>
      val === null || val === undefined ? '—' : `<span class="${cls(val)}">${nf(val, 1)}${suffix}</span>`;

    $('#lnResult').innerHTML = `
      <div class="card" style="margin-bottom:14px;border-color:${vCol}">
        <div class="card-title">ผลทดสอบย้อนหลัง ${r.ticker}</div>
        <div style="color:${vCol};font-weight:600;line-height:1.6;margin-bottom:10px">${v.text || ''}</div>
        ${splitInfo(r)}
        <div class="small muted" style="margin-top:8px">
          สัญญาณที่เจอจากช่วงเรียนรู้: <b>${s.label}</b> · ถือ ${s.lag} วัน ·
          r=${nf(s.r, 3)} (เกณฑ์ ${nf(s.critical_r, 3)}) · หักค่าธรรมเนียม ${r.fee_pct}% ต่อขา
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">เทียบตัวเลข</div>
        <div class="table-scroll"><table class="tbl">
          <thead><tr>
            <th>ช่วง</th><th>ผลตอบแทน</th><th>ต่อปี</th><th>จำนวนไม้</th>
            <th>แม่น %</th><th>ขาดทุนสูงสุด</th><th>ถือหุ้น %เวลา</th>
          </tr></thead><tbody>
            <tr style="opacity:.55">
              <td>เรียนรู้ (in-sample)<div class="small muted">${r.train.from} → ${r.train.to}</div></td>
              <td>${cell(ins.total_return_pct)}</td><td>${cell(ins.annualized_pct)}</td>
              <td class="mono">${ins.num_trades}</td><td class="mono">${nf(ins.win_rate, 1)}%</td>
              <td>${cell(ins.max_drawdown_pct)}</td><td class="mono">${nf(ins.exposure_pct, 0)}%</td>
            </tr>
            <tr style="font-weight:600">
              <td>ทดสอบ (out-of-sample) ⭐<div class="small muted">${r.test.from} → ${r.test.to}</div></td>
              <td>${cell(oos.total_return_pct)}</td><td>${cell(oos.annualized_pct)}</td>
              <td class="mono">${oos.num_trades}</td><td class="mono">${nf(oos.win_rate, 1)}%</td>
              <td>${cell(oos.max_drawdown_pct)}</td><td class="mono">${nf(oos.exposure_pct, 0)}%</td>
            </tr>
            <tr>
              <td>ซื้อแล้วถือ (ช่วงทดสอบ)</td>
              <td>${cell(bh.total_return_pct)}</td><td>${cell(bh.annualized_pct)}</td>
              <td class="mono">1</td><td class="mono">—</td>
              <td>${cell(bh.max_drawdown_pct)}</td><td class="mono">100%</td>
            </tr>
          </tbody></table></div>
        <div class="small muted" style="margin-top:10px">
          ⭐ <b>เชื่อเฉพาะแถวช่วงทดสอบ</b> — แถวเรียนรู้จะสวยกว่าเสมอเพราะสัญญาณถูกเลือกมาจากข้อมูลชุดนั้น
        </div>
      </div>`;
  }

  function splitInfo(r) {
    return `<div class="small muted">
      แบ่งข้อมูล ${r.days} วัน → เรียนรู้ ${r.train.days} วัน / ทดสอบ ${r.test.days} วัน ·
      ทดสอบ ${r.tested_pairs} คู่สัญญาณ ผ่านเกณฑ์ ${r.passing_count} คู่</div>`;
  }

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
        <div class="small muted" style="margin-bottom:8px">
          ✅ = ผ่านเกณฑ์กันผลบังเอิญ (|r| ≥ ${nf(res.critical_r, 3)}) · แถวจาง = ยังเชื่อไม่ได้
        </div>
        ${linkTable(res.links || [])}
      </div>`;
    loadLearned();
  }

  function linkTable(rows) {
    if (!rows.length) return emptyState('🔍', 'ยังไม่พบความสัมพันธ์');
    return `<div class="table-scroll"><table class="tbl">
      <thead><tr>
        <th>สัญญาณ</th><th>ล่วงหน้า</th><th>r</th><th>n</th><th>แม่น %</th><th>เชื่อได้?</th>
      </tr></thead><tbody>
      ${rows.map(L => `<tr style="${L.significant ? '' : 'opacity:.45'}">
        <td>${L.label}</td>
        <td>${L.lag === 0 ? 'วันเดียวกัน' : L.lag + ' วัน'}</td>
        <td class="mono ${cls(L.r)}">${nf(L.r, 3)}</td>
        <td class="mono">${L.n}</td>
        <td class="mono">${L.hit_rate === null || L.hit_rate === undefined ? '—' : nf(L.hit_rate, 1)}</td>
        <td>${!L.enough_data ? '<span class="muted small">ข้อมูลน้อย</span>'
              : L.significant ? `✅ ${L.strength}`
              : '<span class="muted small">อาจบังเอิญ</span>'}</td>
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
