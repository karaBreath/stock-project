/* ============================================================
   charts.js — ตัวช่วยวาดกราฟด้วย Chart.js (ธีม neon)
   ============================================================ */
const NEON = {
  blue: '#28e0ff', purple: '#a06bff', pink: '#ff5ec4',
  up: '#2be58b', down: '#ff5b6e', grid: 'rgba(120,130,255,.08)',
  text: '#8b91c4',
};

const _charts = {};

// กันเหนียว: ถ้า CDN ของ Chart.js โหลดไม่สำเร็จ (เน็ตหลุด/ช้า)
// ให้แสดงข้อความแทนกราฟ แทนที่จะ throw จนทั้งหน้าพัง
if (typeof Chart === 'undefined') {
  window.Chart = function (el) {
    const p = el && el.parentElement;
    if (p) p.innerHTML = '<div class="small muted" style="padding:16px">⚠️ โหลดไลบรารีกราฟไม่สำเร็จ — เช็คอินเทอร์เน็ตแล้วรีเฟรชหน้า</div>';
  };
  Chart.prototype.destroy = function () {};
  Chart.defaults = { font: {}, plugins: { legend: { labels: {} } } };
}

Chart.defaults.font.family = "'Sarabun', sans-serif";
Chart.defaults.color = NEON.text;
Chart.defaults.plugins.legend.labels.boxWidth = 12;
Chart.defaults.plugins.legend.labels.usePointStyle = true;

function _destroy(id) {
  if (_charts[id]) { _charts[id].destroy(); delete _charts[id]; }
}

function _grad(ctx, area, c1, c2) {
  const g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
  g.addColorStop(0, c1); g.addColorStop(1, c2);
  return g;
}

const baseScales = {
  x: { grid: { color: NEON.grid }, ticks: { maxTicksLimit: 7, color: NEON.text } },
  y: { grid: { color: NEON.grid }, ticks: { color: NEON.text } },
};

/* ---- กราฟราคา + เส้นค่าเฉลี่ย + Bollinger ---- */
function priceChart(id, ind) {
  _destroy(id);
  const el = document.getElementById(id); if (!el) return;
  const ds = [
    { label: 'ราคา', data: ind.close, borderColor: NEON.blue, borderWidth: 2, pointRadius: 0, tension: .15,
      fill: true, backgroundColor: (c) => { const {ctx, chartArea} = c.chart; return chartArea ? _grad(ctx, chartArea, 'rgba(40,224,255,.25)', 'rgba(40,224,255,0)') : 'transparent'; } },
    { label: 'SMA20', data: ind.sma20, borderColor: NEON.purple, borderWidth: 1.3, pointRadius: 0, tension: .15 },
    { label: 'SMA50', data: ind.sma50, borderColor: NEON.pink, borderWidth: 1.3, pointRadius: 0, tension: .15 },
    { label: 'BB บน', data: ind.bb_upper, borderColor: 'rgba(139,145,196,.4)', borderWidth: 1, pointRadius: 0, borderDash: [4,4] },
    { label: 'BB ล่าง', data: ind.bb_lower, borderColor: 'rgba(139,145,196,.4)', borderWidth: 1, pointRadius: 0, borderDash: [4,4] },
  ];
  _charts[id] = new Chart(el, {
    type: 'line',
    data: { labels: ind.dates, datasets: ds },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: true, position: 'top' } }, scales: baseScales },
  });
}

/* ---- RSI ---- */
function rsiChart(id, ind) {
  _destroy(id); const el = document.getElementById(id); if (!el) return;
  _charts[id] = new Chart(el, {
    type: 'line',
    data: { labels: ind.dates, datasets: [{ label: 'RSI', data: ind.rsi, borderColor: NEON.purple, borderWidth: 1.6, pointRadius: 0, tension: .2 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
      scales: { x: baseScales.x, y: { ...baseScales.y, min: 0, max: 100,
        grid: { color: (c) => (c.tick.value === 30 || c.tick.value === 70) ? 'rgba(255,94,196,.3)' : NEON.grid } } } },
  });
}

/* ---- MACD ---- */
function macdChart(id, ind) {
  _destroy(id); const el = document.getElementById(id); if (!el) return;
  _charts[id] = new Chart(el, {
    data: { labels: ind.dates, datasets: [
      { type: 'bar', label: 'Histogram', data: ind.macd_hist,
        backgroundColor: ind.macd_hist.map(v => v >= 0 ? 'rgba(43,229,139,.5)' : 'rgba(255,91,110,.5)') },
      { type: 'line', label: 'MACD', data: ind.macd, borderColor: NEON.blue, borderWidth: 1.5, pointRadius: 0 },
      { type: 'line', label: 'Signal', data: ind.macd_signal, borderColor: NEON.pink, borderWidth: 1.5, pointRadius: 0 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'top' } }, scales: baseScales },
  });
}

/* ---- sparkline เล็ก ๆ (dashboard) ---- */
function sparkline(id, data, color) {
  _destroy(id); const el = document.getElementById(id); if (!el) return;
  const up = data.length > 1 && data[data.length-1] >= data[0];
  const col = color || (up ? NEON.up : NEON.down);
  _charts[id] = new Chart(el, {
    type: 'line',
    data: { labels: data.map((_,i)=>i), datasets: [{ data, borderColor: col, borderWidth: 1.6, pointRadius: 0, tension: .3,
      fill: true, backgroundColor: (c) => { const {ctx, chartArea} = c.chart; if(!chartArea) return 'transparent'; return _grad(ctx, chartArea, col.replace(')',',.25)').replace('rgb','rgba').replace('#', '#'), 'rgba(0,0,0,0)'); } }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } } },
  });
}

/* ---- doughnut (portfolio allocation) ---- */
function doughnut(id, labels, data) {
  _destroy(id); const el = document.getElementById(id); if (!el) return;
  const palette = ['#28e0ff','#a06bff','#ff5ec4','#2be58b','#ffb454','#5b8cff','#ff5b6e','#54e0c8','#c084fc','#fb7185'];
  _charts[id] = new Chart(el, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: palette, borderColor: '#0a0a1f', borderWidth: 2 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: '64%', plugins: { legend: { position: 'right', labels: { boxWidth: 10, font: { size: 11 } } } } },
  });
}

/* ---- backtest equity curve ---- */
function equityChart(id, curve) {
  _destroy(id); const el = document.getElementById(id); if (!el) return;
  _charts[id] = new Chart(el, {
    type: 'line',
    data: { labels: curve.map(c => c.date), datasets: [
      { label: 'กลยุทธ์', data: curve.map(c => c.strategy), borderColor: NEON.blue, borderWidth: 2, pointRadius: 0, tension: .1 },
      { label: 'ซื้อแล้วถือ (Buy&Hold)', data: curve.map(c => c.buyhold), borderColor: NEON.purple, borderWidth: 1.5, pointRadius: 0, borderDash: [5,4], tension: .1 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: baseScales },
  });
}

/* ---- horizontal bar (sector / comparison) ---- */
function barChart(id, labels, data, label) {
  _destroy(id); const el = document.getElementById(id); if (!el) return;
  _charts[id] = new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [{ label: label||'', data,
      backgroundColor: data.map(v => v >= 0 ? 'rgba(43,229,139,.6)' : 'rgba(255,91,110,.6)'),
      borderColor: data.map(v => v >= 0 ? NEON.up : NEON.down), borderWidth: 1, borderRadius: 6 }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } }, scales: baseScales },
  });
}
