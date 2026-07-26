/* ============================================================
   app.js — NEBULA Stock Intelligence (SPA)
   จัดการ routing, เรียก API, render ทุกหน้า
   ============================================================ */

// ---------------- helpers ----------------
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; };

async function api(path, opts = {}) {
  const o = { headers: { 'Content-Type': 'application/json' }, ...opts };
  if (o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
  const r = await fetch('/api' + path, o);
  return r.json();
}

function toast(msg, ms = 2800) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), ms);
}

const loader = (text = 'กำลังโหลดข้อมูล…') => `<div class="loader"><div class="spinner"></div><span>${text}</span></div>`;
const emptyState = (ic, text) => `<div class="empty"><div class="ic">${ic}</div>${text}</div>`;

// number formatting
const nf = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const pf = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? '—' : (n >= 0 ? '+' : '') + nf(n, d) + '%';
function bigNum(n) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const a = Math.abs(n);
  if (a >= 1e12) return (n/1e12).toFixed(2) + 'T';
  if (a >= 1e9) return (n/1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (n/1e6).toFixed(2) + 'M';
  if (a >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return nf(n, 0);
}
const cls = (n) => (n === null || n === undefined || isNaN(n)) ? '' : (n > 0 ? 'up' : (n < 0 ? 'down' : ''));
const arrow = (n) => n > 0 ? '▲' : (n < 0 ? '▼' : '·');
// แปลง roe/margin/dividend ที่อาจเป็นทศนิยม (0.15) เป็น %
const asPct = (v) => v === null || v === undefined ? null : (Math.abs(v) < 5 ? v * 100 : v);
const asDE = (v) => v === null || v === undefined ? null : (v > 10 ? v / 100 : v);

// ---------------- nav ----------------
const NAV = [
  { id: 'dashboard', label: 'หน้าแรก',    ic: '🛰️', bottom: true  },
  { id: 'chart',     label: 'กราฟ',       ic: '📊',  bottom: true  },
  { id: 'screener',  label: 'คัดกรอง',    ic: '🔎',  bottom: true  },
  { id: 'analyze',   label: 'วิเคราะห์',  ic: '📈',  bottom: true  },
  { id: 'globe',     label: 'ลูกโลกข่าว', ic: '🌍',  bottom: false },
  { id: 'learn',     label: 'เครื่องเรียนรู้', ic: '🧠', bottom: false },
  { id: 'crisis',    label: 'บทเรียนวิกฤต', ic: '⚠️',  bottom: false },
  { id: 'lab',       label: 'แล็บกลยุทธ์', ic: '🧪',  bottom: false },
  { id: 'tools',     label: 'เครื่องมือ', ic: '🧰',  bottom: false },
  { id: 'selfcheck', label: 'ตรวจระบบ',   ic: '🩺',  bottom: false },
  { id: 'report',    label: 'รายงานวันนี้',ic: '📰', bottom: false },
];

function renderNav() {
  $('#sideNav').innerHTML = NAV.map(n =>
    `<div class="nav-item" data-go="${n.id}"><span class="ic">${n.ic}</span><span>${n.label}</span></div>`).join('');
  $('#bottomNav').innerHTML = NAV.filter(n => n.bottom).map(n =>
    `<div class="bn-item" data-go="${n.id}"><span class="ic">${n.ic}</span><span>${n.label}</span></div>`).join('');
}

// ---------------- router ----------------
const routes = window.routes = {};
let currentMarket = 'th';

function go(view, param) {
  location.hash = param ? `#${view}/${encodeURIComponent(param)}` : `#${view}`;
}

function router() {
  // Cleanup previous view (e.g. chart mode cleans up LWC)
  if (window._viewCleanup) { try { window._viewCleanup(); } catch(e) {} window._viewCleanup = null; }

  const [, raw] = location.hash.split('#');
  const [view = 'dashboard', param] = (raw || 'dashboard').split('/');
  $$('.nav-item, .bn-item').forEach(n => n.classList.toggle('active', n.dataset.go === view));
  const fn = routes[view] || routes.dashboard;
  const app = $('#app');
  app.innerHTML = loader();
  fn(app, param ? decodeURIComponent(param) : undefined);
  window.scrollTo(0, 0);
}

// ============================================================
//  VIEW: Dashboard
// ============================================================
routes.dashboard = async (app) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">ภาพรวมตลาด</div>
      <div class="page-sub">สรุปทุกอย่างในหน้าเดียว · ${new Date().toLocaleDateString('th-TH', {weekday:'long', day:'numeric', month:'long', year:'numeric'})}</div>

      <div class="grid cols-3" style="margin-bottom:16px">
        <div class="card" id="fgCard"><div class="card-title">Fear &amp; Greed Index</div>${loader('')}</div>
        <div class="card span-2"><div class="card-title">ปัจจัยมหภาค <span class="chips" style="margin:0">
            <span class="chip ${currentMarket==='th'?'active':''}" data-mkt="th">ไทย</span>
            <span class="chip ${currentMarket==='us'?'active':''}" data-mkt="us">สหรัฐ</span></span></div>
          <div id="macroBox">${loader('')}</div></div>
      </div>

      <div class="grid cols-2" style="margin-bottom:16px">
        <div class="card"><div class="card-title">หุ้นเด่นวันนี้ (คะแนนสูงสุด)</div><div id="topBuys">${loader('')}</div></div>
        <div class="card"><div class="card-title">ข่าวล่าสุด</div><div id="newsBox">${loader('')}</div></div>
      </div>

      <div class="card">
        <div class="card-title">รายการเฝ้าดู (Watchlist) <button class="btn ghost sm" id="addWatchBtn">+ เพิ่ม</button></div>
        <div id="watchBox">${loader('')}</div>
      </div>
    </div>`;

  $$('.chip[data-mkt]').forEach(c => c.onclick = () => { currentMarket = c.dataset.mkt; router(); });
  $('#addWatchBtn').onclick = async () => {
    const t = prompt('ใส่สัญลักษณ์หุ้น (เช่น PTT.BK หรือ AAPL):'); if (!t) return;
    await api('/watchlist', { method: 'POST', body: { ticker: t } }); toast('เพิ่มแล้ว'); loadWatch();
  };

  // fear & greed
  api(`/fear-greed?market=${currentMarket}`).then(fg => {
    const col = fg.score >= 55 ? 'var(--up)' : fg.score <= 45 ? 'var(--down)' : 'var(--neon-purple)';
    $('#fgCard').innerHTML = `<div class="card-title">Fear &amp; Greed Index</div>
      <div class="fg-meter">
        <div class="fg-score" style="color:${col}">${fg.score}</div>
        <div class="muted">${fg.label}</div>
        <div class="bar-track" style="margin-top:12px"><div class="bar-fill" style="width:${fg.score}%;background:${col}"></div></div>
        <div class="small muted" style="margin-top:10px;text-align:left">
          ${Object.entries(fg.components||{}).map(([k,v])=>`<div class="stat-row"><span class="k">${({momentum:'โมเมนตัม',volatility:'ความผันผวน',safe_haven_gold:'ทองคำ (safe haven)'})[k]||k}</span><span class="v ${cls(v)}">${pf(v)}</span></div>`).join('')}
        </div>
      </div>`;
  });

  // macro
  api(`/macro?market=${currentMarket}`).then(m => {
    $('#macroBox').innerHTML = `<div class="grid cols-4">${m.items.map(it => `
      <div class="card ticker-card" style="padding:12px">
        <div class="nm">${it.label}</div>
        <div class="px">${nf(it.price, 2)}</div>
        <div class="small ${cls(it.change_pct)}">${arrow(it.change_pct)} ${pf(it.change_pct)}</div>
      </div>`).join('')}</div>`;
  });

  // top buys
  api(`/daily-report?market=${currentMarket}&top=5`).then(r => {
    const rows = r.top_buys || [];
    $('#topBuys').innerHTML = rows.length ? rows.map(s => `
      <div class="stat-row ticker-card" data-go="analyze/${s.ticker}" style="cursor:pointer">
        <span><b class="mono">${s.ticker}</b> <span class="muted small">${(s.name||'').slice(0,18)}</span></span>
        <span><span class="pill ${s.total_score>=70?'buy':s.total_score>=45?'hold':'sell'}">${s.total_score}</span></span>
      </div>`).join('') : emptyState('🔍', 'ยังไม่มีหุ้นเข้าเกณฑ์');
    $$('#topBuys [data-go]').forEach(x => x.onclick = () => go('analyze', x.dataset.go.split('/')[1]));
  });

  // news
  api('/news?limit=7').then(n => {
    $('#newsBox').innerHTML = (n.items||[]).map(i => `
      <a class="news-item" href="${i.link}" target="_blank" rel="noopener">
        <div class="nh">${i.title}</div>
        <div class="nm"><span class="pill ${({positive:'pos',negative:'neg',neutral:'neu'})[i.sentiment]}">${({positive:'บวก',negative:'ลบ',neutral:'กลาง'})[i.sentiment]}</span> ${i.source||''}</div>
      </a>`).join('');
  });

  loadWatch();
  async function loadWatch() {
    const w = await api('/watchlist');
    const tickers = (w.watchlist||[]).map(x => x.ticker);
    if (!tickers.length) { $('#watchBox').innerHTML = emptyState('⭐', 'ยังไม่มีหุ้นในรายการเฝ้าดู — กด "เพิ่ม"'); return; }
    const { quotes } = await api('/quotes', { method: 'POST', body: { tickers } });
    $('#watchBox').innerHTML = `<div class="grid cols-4">${quotes.map(q => `
      <div class="card ticker-card" data-t="${q.ticker}">
        <div class="sym">${q.ticker}</div>
        <div class="nm">${(q.name||'').slice(0,20)}</div>
        <div class="px">${nf(q.price)}</div>
        <div class="small ${cls(q.change_pct)}">${arrow(q.change_pct)} ${pf(q.change_pct)}</div>
      </div>`).join('')}</div>`;
    $$('#watchBox [data-t]').forEach(c => c.onclick = () => go('analyze', c.dataset.t));
  }
};

// ============================================================
//  VIEW: Screener
// ============================================================
routes.screener = (app) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">Stock Screener</div>
      <div class="page-sub">สแกนหุ้นไทย 300+ ตัว / US 500+ ตัว ครอบคลุมทุกกลุ่มอุตสาหกรรม</div>
      <div class="card" style="margin-bottom:16px">
        <div class="chips" style="margin-bottom:14px">
          <span class="chip ${currentMarket==='th'?'active':''}" data-mkt="th">หุ้นไทย (SET) 300+</span>
          <span class="chip ${currentMarket==='us'?'active':''}" data-mkt="us">หุ้นสหรัฐ 500+</span>
        </div>
        <div class="form-grid">
          <div><label>P/E สูงสุด</label><input id="pe_max" type="number" placeholder="เช่น 20"></div>
          <div><label>P/E ต่ำสุด</label><input id="pe_min" type="number" placeholder="เช่น 0"></div>
          <div><label>ROE ต่ำสุด (%)</label><input id="roe_min" type="number" placeholder="เช่น 10"></div>
          <div><label>D/E สูงสุด</label><input id="de_max" type="number" placeholder="เช่น 1.5"></div>
          <div><label>ปันผลต่ำสุด (%)</label><input id="dy_min" type="number" placeholder="เช่น 3"></div>
          <div><label>Market Cap ต่ำสุด (B)</label><input id="mcap_min_b" type="number" placeholder="เช่น 1"></div>
          <div><button class="btn" id="runScreen">สแกนทั้งตลาด</button></div>
        </div>
      </div>
      <div class="card"><div id="screenResults">${emptyState('🔎','กด "สแกนทั้งตลาด" เพื่อค้นหาหุ้นนอกสายตา')}</div></div>

      <div class="card" style="margin-top:16px;border-color:var(--neon-purple)">
        <div class="card-title">📊 หา setup Volume Profile ตอนนี้</div>
        <div class="small muted" style="margin-bottom:10px">
          สแกนหาหุ้นที่กำลังเข้า setup VAB/VAR (เบรก/เด้งจาก Value Area) พร้อมจุดเข้า-ออก
          · VP ดึงราคา intraday ต่อตัว จึงสแกนได้ทีละ ~60 ตัว
        </div>
        <div class="chips" style="margin-bottom:12px">
          <span class="chip active" data-vpsrc="watchlist">รายการเฝ้าดู</span>
          <span class="chip" data-vpsrc="us">หุ้นสหรัฐ (60 ตัวแรก)</span>
          <span class="chip" data-vpsrc="th">หุ้นไทย (60 ตัวแรก)</span>
        </div>
        <button class="btn" id="runVpScan">หา setup</button>
        <div id="vpScanResults" style="margin-top:14px"></div>
      </div>
    </div>`;

    let vpSrc = 'watchlist';
    $$('.chip[data-vpsrc]').forEach(c => c.onclick = () => {
      vpSrc = c.dataset.vpsrc;
      $$('.chip[data-vpsrc]').forEach(x => x.classList.toggle('active', x === c));
    });
    $('#runVpScan').onclick = runVpScan;

    async function runVpScan() {
      const btn = $('#runVpScan');
      btn.disabled = true; btn.textContent = 'กำลังสแกน…';
      const el = $('#vpScanResults');
      el.innerHTML = loader('กำลังหา setup (ดึง Volume Profile ต่อตัว อาจใช้เวลาสักครู่)…');
      toast('กำลังสแกน setup — อาจใช้เวลา 30-60 วินาที', 40000);
      try {
        const r = await api('/volume-scan', { method: 'POST', body: { source: vpSrc } });
        btn.disabled = false; btn.textContent = 'หา setup';
        if (!r.hits?.length) {
          el.innerHTML = emptyState('📊', `${r.note || ''}<br>ตอนนี้ไม่มีหุ้นเข้า setup VAB/VAR`);
          return;
        }
        el.innerHTML = `
          <div class="small muted" style="margin-bottom:10px">${r.note} · พบ <b class="up">${r.count}</b> ตัวที่เข้า setup</div>
          <div class="table-scroll"><table class="tbl"><thead><tr>
            <th>หุ้น</th><th>setup</th><th>ราคา</th><th>เข้า</th><th>ตัดขาดทุน</th><th>เป้า</th><th>R:R</th><th>คะแนน+</th>
          </tr></thead>
          <tbody>${r.hits.map(h => `<tr data-t="${h.ticker}">
            <td><b class="mono">${h.ticker}</b></td>
            <td><span class="pill ${h.passes_gate?'buy':'hold'}">${h.setup}</span></td>
            <td>${nf(h.price)}</td>
            <td class="up">${nf(h.levels?.entry)}</td>
            <td class="down">${nf(h.levels?.stop_loss)}</td>
            <td class="up">${nf(h.levels?.target)}</td>
            <td class="mono">${h.risk_reward?('1:'+nf(h.risk_reward,1)):'—'}</td>
            <td class="${h.adjust>0?'up':'muted'}">${h.adjust>0?'+'+nf(h.adjust,1):'—'}</td>
          </tr>`).join('')}</tbody></table></div>
          <div class="small muted" style="margin-top:8px">
            "คะแนน+" = ที่จะบวกเข้าคะแนนรวม · ขีด — คือเข้า setup แต่ไม่ผ่านประตู (R:R ต่ำ/backtest ไม่ผ่าน)
          </div>`;
        $$('#vpScanResults tr[data-t]').forEach(tr => tr.onclick = () => go('analyze', tr.dataset.t));
      } catch (e) {
        btn.disabled = false; btn.textContent = 'หา setup';
        el.innerHTML = emptyState('⚠️', 'สแกนไม่สำเร็จ ลองใหม่');
      }
    }

  $$('.chip[data-mkt]').forEach(c => c.onclick = () => {
    currentMarket = c.dataset.mkt;
    $$('.chip[data-mkt]').forEach(x => x.classList.toggle('active', x === c));
  });
  $('#runScreen').onclick = run;

  async function run() {
    const mktLabel = currentMarket === 'th' ? 'หุ้นไทย 300+ ตัว' : 'หุ้นสหรัฐ 500+ ตัว';
    // แสดง toast + เลื่อนไปผล + อัปเดต button
    const btn = $('#runScreen');
    btn.disabled = true; btn.textContent = 'กำลังสแกน…';
    toast(`กำลังสแกน${mktLabel} อาจใช้เวลา 20-40 วินาที`, 35000);
    const resEl = $('#screenResults');
    resEl.innerHTML = loader(`กำลังสแกน ${mktLabel}…`);
    resEl.scrollIntoView({ behavior: 'smooth', block: 'start' });

    const body = { market: currentMarket };
    ['pe_max','pe_min','roe_min','de_max','dy_min'].forEach(k => {
      const v = $('#' + k)?.value; if (v) body[k] = v;
    });
    const mcapB = $('#mcap_min_b')?.value;
    if (mcapB) body.mcap_min = parseFloat(mcapB) * 1e9;

    try {
      const r = await api('/screener', { method: 'POST', body });
      const scanned = r.scanned || '?';
      btn.disabled = false; btn.textContent = 'สแกนทั้งตลาด';
      if (!r.results?.length) {
        resEl.innerHTML = emptyState('🔍', `สแกน ${scanned} ตัวแล้ว ไม่พบหุ้นที่เข้าเกณฑ์ — ลองผ่อนเงื่อนไข`);
        return;
      }
      toast(`พบ ${r.count} หุ้นจาก ${scanned} ตัว`, 3000);
      resEl.innerHTML = `
        <div class="muted small" style="margin-bottom:10px">
          สแกนแล้ว <b>${scanned}</b> ตัว · พบ <b class="up">${r.count}</b> หุ้นที่เข้าเกณฑ์
        </div>
        <div class="table-scroll"><table class="tbl"><thead><tr>
          <th>หุ้น</th><th>กลุ่ม</th><th>ราคา</th><th>%วันนี้</th>
          <th>P/E</th><th>ROE</th><th>D/E</th><th>ปันผล</th><th>มูลค่าตลาด</th>
        </tr></thead>
        <tbody>${r.results.map(s => `<tr data-t="${s.ticker}">
          <td><b class="mono">${s.ticker}</b><div class="muted small">${(s.name||'').slice(0,22)}</div></td>
          <td><span class="muted small">${(s.sector||'—').slice(0,18)}</span></td>
          <td>${nf(s.price)}</td>
          <td class="${cls(s.change_pct)}">${pf(s.change_pct)}</td>
          <td>${nf(s.pe,1)}</td>
          <td>${nf(asPct(s.roe),1)}%</td>
          <td>${nf(asDE(s.debt_to_equity),2)}</td>
          <td>${nf(asPct(s.dividend_yield),2)}%</td>
          <td>${bigNum(s.market_cap)}</td>
        </tr>`).join('')}</tbody></table></div>`;
      $$('#screenResults tr[data-t]').forEach(tr => tr.onclick = () => go('analyze', tr.dataset.t));
    } catch(e) {
      btn.disabled = false; btn.textContent = 'สแกนทั้งตลาด';
      resEl.innerHTML = emptyState('⚠️', 'เกิดข้อผิดพลาด กรุณาลองใหม่');
    }
  }
};

// ============================================================
//  VIEW: Analyze (รายตัว) — overview + tabs
// ============================================================
routes.analyze = async (app, ticker) => {
  if (!ticker) {
    app.innerHTML = `<div class="view active"><div class="page-title">วิเคราะห์หุ้น</div>
      <div class="page-sub">พิมพ์ชื่อหุ้นในช่องค้นหาด้านบน หรือเลือกจากตัวอย่าง</div>
      <div class="card"><div id="examples">${loader('')}</div></div></div>`;
    const d = await api('/defaults');
    $('#examples').innerHTML = `<div class="chips">${[...d.th, ...d.us].map(t => `<span class="chip" data-t="${t}">${t}</span>`).join('')}</div>`;
    $$('#examples .chip').forEach(c => c.onclick = () => go('analyze', c.dataset.t));
    return;
  }

  app.innerHTML = `<div class="view active" id="analyzeView">${loader('กำลังวิเคราะห์ '+ticker+' …')}</div>`;
  const score = await api('/score/' + encodeURIComponent(ticker));
  if (!score || score.price === null || score.error) {
    const isTH = ticker.toUpperCase().endsWith('.BK');
    const hint = isTH ? '' : ' — หุ้นไทยลงท้าย .BK เช่น PTT.BK, หุ้นสหรัฐใช้สัญลักษณ์ตรงๆ เช่น AAPL';
    $('#analyzeView').innerHTML = emptyState('⚠️', `ไม่พบข้อมูลหุ้น ${ticker}${hint}`);
    return;
  }
  const b = score.breakdown, lv = score.levels || {};
  const recCls = score.total_score>=70?'buy':score.total_score>=45?'hold':'sell';

  $('#analyzeView').innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:8px">
      <div>
        <div class="page-title">${score.name} <span class="muted mono" style="font-size:18px">${score.ticker}</span></div>
        <div class="stat-big">${nf(score.price)} <span class="muted small">${score.currency||''}</span></div>
      </div>
      <button class="btn ghost sm" id="watchAdd">⭐ เพิ่มเฝ้าดู</button>
    </div>

    <div class="grid cols-3" style="margin:16px 0">
      <div class="card" style="display:flex;gap:18px;align-items:center">
        ${scoreRing(score.total_score)}
        <div><div class="card-title" style="margin:0">คะแนนรวม</div>
          <div class="pill ${recCls}" style="font-size:14px;margin-top:6px">${score.recommendation}</div>
          <div class="small muted" style="margin-top:8px">พื้นฐาน · เทคนิคัล · ข่าว</div></div>
      </div>
      <div class="card">
        <div class="card-title">องค์ประกอบคะแนน</div>
        ${scoreBar('พื้นฐาน', b.fundamental)}${scoreBar('เทคนิคัล', b.technical)}${scoreBar('Sentiment', b.sentiment)}
        ${catalystRow(score)}
      </div>
      <div class="card">
        <div class="card-title">แผนเทรด</div>
        <div class="stat-row"><span class="k">จุดเข้า</span><span class="v up">${nf(lv.entry)}</span></div>
        <div class="stat-row"><span class="k">ตัดขาดทุน</span><span class="v down">${nf(lv.stop_loss)}</span></div>
        <div class="stat-row"><span class="k">เป้าราคา</span><span class="v up">${nf(lv.target)}</span></div>
        <div class="stat-row"><span class="k">Risk:Reward</span><span class="v">1 : ${nf(lv.risk_reward,1)}</span></div>
      </div>
    </div>

    <div class="tabs" id="aTabs">
      <div class="tab active" data-tab="overview">ภาพรวม</div>
      <div class="tab" data-tab="technical">เทคนิคัล</div>
      <div class="tab" data-tab="fundamental">พื้นฐาน</div>
      <div class="tab" data-tab="volume">Volume Profile</div>
      <div class="tab" data-tab="news">ข่าว &amp; Sentiment</div>
      <div class="tab" data-tab="institutional">เงินสถาบัน</div>
    </div>
    <div id="tabBody"></div>`;

  $('#watchAdd').onclick = async () => { await api('/watchlist', { method: 'POST', body: { ticker } }); toast('เพิ่มเข้ารายการเฝ้าดูแล้ว'); };
  $$('#aTabs .tab').forEach(t => t.onclick = () => { $$('#aTabs .tab').forEach(x => x.classList.toggle('active', x===t)); loadTab(t.dataset.tab); });
  loadTab('overview');

  function loadTab(tab) {
    const body = $('#tabBody'); body.innerHTML = loader('');
    if (tab === 'overview') renderOverview(body, score);
    if (tab === 'technical') renderTechnical(body, ticker);
    if (tab === 'fundamental') renderFundamental(body, ticker);
    if (tab === 'volume') renderVolumeProfile(body, ticker);
    if (tab === 'news') renderNews(body, ticker);
    if (tab === 'institutional') renderInstitutional(body, ticker);
  }
};

function renderOverview(body, score) {
  body.innerHTML = `<div class="grid cols-2">
    <div class="card"><div class="card-title">จุดเด่นพื้นฐาน</div>
      ${(score.fundamental_notes||[]).map(n => `<div class="sig-item"><div class="dot ${n.ok?'buy':'sell'}"></div><div>${n.text}</div></div>`).join('') || '<div class="muted small">ข้อมูลพื้นฐานไม่พอ</div>'}</div>
    <div class="card"><div class="card-title">สัญญาณเทคนิคัล</div>
      ${(score.technical_signals||[]).map(s => `<div class="sig-item"><div class="dot ${s.signal==='ซื้อ'?'buy':s.signal==='ขาย'?'sell':'hold'}"></div><div><b>${s.name}</b> — ${s.desc}</div></div>`).join('') || '<div class="muted small">ไม่มีสัญญาณ</div>'}</div>
  </div>`;
}

async function renderTechnical(body, ticker) {
  body.innerHTML = `
    <div class="chips" id="periodChips">
      ${['3mo','6mo','1y','2y','5y'].map((p,i)=>`<span class="chip ${p==='1y'?'active':''}" data-p="${p}">${({'3mo':'3 เดือน','6mo':'6 เดือน','1y':'1 ปี','2y':'2 ปี','5y':'5 ปี'})[p]}</span>`).join('')}
    </div>
    <div class="card" style="margin-bottom:16px"><div class="card-title">ราคา + เส้นค่าเฉลี่ย + Bollinger Bands</div><div class="chart-box tall"><canvas id="cPrice"></canvas></div></div>
    <div class="grid cols-2">
      <div class="card"><div class="card-title">RSI (14)</div><div class="chart-box mid"><canvas id="cRsi"></canvas></div></div>
      <div class="card"><div class="card-title">MACD</div><div class="chart-box mid"><canvas id="cMacd"></canvas></div></div>
    </div>
    <div class="card" style="margin-top:16px"><div class="card-title">สรุปสัญญาณ</div><div id="techSig"></div></div>`;
  $$('#periodChips .chip').forEach(c => c.onclick = () => { $$('#periodChips .chip').forEach(x=>x.classList.toggle('active',x===c)); load(c.dataset.p); });
  load('1y');
  async function load(period) {
    const t = await api(`/technical/${encodeURIComponent(ticker)}?period=${period}`);
    if (!t.ok) { $('#techSig').innerHTML = emptyState('⚠️', t.error||'ไม่มีข้อมูล'); return; }
    priceChart('cPrice', t.indicators); rsiChart('cRsi', t.indicators); macdChart('cMacd', t.indicators);
    $('#techSig').innerHTML = (t.signals||[]).map(s => `<div class="sig-item"><div class="dot ${s.signal==='ซื้อ'?'buy':s.signal==='ขาย'?'sell':'hold'}"></div>
      <div><b>${s.name}</b> <span class="pill ${s.signal==='ซื้อ'?'buy':s.signal==='ขาย'?'sell':'hold'}">${s.signal}</span><div class="muted small">${s.desc}</div></div></div>`).join('');
  }
}

async function renderFundamental(body, ticker) {
  const f = await api('/fundamental/' + encodeURIComponent(ticker));
  const q = f.quote || {}, g = f.growth || {};
  const fin = f.financials || {};
  body.innerHTML = `
    <div class="grid cols-3" style="margin-bottom:16px">
      <div class="card"><div class="card-title">มูลค่า (Valuation)</div>
        ${row('P/E', nf(q.pe,2))}${row('Forward P/E', nf(q.forward_pe,2))}${row('P/B', nf(q.pb,2))}${row('EPS', nf(q.eps,2))}</div>
      <div class="card"><div class="card-title">คุณภาพ &amp; กำไร</div>
        ${row('ROE', nf(asPct(q.roe),1)+'%')}${row('อัตรากำไรสุทธิ', nf(asPct(q.profit_margin),1)+'%')}${row('D/E', nf(asDE(q.debt_to_equity),2))}${row('Beta', nf(q.beta,2))}</div>
      <div class="card"><div class="card-title">การเติบโต &amp; ปันผล</div>
        ${row('รายได้โต (CAGR)', g.revenue_cagr!=null?pf(g.revenue_cagr):'—')}${row('กำไรโต (CAGR)', g.net_income_cagr!=null?pf(g.net_income_cagr):'—')}${row('ปันผล', nf(asPct(q.dividend_yield),2)+'%')}${row('มูลค่าตลาด', bigNum(q.market_cap))}</div>
    </div>
    <div class="card" style="margin-bottom:16px"><div class="card-title">งบการเงินย้อนหลัง (รายได้ vs กำไรสุทธิ)</div>
      <div class="chart-box mid"><canvas id="cFin"></canvas></div></div>
    <div class="card"><div class="card-title">เปรียบเทียบคู่แข่งในกลุ่ม
      <button class="btn ghost sm" id="cmpBtn">+ เพิ่มหุ้นเทียบ</button></div>
      <div id="cmpBox"><div class="muted small">เพิ่มหุ้นเพื่อเปรียบเทียบ side-by-side</div></div></div>`;

  // financial bar chart
  const years = fin.years || [];
  const rev = pickFin(fin.income, ['Total Revenue','Operating Revenue']);
  const ni = pickFin(fin.income, ['Net Income','Net Income Common Stockholders']);
  if (years.length && (rev||ni)) {
    setTimeout(() => {
      const elc = document.getElementById('cFin'); if (!elc) return;
      new Chart(elc, { type:'bar', data:{ labels: years, datasets:[
        { label:'รายได้', data: rev||[], backgroundColor:'rgba(40,224,255,.55)', borderRadius:6 },
        { label:'กำไรสุทธิ', data: ni||[], backgroundColor:'rgba(160,107,255,.6)', borderRadius:6 },
      ]}, options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'top'}},
        scales:{ x:{grid:{color:'rgba(120,130,255,.08)'}}, y:{grid:{color:'rgba(120,130,255,.08)'}, ticks:{callback:v=>bigNum(v)}} } } });
    }, 50);
  } else {
    $('#cFin').closest('.card').querySelector('.chart-box').innerHTML = `<div class="muted small" style="padding:20px">ไม่มีข้อมูลงบการเงิน</div>`;
  }

  $('#cmpBtn').onclick = async () => {
    const t = prompt('ใส่สัญลักษณ์หุ้นที่ต้องการเทียบ (คั่นด้วยจุลภาค):', ticker);
    if (!t) return;
    $('#cmpBox').innerHTML = loader('');
    const tickers = t.split(',').map(x=>x.trim()).filter(Boolean);
    const r = await api('/compare', { method:'POST', body:{ tickers } });
    $('#cmpBox').innerHTML = `<div class="table-scroll"><table class="tbl"><thead><tr>
      <th>หุ้น</th><th>ราคา</th><th>P/E</th><th>P/B</th><th>ROE</th><th>D/E</th><th>กำไร%</th><th>ปันผล</th><th>คะแนน</th></tr></thead>
      <tbody>${r.rows.map(s=>`<tr data-t="${s.ticker}"><td><b class="mono">${s.ticker}</b></td><td>${nf(s.price)}</td>
        <td>${nf(s.pe,1)}</td><td>${nf(s.pb,2)}</td><td>${nf(asPct(s.roe),1)}%</td><td>${nf(asDE(s.debt_to_equity),2)}</td>
        <td>${nf(asPct(s.profit_margin),1)}%</td><td>${nf(asPct(s.dividend_yield),2)}%</td>
        <td><span class="pill ${s.fund_score>=65?'buy':s.fund_score>=45?'hold':'sell'}">${s.fund_score}</span></td></tr>`).join('')}</tbody></table></div>`;
    $$('#cmpBox tr[data-t]').forEach(tr=>tr.onclick=()=>go('analyze',tr.dataset.t));
  };
}

async function renderNews(body, ticker) {
  body.innerHTML = `<div class="grid cols-2">
    <div class="card"><div class="card-title">Sentiment ข่าว</div><div id="sentBox">${loader('')}</div></div>
    <div class="card"><div class="card-title">หัวข้อข่าว</div><div id="newsList">${loader('')}</div></div></div>`;
  const s = await api('/sentiment/' + encodeURIComponent(ticker));
  const col = s.sentiment_score>=55?'var(--up)':s.sentiment_score<=45?'var(--down)':'var(--neon-purple)';
  $('#sentBox').innerHTML = `<div class="fg-meter"><div class="fg-score" style="color:${col}">${s.sentiment_score}</div>
    <div class="muted">คะแนน Sentiment (0-100)</div>
    <div class="bar-track" style="margin-top:12px"><div class="bar-fill" style="width:${s.sentiment_score}%;background:${col}"></div></div>
    <div class="grid cols-3" style="margin-top:16px">
      <div><div class="stat-big up">${s.summary.positive}</div><div class="small muted">ข่าวบวก</div></div>
      <div><div class="stat-big">${s.summary.neutral}</div><div class="small muted">กลาง</div></div>
      <div><div class="stat-big down">${s.summary.negative}</div><div class="small muted">ข่าวลบ</div></div></div></div>`;
  $('#newsList').innerHTML = (s.headlines||[]).map(i => `<a class="news-item" href="${i.link}" target="_blank" rel="noopener">
    <div class="nh">${i.title}</div><div class="nm"><span class="pill ${({positive:'pos',negative:'neg',neutral:'neu'})[i.sentiment]}">${({positive:'บวก',negative:'ลบ',neutral:'กลาง'})[i.sentiment]}</span> ${i.source||''}</div></a>`).join('');
}

async function renderInstitutional(body, ticker) {
  const d = await api('/institutional/' + encodeURIComponent(ticker));
  if (!d.ok) { body.innerHTML = emptyState('🏦', d.error || 'ไม่มีข้อมูลผู้ถือหุ้นสถาบัน/insider สำหรับหุ้นตัวนี้'); return; }
  const insSum = d.insider_summary || {};
  body.innerHTML = `<div class="grid cols-2">
    <div class="card"><div class="card-title">ผู้ถือหุ้นสถาบัน</div>
      ${(d.institutional||[]).length ? `<div class="table-scroll"><table class="tbl"><thead><tr><th>สถาบัน</th><th>หุ้น</th><th>%</th></tr></thead>
        <tbody>${d.institutional.map(h=>`<tr><td>${h.holder||'—'}</td><td>${bigNum(h.shares)}</td><td>${nf(asPct(h.pct_out),2)}%</td></tr>`).join('')}</tbody></table></div>` : '<div class="muted small">ไม่มีข้อมูล</div>'}</div>
    <div class="card"><div class="card-title">รายการ Insider <span class="pill ${insSum.bias==='ซื้อสุทธิ'?'buy':insSum.bias==='ขายสุทธิ'?'sell':'hold'}">${insSum.bias||'—'}</span></div>
      ${(d.insider||[]).length ? `<div class="table-scroll"><table class="tbl"><thead><tr><th>ผู้บริหาร</th><th>รายการ</th><th>หุ้น</th></tr></thead>
        <tbody>${d.insider.map(h=>`<tr><td>${(h.insider||'—')}<div class="muted small">${h.position||''}</div></td><td>${h.transaction||h.text||'—'}</td><td>${bigNum(h.shares)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="muted small">ไม่มีข้อมูล insider</div>'}</div>
  </div>`;
}

async function renderVolumeProfile(body, ticker) {
  const s = await api('/volume-setup/' + encodeURIComponent(ticker));
  if (!s.ok) { body.innerHTML = emptyState('📊', s.error || 'สร้าง Volume Profile ไม่ได้ (ข้อมูลราคาไม่พอ)'); return; }
  const prof = s.profile || {};
  const setup = s.setup;
  const exp = s.expectancy;

  // สีของกล่องสรุปตามสถานะ setup
  const badge = setup
    ? `<span class="pill buy">พบ setup ${setup}</span>`
    : `<span class="pill hold">ยังไม่เข้า setup</span>`;

  body.innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <div class="card-title">Volume Profile — ${ticker} ${badge}</div>
      <div class="small muted" style="margin-bottom:10px">
        composite ${prof.bars || '—'} แท่ง (${prof.interval || '—'}) ·
        กระจาย volume ตามช่วงราคา = แม่นระดับโซน (ไม่มี tick data)
      </div>
      <div class="grid cols-3" style="gap:10px;margin-bottom:12px">
        ${vpStat('POC (ราคาหนาแน่นสุด)', prof.poc, 'var(--neon-purple)')}
        ${vpStat('ขอบบน Value Area (VAH)', prof.vah, 'var(--up)')}
        ${vpStat('ขอบล่าง Value Area (VAL)', prof.val, 'var(--down)')}
      </div>
      <div id="vpChart" style="height:260px"></div>
    </div>

    <div class="card" style="margin-bottom:14px;border-color:${setup?'var(--up)':'var(--stroke)'}">
      <div class="card-title">สัญญาณ &amp; เหตุผล</div>
      <div class="sig-item"><div>${s.evidence || '—'}</div></div>
      ${!s.trend_ok ? `<div class="small muted" style="margin-top:6px">📉 ต่ำกว่า SMA200 (${nf(s.sma200)}) — ระบบเป็น long-only</div>` : ''}
      ${setup && s.levels ? `
        <div class="grid cols-4" style="margin-top:12px;gap:8px">
          ${vpLevel('จุดเข้า', s.levels.entry, 'up')}
          ${vpLevel('ตัดขาดทุน', s.levels.stop_loss, 'down')}
          ${vpLevel('เป้า', s.levels.target, 'up')}
          ${vpLevel('R:R', '1 : '+nf(s.levels.risk_reward,1), '')}
        </div>` : ''}
    </div>

    ${exp ? `<div class="card">
      <div class="card-title">ความจริงจาก backtest (ไม่โม้)</div>
      <div class="small" style="line-height:1.7">
        setup <b>${setup}</b> — ${exp.note}<br>
        ผลตอบแทนคาดหวังนอกกลุ่มตัวอย่าง: <b class="${cls(exp.oos_r)}">${exp.oos_r>0?'+':''}${nf(exp.oos_r,3)}R/ไม้</b>
        (จาก ${bigNum(exp.n)} ไม้)<br>
        <span class="muted">⚠️ ตัวเลขนี้แทบเสมอตัว และในอดีตแพ้ถือ SPY เฉย ๆ —
        VP ช่วยเรื่องวินัย จังหวะเข้า และจุด stop/target ไม่ใช่การันตีกำไร</span>
      </div>
    </div>` : ''}`;

  drawVolumeProfile(prof, setup);
}

function vpStat(label, val, color) {
  return `<div class="card" style="padding:12px">
    <div class="small muted">${label}</div>
    <div class="stat-big" style="font-size:22px;color:${color}">${nf(val)}</div></div>`;
}
function vpLevel(label, val, c) {
  return `<div class="stat-row" style="flex-direction:column;align-items:flex-start;gap:2px">
    <span class="small muted">${label}</span><span class="v ${c}" style="font-size:16px">${typeof val==='number'?nf(val):val}</span></div>`;
}

// วาด Volume Profile เป็นแท่งแนวนอน (histogram) + เส้น POC / Value Area
function drawVolumeProfile(prof, setup) {
  const el = document.getElementById('vpChart');
  if (!el || !prof.histogram) return;
  const hist = prof.histogram;
  const maxV = Math.max(...hist.map(h => h.volume)) || 1;
  const inVA = (p) => prof.val != null && prof.vah != null && p >= prof.val && p <= prof.vah;

  // หา index ของแท่งที่ใกล้ POC / VAH / VAL ที่สุด (เพื่อป้ายไม่ซ้อนกัน)
  const nearestIdx = (t) => t == null ? -1 :
    hist.reduce((best, h, i) => Math.abs(h.price - t) < Math.abs(hist[best].price - t) ? i : best, 0);
  const iPOC = nearestIdx(prof.poc), iVAH = nearestIdx(prof.vah), iVAL = nearestIdx(prof.val);
  const labelFor = { [iPOC]: 'POC', [iVAH]: 'VAH', [iVAL]: 'VAL' };
  const labelCol = { POC: 'var(--neon-purple)', VAH: 'var(--up)', VAL: 'var(--down)' };

  // วาดด้วย HTML bar แนวนอน (เบา ไม่ต้องพึ่ง lib) — ราคาสูงอยู่บน
  el.innerHTML = `<div style="display:flex;flex-direction:column-reverse;gap:1px;height:100%;justify-content:space-between">
    ${hist.map((h, i) => {
      const w = Math.max(2, h.volume / maxV * 100);
      const tag = labelFor[i];
      const col = i === iPOC ? 'var(--neon-purple)' : inVA(h.price) ? 'rgba(99,230,190,.55)' : 'rgba(120,130,255,.22)';
      return `<div style="display:flex;align-items:center;gap:6px;height:${100/hist.length}%">
        <div style="width:74px;text-align:right;font-size:9px;font-family:monospace;color:${tag?labelCol[tag]:'transparent'}">
          ${tag ? tag+' '+nf(h.price,1) : nf(h.price,1)}</div>
        <div style="height:100%;width:${w}%;background:${col};border-radius:2px" title="${nf(h.price,2)} · vol ${bigNum(h.volume)}"></div>
      </div>`;
    }).join('')}
  </div>`;
}

// ============================================================
//  VIEW: Portfolio
// ============================================================
routes.portfolio = async (app) => {
  app.innerHTML = `<div class="view active">
    <div class="page-title">พอร์ตการลงทุน</div>
    <div class="page-sub">บันทึกหุ้นที่ถือ คำนวณกำไร/ขาดทุนแบบ real-time พร้อมวิเคราะห์ความเสี่ยง</div>
    <div id="pSummary">${loader('')}</div>
    <div class="grid cols-2" style="margin:16px 0">
      <div class="card"><div class="card-title">สัดส่วนการถือครอง</div><div class="chart-box mid"><canvas id="cAlloc"></canvas></div></div>
      <div class="card"><div class="card-title">วิเคราะห์ความเสี่ยงพอร์ต</div><div id="riskBox">${loader('')}</div></div>
    </div>
    <div class="card" style="margin-bottom:16px"><div class="card-title">เพิ่มหุ้นเข้าพอร์ต</div>
      <div class="form-grid">
        <div><label>สัญลักษณ์</label><input id="h_ticker" placeholder="PTT.BK"></div>
        <div><label>จำนวนหุ้น</label><input id="h_shares" type="number" placeholder="100"></div>
        <div><label>ราคาซื้อ</label><input id="h_price" type="number" placeholder="35.5"></div>
        <div><label>วันที่ซื้อ</label><input id="h_date" type="date"></div>
        <div><button class="btn" id="addHolding">+ เพิ่ม</button></div>
      </div></div>
    <div class="card"><div class="card-title">รายการหุ้นที่ถือ</div><div id="holdings">${loader('')}</div></div>
  </div>`;

  $('#addHolding').onclick = async () => {
    const body = { ticker: $('#h_ticker').value, shares: $('#h_shares').value, buy_price: $('#h_price').value, buy_date: $('#h_date').value };
    if (!body.ticker || !body.shares || !body.buy_price) { toast('กรอกข้อมูลให้ครบ'); return; }
    await api('/portfolio', { method: 'POST', body }); toast('เพิ่มหุ้นแล้ว'); load();
  };
  load();

  async function load() {
    const p = await api('/portfolio');
    const t = p.totals;
    $('#pSummary').innerHTML = `<div class="grid cols-4">
      <div class="card"><div class="card-title">มูลค่าพอร์ต</div><div class="stat-big">${nf(t.value)}</div></div>
      <div class="card"><div class="card-title">ต้นทุนรวม</div><div class="stat-big">${nf(t.cost)}</div></div>
      <div class="card"><div class="card-title">กำไร/ขาดทุน</div><div class="stat-big ${cls(t.pnl)}">${nf(t.pnl)}</div></div>
      <div class="card"><div class="card-title">ผลตอบแทน</div><div class="stat-big ${cls(t.pnl_pct)}">${pf(t.pnl_pct)}</div></div></div>`;

    if (!p.holdings.length) {
      $('#holdings').innerHTML = emptyState('💼', 'ยังไม่มีหุ้นในพอร์ต — เพิ่มด้านบน');
      $('#riskBox').innerHTML = emptyState('🛡️','เพิ่มหุ้นเพื่อดูความเสี่ยง'); return;
    }
    $('#holdings').innerHTML = `<div class="table-scroll"><table class="tbl"><thead><tr>
      <th>หุ้น</th><th>จำนวน</th><th>ราคาซื้อ</th><th>ราคาปัจจุบัน</th><th>มูลค่า</th><th>กำไร/ขาดทุน</th><th>%</th><th>น้ำหนัก</th><th></th></tr></thead>
      <tbody>${p.holdings.map(h=>`<tr><td><b class="mono">${h.ticker}</b><div class="muted small">${(h.name||'').slice(0,18)}</div></td>
        <td>${nf(h.shares,0)}</td><td>${nf(h.buy_price)}</td><td>${nf(h.current_price)}</td><td>${nf(h.value)}</td>
        <td class="${cls(h.pnl)}">${nf(h.pnl)}</td><td class="${cls(h.pnl_pct)}">${pf(h.pnl_pct)}</td><td>${nf(h.weight,1)}%</td>
        <td><button class="btn ghost sm" data-del="${h.id}">✕</button></td></tr>`).join('')}</tbody></table></div>`;
    $$('#holdings [data-del]').forEach(b => b.onclick = async () => { await api('/portfolio/'+b.dataset.del, { method:'DELETE' }); toast('ลบแล้ว'); load(); });

    doughnut('cAlloc', p.holdings.map(h=>h.ticker), p.holdings.map(h=>h.value));

    const risk = await api('/risk');
    if (risk.ok) {
      $('#riskBox').innerHTML = `<div class="grid cols-2" style="gap:10px">
        ${row('ความผันผวน/ปี', nf(risk.portfolio_volatility,1)+'%')}
        ${row('Beta พอร์ต', nf(risk.portfolio_beta,2))}
        ${row('คะแนนกระจายเสี่ยง', nf(risk.diversification_score,0))}
        ${row('ระดับความเสี่ยง', risk.risk_level)}</div>
        <div style="margin-top:12px">${risk.recommendations.map(r=>`<div class="sig-item"><div class="dot hold"></div><div class="small">${r}</div></div>`).join('')}</div>`;
    } else { $('#riskBox').innerHTML = `<div class="muted small">${risk.message||''}</div>`; }
  }
};

// ============================================================
//  VIEW: AI advisory
// ============================================================
routes.ai = async (app) => {
  const d = await api('/defaults');
  app.innerHTML = `<div class="view active">
    <div class="page-title">AI ที่ปรึกษาการลงทุน</div>
    <div class="page-sub">ถามตอบเรื่องหุ้นได้ พร้อมเหตุผลทุกคำแนะนำ · โหมด: <b>${d.ai_mode}</b></div>
    <div class="card">
      <div class="chat-box" id="chat">
        <div class="msg bot">สวัสดีครับ 👋 ผมคือ AI ที่ปรึกษาหุ้น ลองถามได้เลย เช่น\n• "PTT.BK น่าซื้อไหม"\n• "วิเคราะห์ AAPL ให้หน่อย"\n• "หุ้นตัวนี้ความเสี่ยงเป็นยังไง"</div>
      </div>
      <div class="chips">${['PTT.BK น่าซื้อไหม','วิเคราะห์ AAPL','DELTA.BK ความเสี่ยงสูงไหม'].map(q=>`<span class="chip" data-q="${q}">${q}</span>`).join('')}</div>
      <div class="chat-input">
        <input id="aiInput" placeholder="พิมพ์คำถามเรื่องหุ้น…" />
        <button class="btn" id="aiSend">ส่ง</button>
      </div>
    </div></div>`;

  const chat = $('#chat');
  const send = async (q) => {
    q = (q || $('#aiInput').value).trim(); if (!q) return;
    $('#aiInput').value = '';
    chat.appendChild(el(`<div class="msg user">${q}</div>`)); chat.scrollTop = chat.scrollHeight;
    const thinking = el(`<div class="msg bot"><span class="spinner" style="width:16px;height:16px;display:inline-block;vertical-align:middle"></span> กำลังวิเคราะห์…</div>`);
    chat.appendChild(thinking); chat.scrollTop = chat.scrollHeight;
    const r = await api('/advisory', { method: 'POST', body: { question: q } });
    thinking.remove();
    chat.appendChild(el(`<div class="msg bot">${(r.answer||'ขออภัย ตอบไม่ได้').replace(/</g,'&lt;')}</div>`));
    chat.scrollTop = chat.scrollHeight;
  };
  $('#aiSend').onclick = () => send();
  $('#aiInput').onkeydown = (e) => { if (e.key === 'Enter') send(); };
  $$('#chat ~ .chips .chip, .chip[data-q]').forEach(c => c.onclick = () => send(c.dataset.q));
};

// ============================================================
//  VIEW: Tools (backtest, alerts, risk calc, sector)
// ============================================================
routes.tools = (app) => {
  app.innerHTML = `<div class="view active">
    <div class="page-title">เครื่องมือ</div>
    <div class="page-sub">Backtest · แจ้งเตือน LINE · คำนวณขนาดการลงทุน · Sector Rotation</div>
    <div class="tabs" id="tTabs">
      <div class="tab active" data-tab="backtest">Backtest</div>
      <div class="tab" data-tab="alerts">แจ้งเตือน + LINE</div>
      <div class="tab" data-tab="possize">คำนวณขนาดลงทุน</div>
      <div class="tab" data-tab="sector">Sector Rotation</div>
    </div>
    <div id="toolBody"></div></div>`;
  $$('#tTabs .tab').forEach(t => t.onclick = () => { $$('#tTabs .tab').forEach(x=>x.classList.toggle('active',x===t)); load(t.dataset.tab); });
  load('backtest');
  function load(tab) {
    const b = $('#toolBody');
    if (tab==='backtest') toolBacktest(b);
    if (tab==='alerts') toolAlerts(b);
    if (tab==='possize') toolPosSize(b);
    if (tab==='sector') toolSector(b);
  }
};

function toolBacktest(b) {
  b.innerHTML = `<div class="card" style="margin-bottom:16px">
    <div class="form-grid">
      <div><label>หุ้น</label><input id="bt_ticker" placeholder="PTT.BK"></div>
      <div><label>กลยุทธ์</label><select id="bt_strat">
        <option value="sma_cross">เส้นค่าเฉลี่ยตัดกัน (SMA Cross)</option>
        <option value="rsi">RSI ซื้อถูกขายแพง</option>
        <option value="macd">MACD Cross</option></select></div>
      <div><label>ช่วงเวลา</label><select id="bt_period"><option value="2y">2 ปี</option><option value="5y" selected>5 ปี</option><option value="10y">10 ปี</option></select></div>
      <div><button class="btn" id="bt_run">ทดสอบ</button></div>
    </div></div>
    <div id="btResult">${emptyState('🧪','ตั้งค่าแล้วกด "ทดสอบ"')}</div>`;
  $('#bt_run').onclick = async () => {
    const ticker = $('#bt_ticker').value.trim(); if (!ticker) { toast('ใส่ชื่อหุ้น'); return; }
    $('#btResult').innerHTML = loader('กำลัง backtest…');
    const r = await api('/backtest', { method:'POST', body:{ ticker, strategy: $('#bt_strat').value, period: $('#bt_period').value } });
    if (!r.ok) { $('#btResult').innerHTML = emptyState('⚠️', r.message||'ทำไม่สำเร็จ'); return; }
    $('#btResult').innerHTML = `<div class="grid cols-4" style="margin-bottom:16px">
      <div class="card"><div class="card-title">ผลตอบแทนกลยุทธ์</div><div class="stat-big ${cls(r.total_return_pct)}">${pf(r.total_return_pct)}</div></div>
      <div class="card"><div class="card-title">Buy &amp; Hold</div><div class="stat-big ${cls(r.buyhold_return_pct)}">${pf(r.buyhold_return_pct)}</div></div>
      <div class="card"><div class="card-title">Win Rate</div><div class="stat-big">${nf(r.win_rate,1)}%</div><div class="small muted">${r.num_trades} เทรด</div></div>
      <div class="card"><div class="card-title">Max Drawdown</div><div class="stat-big down">${pf(r.max_drawdown_pct)}</div></div></div>
    <div class="card"><div class="card-title">Equity Curve</div><div class="chart-box tall"><canvas id="cEquity"></canvas></div></div>`;
    equityChart('cEquity', r.curve);
  };
}

async function toolAlerts(b) {
  const d = await api('/defaults');
  b.innerHTML = `<div class="card" style="margin-bottom:16px">
    <div class="card-title">สถานะ LINE: ${d.line_configured ? '<span class="pill buy">เชื่อมต่อแล้ว</span>' : '<span class="pill sell">ยังไม่ตั้งค่า</span>'}
      <button class="btn ghost sm" id="lineTest">ทดสอบส่ง LINE</button></div>
    ${!d.line_configured ? '<div class="muted small">ตั้งค่า LINE_CHANNEL_TOKEN และ LINE_USER_ID ใน environment variable (ดู README) เพื่อรับแจ้งเตือน</div>' : ''}
    <div class="form-grid" style="margin-top:14px">
      <div><label>หุ้น</label><input id="al_ticker" placeholder="PTT.BK"></div>
      <div><label>เงื่อนไข</label><select id="al_cond">
        <option value="above">ราคาทะลุเหนือ</option><option value="below">ราคาต่ำกว่า</option>
        <option value="rsi_above">RSI สูงกว่า</option><option value="rsi_below">RSI ต่ำกว่า</option></select></div>
      <div><label>ค่าเป้าหมาย</label><input id="al_target" type="number" placeholder="40"></div>
      <div><label>โน้ต</label><input id="al_note" placeholder="(ไม่บังคับ)"></div>
      <div><button class="btn" id="al_add">+ ตั้งแจ้งเตือน</button></div>
    </div></div>
    <div class="card"><div class="card-title">รายการแจ้งเตือน <button class="btn ghost sm" id="al_check">ตรวจสอบเดี๋ยวนี้</button></div><div id="alertList">${loader('')}</div></div>`;
  $('#lineTest').onclick = async () => { const r = await api('/line/test', { method:'POST', body:{} }); toast(r.ok ? 'ส่ง LINE สำเร็จ ✓' : ('ส่งไม่สำเร็จ: '+(r.error||r.status))); };
  $('#al_add').onclick = async () => {
    const body = { ticker: $('#al_ticker').value, condition: $('#al_cond').value, target: $('#al_target').value, note: $('#al_note').value };
    if (!body.ticker || !body.target) { toast('กรอกหุ้นและค่าเป้าหมาย'); return; }
    await api('/alerts', { method:'POST', body }); toast('ตั้งแจ้งเตือนแล้ว'); loadAlerts();
  };
  $('#al_check').onclick = async () => { const r = await api('/alerts/check', { method:'POST', body:{ send:true } }); toast(`ตรวจ ${r.checked} รายการ · เข้าเงื่อนไข ${r.triggered.length}`); loadAlerts(); };
  loadAlerts();
  async function loadAlerts() {
    const r = await api('/alerts');
    $('#alertList').innerHTML = r.alerts.length ? `<div class="table-scroll"><table class="tbl"><thead><tr><th>หุ้น</th><th>เงื่อนไข</th><th>เป้า</th><th>สถานะ</th><th></th></tr></thead>
      <tbody>${r.alerts.map(a=>`<tr><td><b class="mono">${a.ticker}</b></td>
        <td>${({above:'ทะลุเหนือ',below:'ต่ำกว่า',rsi_above:'RSI >',rsi_below:'RSI <'})[a.condition]}</td><td>${nf(a.target)}</td>
        <td>${a.active?'<span class="pill hold">รออยู่</span>':'<span class="pill buy">แจ้งแล้ว</span>'}</td>
        <td><button class="btn ghost sm" data-del="${a.id}">✕</button></td></tr>`).join('')}</tbody></table></div>` : emptyState('🔔','ยังไม่มีการแจ้งเตือน');
    $$('#alertList [data-del]').forEach(x=>x.onclick=async()=>{ await api('/alerts/'+x.dataset.del,{method:'DELETE'}); loadAlerts(); });
  }
}

function toolPosSize(b) {
  b.innerHTML = `<div class="card" style="max-width:640px">
    <div class="card-title">คำนวณขนาดการลงทุน (Position Sizing)</div>
    <div class="muted small" style="margin-bottom:14px">บริหารความเสี่ยงต่อการเทรด — กำหนดว่ายอมเสียได้กี่ % ของพอร์ตต่อไม้</div>
    <div class="form-grid">
      <div><label>เงินทุนทั้งหมด</label><input id="ps_acc" type="number" placeholder="100000"></div>
      <div><label>ความเสี่ยงต่อไม้ (%)</label><input id="ps_risk" type="number" value="2"></div>
      <div><label>ราคาเข้า</label><input id="ps_entry" type="number" placeholder="40"></div>
      <div><label>จุดตัดขาดทุน</label><input id="ps_stop" type="number" placeholder="37"></div>
      <div><button class="btn" id="ps_calc">คำนวณ</button></div>
    </div>
    <div id="psResult" style="margin-top:16px"></div></div>`;
  $('#ps_calc').onclick = async () => {
    const r = await api('/risk/position-size', { method:'POST', body:{ account_size:$('#ps_acc').value, risk_pct:$('#ps_risk').value, entry:$('#ps_entry').value, stop_loss:$('#ps_stop').value } });
    if (!r.ok) { $('#psResult').innerHTML = `<div class="muted">${r.message}</div>`; return; }
    $('#psResult').innerHTML = `<div class="grid cols-2" style="gap:10px">
      ${row('จำนวนหุ้นที่ควรซื้อ', '<b>'+nf(r.shares,0)+'</b> หุ้น')}
      ${row('มูลค่าการลงทุน', nf(r.position_value)+' ('+nf(r.position_pct,1)+'% ของพอร์ต)')}
      ${row('เงินเสี่ยงต่อไม้', nf(r.risk_amount))}
      ${row('ความเสี่ยงต่อหุ้น', nf(r.per_share_risk))}</div>`;
  };
}

async function toolSector(b) {
  b.innerHTML = `<div class="chips" id="secMkt">
      <span class="chip ${currentMarket==='th'?'active':''}" data-mkt="th">ไทย</span>
      <span class="chip ${currentMarket==='us'?'active':''}" data-mkt="us">สหรัฐ</span></div>
    <div class="card"><div class="card-title">ผลตอบแทนรายกลุ่มอุตสาหกรรม (1 เดือน)</div>
      <div class="chart-box tall"><canvas id="cSector"></canvas></div><div id="secTbl"></div></div>`;
  $$('#secMkt .chip').forEach(c => c.onclick = () => { currentMarket = c.dataset.mkt; $$('#secMkt .chip').forEach(x=>x.classList.toggle('active',x===c)); load(); });
  load();
  async function load() {
    $('#secTbl').innerHTML = loader('');
    const r = await api('/sectors?market=' + currentMarket);
    barChart('cSector', r.rows.map(x=>x.sector), r.rows.map(x=>x.perf_1m??0), '% 1 เดือน');
    $('#secTbl').innerHTML = `<div class="table-scroll" style="margin-top:12px"><table class="tbl"><thead><tr><th>กลุ่ม</th><th>ตัวแทน</th><th>1 เดือน</th><th>3 เดือน</th></tr></thead>
      <tbody>${r.rows.map(x=>`<tr data-t="${x.symbol}"><td>${x.sector}</td><td class="mono">${x.symbol}</td>
        <td class="${cls(x.perf_1m)}">${pf(x.perf_1m)}</td><td class="${cls(x.perf_3m)}">${pf(x.perf_3m)}</td></tr>`).join('')}</tbody></table></div>`;
    $$('#secTbl tr[data-t]').forEach(tr=>tr.onclick=()=>go('analyze',tr.dataset.t));
  }
}

// ============================================================
//  VIEW: Daily report
// ============================================================
routes.report = async (app) => {
  app.innerHTML = `<div class="view active">
    <div class="page-title">รายงานประจำวัน</div>
    <div class="page-sub">สรุปหุ้นน่าซื้อพร้อมจุดเข้า/ตัดขาดทุน/เป้าราคา + ภาวะตลาด</div>
    <div class="chips" id="repMkt">
      <span class="chip ${currentMarket==='th'?'active':''}" data-mkt="th">ไทย</span>
      <span class="chip ${currentMarket==='us'?'active':''}" data-mkt="us">สหรัฐ</span></div>
    <div id="repBody">${loader('กำลังสแกนตลาด…')}</div></div>`;
  $$('#repMkt .chip').forEach(c => c.onclick = () => { currentMarket = c.dataset.mkt; $$('#repMkt .chip').forEach(x=>x.classList.toggle('active',x===c)); load(); });
  load();
  async function load() {
    $('#repBody').innerHTML = loader('กำลังสแกนตลาด…');
    const r = await api(`/daily-report?market=${currentMarket}&top=5`);
    const fg = r.fear_greed || {};
    $('#repBody').innerHTML = `
      <div class="grid cols-2" style="margin-bottom:16px">
        <div class="card"><div class="card-title">ภาวะตลาด (${r.date})</div>
          <div class="stat-row"><span class="k">Fear &amp; Greed</span><span class="v">${fg.score} · ${fg.label}</span></div>
          <div class="stat-row"><span class="k">สแกนทั้งหมด</span><span class="v">${r.scanned} หุ้น</span></div></div>
        <div class="card"><div class="card-title">ปัจจัยมหภาค</div>
          ${(r.macro||[]).map(m=>`<div class="stat-row"><span class="k">${m.label}</span><span class="v ${cls(m.change_pct)}">${nf(m.price)} (${pf(m.change_pct)})</span></div>`).join('')}</div>
      </div>
      ${(r.world_news||[]).length ? `<div class="card" style="margin-bottom:16px">
        <div class="card-title">🌍 ข่าวโลกที่ผิดปกติที่สุดวันนี้</div>
        ${r.world_news.map(w=>`<div class="stat-row">
          <span><span class="dot" style="background:${w.color}"></span>${w.label}</span>
          <span class="v ${cls(w.deviation)}">${nf(w.tone,2)} <span class="small muted">(${w.deviation>0?'+':''}${nf(w.deviation,2)})</span></span>
        </div>`).join('')}
        <div class="small muted" style="margin-top:8px">Tone เทียบค่าเฉลี่ย 7 วัน · ติดลบ = ข่าวร้าย</div></div>` : ''}

      ${(r.catalysts||[]).length ? `<div class="card" style="margin-bottom:16px">
        <div class="card-title">🧠 หุ้นที่ข่าวโลกกำลังหนุน/กดดัน</div>
        <div class="small muted" style="margin-bottom:8px">จากความสัมพันธ์ที่เครื่องเรียนรู้ไว้</div>
        ${r.catalysts.map(c=>`<div class="ticker-card" data-t="${c.ticker}" style="cursor:pointer;padding:8px 0;border-bottom:1px solid var(--stroke)">
          <div style="display:flex;justify-content:space-between;gap:8px">
            <span><b class="mono">${c.ticker}</b> <span class="muted small">${(c.name||'').slice(0,20)}</span></span>
            <span class="v ${cls(c.adjust)}">${c.adjust>0?'+':''}${nf(c.adjust,1)}</span></div>
          ${(c.reasons||[]).map(t=>`<div class="small muted">· ${t}</div>`).join('')}
        </div>`).join('')}</div>` : ''}

      <div class="card" style="margin-bottom:16px"><div class="card-title">⭐ หุ้นน่าสนใจวันนี้</div>
        ${(r.top_buys||[]).length ? r.top_buys.map(s=>repCard(s)).join('') : emptyState('🔍','ไม่มีหุ้นเข้าเกณฑ์วันนี้')}</div>
      ${(r.watch_avoid||[]).length ? `<div class="card"><div class="card-title">⚠️ ระวัง / คะแนนต่ำ</div>
        ${r.watch_avoid.map(s=>`<div class="stat-row ticker-card" data-t="${s.ticker}" style="cursor:pointer"><span><b class="mono">${s.ticker}</b> ${s.name||''}</span><span class="pill sell">${s.total_score}</span></div>`).join('')}</div>` : ''}`;
    $$('#repBody [data-t]').forEach(x=>x.onclick=()=>go('analyze',x.dataset.t));
  }
  function repCard(s) {
    const lv = s.levels||{};
    return `<div class="card ticker-card" data-t="${s.ticker}" style="margin-bottom:10px;cursor:pointer">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <div><b class="mono" style="font-size:16px">${s.ticker}</b> <span class="muted">${(s.name||'').slice(0,24)}</span>
          <span class="pill ${s.total_score>=70?'buy':'hold'}" style="margin-left:8px">${s.recommendation} · ${s.total_score}</span></div>
        <div class="small">เข้า <b class="up">${nf(lv.entry)}</b> · ตัดขาดทุน <b class="down">${nf(lv.stop_loss)}</b> · เป้า <b class="up">${nf(lv.target)}</b></div>
      </div></div>`;
  }
};

// ---------------- shared render helpers ----------------
function row(k, v) { return `<div class="stat-row"><span class="k">${k}</span><span class="v">${v}</span></div>`; }
function scoreRing(score) {
  const r = 54, c = 2*Math.PI*r, off = c*(1-score/100);
  const col = score>=70?'var(--up)':score>=45?'var(--neon-purple)':'var(--down)';
  return `<div class="score-ring"><svg width="130" height="130">
    <circle cx="65" cy="65" r="${r}" fill="none" stroke="rgba(120,130,255,.12)" stroke-width="10"/>
    <circle cx="65" cy="65" r="${r}" fill="none" stroke="${col}" stroke-width="10" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}" style="filter:drop-shadow(0 0 6px ${col});transition:stroke-dashoffset 1s ease"/>
    </svg><div class="score-val"><div class="num" style="color:${col}">${score}</div><div class="lbl">/ 100</div></div></div>`;
}
function scoreBar(label, val) {
  const col = val>=65?'var(--up)':val>=45?'var(--neon-blue)':'var(--down)';
  return `<div style="margin-bottom:10px"><div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
    <span class="muted">${label}</span><span class="v">${val}</span></div>
    <div class="bar-track"><div class="bar-fill" style="width:${val}%;background:${col}"></div></div></div>`;
}
// แถบ "ข่าวโลก" ในองค์ประกอบคะแนน — โชว์เฉพาะเมื่อเครื่องเรียนรู้หุ้นตัวนี้แล้ว
function catalystRow(score) {
  const c = score.catalyst || {};
  const adj = (score.breakdown || {}).catalyst_adjust || 0;

  if (!c.ok) {
    return `<div class="small muted" style="margin-top:10px;padding-top:10px;border-top:1px solid var(--stroke)">
      🧠 ข่าวโลก: ยังไม่ได้เรียนรู้หุ้นตัวนี้
      <a href="#learn/${encodeURIComponent(score.ticker)}">เรียนรู้เลย →</a></div>`;
  }

  const col = adj > 0 ? 'var(--up)' : adj < 0 ? 'var(--down)' : 'var(--muted)';
  const sign = adj > 0 ? '+' : '';
  return `<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--stroke)">
    <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:6px">
      <span class="muted">🧠 ${c.label || 'ข่าวโลก'}</span>
      <span class="v" style="color:${col}">${sign}${nf(adj, 1)} คะแนน</span>
    </div>
    <div class="small muted">ฐาน ${score.base_score} → รวม ${score.total_score}</div>
    ${(c.reasons || []).map(r => `<div class="small" style="margin-top:6px">· ${r.text}</div>`).join('')}
    <div class="small muted" style="margin-top:6px">
      <a href="#learn/${encodeURIComponent(score.ticker)}">ดูรายละเอียดความสัมพันธ์ →</a></div>
  </div>`;
}

function pickFin(obj, keys) {
  if (!obj) return null;
  for (const k of keys) for (const key in obj) if (key.toLowerCase() === k.toLowerCase()) return obj[key];
  return null;
}

// ---------------- global search ----------------
function initSearch() {
  const inp = $('#globalSearch'), box = $('#searchResults');
  let timer;
  inp.addEventListener('input', () => {
    clearTimeout(timer);
    const q = inp.value.trim();
    if (q.length < 2) { box.classList.remove('show'); return; }
    timer = setTimeout(async () => {
      const r = await api('/search?q=' + encodeURIComponent(q));
      const items = r.results || [];
      box.innerHTML = items.length ? items.map(i => `<div class="sr-item" data-t="${i.symbol}">
        <span class="sym">${i.symbol}</span><span class="muted small">${(i.name||'').slice(0,28)} · ${i.exchange||''}</span></div>`).join('')
        : `<div class="sr-item muted">ไม่พบ — ลองพิมพ์สัญลักษณ์เต็ม เช่น PTT.BK</div>`;
      box.classList.add('show');
      $$('.sr-item[data-t]', box).forEach(x => x.onclick = () => { box.classList.remove('show'); inp.value=''; go('analyze', x.dataset.t); });
    }, 350);
  });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const v = inp.value.trim(); if (v) { box.classList.remove('show'); inp.value=''; go('analyze', v.toUpperCase()); } } });
  document.addEventListener('click', (e) => { if (!e.target.closest('.search-wrap')) box.classList.remove('show'); });
}

// ---------------- stars background ----------------
function initStars() {
  const c = $('#stars'); let html = '';
  for (let i = 0; i < 70; i++) {
    html += `<div class="star" style="left:${Math.random()*100}%;top:${Math.random()*100}%;animation-delay:${Math.random()*4}s;width:${Math.random()*2+1}px;height:${Math.random()*2+1}px"></div>`;
  }
  c.innerHTML = html;
}

function initClock() {
  const tick = () => { $('#clock').textContent = new Date().toLocaleTimeString('th-TH'); };
  tick(); setInterval(tick, 1000);
}

// ---------------- boot ----------------
document.addEventListener('click', (e) => { const n = e.target.closest('[data-go]'); if (n) { e.preventDefault(); go(n.dataset.go); } });
window.addEventListener('hashchange', router);
window.addEventListener('DOMContentLoaded', async () => {
  renderNav(); initStars(); initSearch(); initClock();
  try { const d = await api('/defaults'); $('#aiModeBadge').textContent = 'AI: ' + d.ai_mode; } catch(e) {}
  router();
});
