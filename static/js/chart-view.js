/* ============================================================
   chart-view.js — TradingView-like Chart Page
   ต้องโหลด Lightweight Charts v4 ก่อน (ผ่าน CDN ใน index.html)
   ============================================================ */
'use strict';

(function () {

  // ── CONSTANTS ────────────────────────────────────────────────
  const TF_LIST = [
    { label: '1m',  yf: '1m',   period: '5d',   intra: true  },
    { label: '5m',  yf: '5m',   period: '60d',  intra: true  },
    { label: '15m', yf: '15m',  period: '60d',  intra: true  },
    { label: '30m', yf: '30m',  period: '60d',  intra: true  },
    { label: '1H',  yf: '60m',  period: '730d', intra: true  },
    { label: '1D',  yf: '1d',   period: '5y',   intra: false },
    { label: '1W',  yf: '1wk',  period: 'max',  intra: false },
    { label: '1M',  yf: '1mo',  period: 'max',  intra: false },
  ];

  const CHART_TYPES = [
    { id: 'candle', label: 'Candles'     },
    { id: 'ha',     label: 'Heikin Ashi' },
    { id: 'line',   label: 'Line'        },
    { id: 'area',   label: 'Area'        },
    { id: 'bar',    label: 'Bars'        },
  ];

  const DRAW_TOOLS = [
    { id: 'cursor',   icon: '↖', tip: 'เลือก [V]'              },
    { id: 'trendline',icon: '╱', tip: 'เส้นแนวโน้ม [T]'        },
    { id: 'hline',    icon: '—', tip: 'เส้นแนวนอน [H]'         },
    { id: 'vline',    icon: '|', tip: 'เส้นแนวตั้ง'            },
    { id: 'ray',      icon: '→', tip: 'Ray'                     },
    { id: 'fib',      icon: '🌀', tip: 'Fibonacci Retracement [F]' },
    { id: 'rect',     icon: '▭', tip: 'สี่เหลี่ยม [R]'         },
    { id: 'text',     icon: 'T', tip: 'ข้อความ'                },
    { id: 'longpos',  icon: '▲', tip: 'Long Position'           },
    { id: 'shortpos', icon: '▼', tip: 'Short Position'          },
    { id: 'brush',    icon: '✏', tip: 'Brush'                   },
    { id: 'eraser',   icon: '⌫', tip: 'ลบ [Del]'               },
  ];

  const FIB_LEVELS  = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.272, 1.618];
  const FIB_COLORS  = ['#ff5b6e','#ffa500','#ffdd00','#2be58b','#28e0ff','#a06bff','#ff5b6e','#ffa500','#ffdd00'];

  const OVERLAY_INDICATORS = [
    { id: 'EMA',  label: 'EMA',            color: '#ff9800', params: { period: 20 } },
    { id: 'SMA',  label: 'SMA',            color: '#2be58b', params: { period: 50 } },
    { id: 'WMA',  label: 'WMA',            color: '#e040fb', params: { period: 20 } },
    { id: 'DEMA', label: 'DEMA',           color: '#ff5ec4', params: { period: 20 } },
    { id: 'BB',   label: 'Bollinger Bands',color: '#a06bff', params: { period: 20, mult: 2 } },
    { id: 'VWAP', label: 'VWAP',           color: '#ff5ec4', params: {} },
    { id: 'PSAR', label: 'Parabolic SAR',  color: '#ffd600', params: {} },
  ];

  const SUB_INDICATORS = [
    { id: 'volume', label: 'Volume'     },
    { id: 'rsi',    label: 'RSI'        },
    { id: 'macd',   label: 'MACD'       },
    { id: 'stoch',  label: 'Stochastic' },
    { id: 'cci',    label: 'CCI'        },
  ];

  // ── CHART THEME ──────────────────────────────────────────────
  const THEME = {
    layout: { background: { color: '#050510' }, textColor: '#8b91c4' },
    grid: {
      vertLines: { color: 'rgba(120,130,255,0.06)' },
      horzLines: { color: 'rgba(120,130,255,0.06)' },
    },
    crosshair: {
      mode: 1,
      vertLine: { color: 'rgba(120,130,255,0.5)', width: 1, style: 2, labelBackgroundColor: '#1c1e3c' },
      horzLine: { color: 'rgba(120,130,255,0.5)', width: 1, style: 2, labelBackgroundColor: '#1c1e3c' },
    },
    rightPriceScale: { borderColor: 'rgba(120,130,255,0.18)' },
    timeScale: { borderColor: 'rgba(120,130,255,0.18)', timeVisible: true, secondsVisible: false },
  };

  // ── STATE ────────────────────────────────────────────────────
  let mainChart   = null;
  let subChart    = null;
  let mainSeries  = null;
  let volSeries   = null;
  let overlayLines= {};          // key -> series[]
  let activeInds  = {};          // key -> {id,params,color}
  let currentSymbol   = 'PTT.BK';
  let currentTF       = TF_LIST[5];   // 1D default
  let currentType     = 'candle';
  let currentSub      = 'volume';
  let rawData         = [];
  let drawMode        = 'cursor';
  let drawings        = [];
  let drawState       = null;    // in-progress drawing
  let chartWrap       = null;
  let drawCanvas      = null;
  let resizeObs       = null;
  let syncSub         = null;    // cleanup fn for sub-chart sync
  let searchTid       = null;

  // ── MATH ─────────────────────────────────────────────────────
  function ema(prices, p) {
    const k = 2 / (p + 1);
    const out = [prices[0]];
    for (let i = 1; i < prices.length; i++) out.push(prices[i] * k + out[i - 1] * (1 - k));
    return out;
  }

  function sma(prices, p) {
    return prices.map((_, i) => {
      if (i < p - 1) return null;
      let s = 0; for (let j = i - p + 1; j <= i; j++) s += prices[j];
      return s / p;
    });
  }

  function wma(prices, p) {
    const d = p * (p + 1) / 2;
    return prices.map((_, i) => {
      if (i < p - 1) return null;
      let s = 0; for (let j = 0; j < p; j++) s += prices[i - p + 1 + j] * (j + 1);
      return s / d;
    });
  }

  function dema(prices, p) {
    const e1 = ema(prices, p);
    const e2 = ema(e1, p);
    return prices.map((_, i) => 2 * e1[i] - e2[i]);
  }

  function calcBB(data, p, mult) {
    const closes = data.map(d => d.close);
    const smaV = sma(closes, p);
    return data.map((d, i) => {
      if (smaV[i] === null) return null;
      const sl = closes.slice(Math.max(0, i - p + 1), i + 1);
      const sd = Math.sqrt(sl.reduce((s, v) => s + (v - smaV[i]) ** 2, 0) / sl.length);
      return { time: d.time, upper: smaV[i] + mult * sd, mid: smaV[i], lower: smaV[i] - mult * sd };
    }).filter(Boolean);
  }

  function calcRSI(data, p) {
    const closes = data.map(d => d.close);
    const res = [];
    let ag = 0, al = 0;
    for (let i = 1; i <= p; i++) {
      const d = closes[i] - closes[i - 1];
      if (d > 0) ag += d; else al -= d;
    }
    ag /= p; al /= p;
    for (let i = p; i < closes.length; i++) {
      if (i > p) {
        const d = closes[i] - closes[i - 1];
        ag = (ag * (p - 1) + Math.max(0, d)) / p;
        al = (al * (p - 1) + Math.max(0, -d)) / p;
      }
      const rs = al === 0 ? 100 : ag / al;
      res.push({ time: data[i].time, value: 100 - 100 / (1 + rs) });
    }
    return res;
  }

  function calcMACD(data, fast = 12, slow = 26, sig = 9) {
    const closes = data.map(d => d.close);
    const eFast = ema(closes, fast);
    const eSlow = ema(closes, slow);
    const macdLine = closes.map((_, i) => eFast[i] - eSlow[i]);
    const sigLine  = ema(macdLine.slice(slow - 1), sig);
    const offset   = slow - 1;
    const macd = [], signal = [], hist = [];
    for (let i = sig - 1; i < sigLine.length; i++) {
      const di = i + offset;
      macd.push({ time: data[di].time, value: macdLine[di] });
      signal.push({ time: data[di].time, value: sigLine[i] });
      hist.push({ time: data[di].time, value: macdLine[di] - sigLine[i] });
    }
    return { macd, signal, hist };
  }

  function calcStoch(data, k = 14, d = 3) {
    const kVals = [];
    for (let i = k - 1; i < data.length; i++) {
      const sl = data.slice(i - k + 1, i + 1);
      const hi = Math.max(...sl.map(x => x.high));
      const lo = Math.min(...sl.map(x => x.low));
      kVals.push({ time: data[i].time, value: hi === lo ? 50 : ((data[i].close - lo) / (hi - lo)) * 100 });
    }
    const dVals = sma(kVals.map(x => x.value), d);
    const dFull = kVals.map((p, i) => dVals[i] !== null ? { time: p.time, value: dVals[i] } : null).filter(Boolean);
    return { k: kVals, d: dFull };
  }

  function calcCCI(data, p = 20) {
    return data.map((d, i) => {
      if (i < p - 1) return null;
      const sl = data.slice(i - p + 1, i + 1);
      const tps = sl.map(x => (x.high + x.low + x.close) / 3);
      const avg = tps.reduce((s, v) => s + v, 0) / p;
      const md  = tps.reduce((s, v) => s + Math.abs(v - avg), 0) / p;
      const tp  = (d.high + d.low + d.close) / 3;
      return { time: d.time, value: md === 0 ? 0 : (tp - avg) / (0.015 * md) };
    }).filter(Boolean);
  }

  function calcVWAP(data) {
    let cumTP = 0, cumVol = 0;
    return data.map(d => {
      const tp = (d.high + d.low + d.close) / 3;
      cumTP  += tp * (d.volume || 0);
      cumVol += (d.volume || 0);
      return { time: d.time, value: cumVol ? cumTP / cumVol : d.close };
    });
  }

  function calcPSAR(data, step = 0.02, max = 0.2) {
    if (data.length < 2) return [];
    const res = [];
    let bull = true, sar = data[0].low, ep = data[0].high, af = step;
    for (let i = 1; i < data.length; i++) {
      const d = data[i], prev = data[i - 1];
      sar = sar + af * (ep - sar);
      if (bull) {
        if (d.low < sar) { bull = false; sar = ep; ep = d.low; af = step; }
        else { if (d.high > ep) { ep = d.high; af = Math.min(af + step, max); } sar = Math.min(sar, prev.low, d.low); }
      } else {
        if (d.high > sar) { bull = true;  sar = ep; ep = d.high; af = step; }
        else { if (d.low < ep) { ep = d.low; af = Math.min(af + step, max); } sar = Math.max(sar, prev.high, d.high); }
      }
      res.push({ time: d.time, value: sar });
    }
    return res;
  }

  function heikinAshi(data) {
    return data.map((d, i) => {
      const haClose = (d.open + d.high + d.low + d.close) / 4;
      const haOpen  = i === 0 ? (d.open + d.close) / 2
                               : (data[i - 1].open + data[i - 1].close) / 2;
      return { time: d.time, open: haOpen, high: Math.max(haOpen, haClose, d.high), low: Math.min(haOpen, haClose, d.low), close: haClose };
    });
  }

  // ── DATA ─────────────────────────────────────────────────────
  async function fetchData(symbol, tf) {
    const url = `/api/history/${encodeURIComponent(symbol)}?period=${tf.period}&interval=${tf.yf}`;
    const r = await fetch(url);
    const j = await r.json();
    if (!j.ok || !j.candles?.length) throw new Error(j.error || 'No data');
    return j.candles
      .filter(c => c.open != null && c.close != null)
      .map(c => ({
        time:   c.time,
        open:   c.open,
        high:   c.high,
        low:    c.low,
        close:  c.close,
        volume: c.volume || 0,
      }));
  }

  // ── CHART INIT ───────────────────────────────────────────────
  function makeChart(container, extraOpts = {}) {
    return LightweightCharts.createChart(container, {
      ...THEME,
      width:  container.clientWidth,
      height: container.clientHeight,
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
      handleScale:  { mouseWheel: true, pinch: true },
      ...extraOpts,
    });
  }

  function setSeries(data) {
    if (mainSeries) { try { mainChart.removeSeries(mainSeries); } catch (e) {} mainSeries = null; }
    const processed = currentType === 'ha' ? heikinAshi(data) : data;

    if (currentType === 'line') {
      mainSeries = mainChart.addLineSeries({ color: '#28e0ff', lineWidth: 2, priceLineVisible: false });
      mainSeries.setData(processed.map(d => ({ time: d.time, value: d.close })));
    } else if (currentType === 'area') {
      mainSeries = mainChart.addAreaSeries({
        topColor: 'rgba(40,224,255,0.4)', bottomColor: 'rgba(40,224,255,0)',
        lineColor: '#28e0ff', lineWidth: 2, priceLineVisible: false,
      });
      mainSeries.setData(processed.map(d => ({ time: d.time, value: d.close })));
    } else if (currentType === 'bar') {
      mainSeries = mainChart.addBarSeries({ upColor: '#2be58b', downColor: '#ff5b6e', priceLineVisible: false });
      mainSeries.setData(processed);
    } else {
      mainSeries = mainChart.addCandlestickSeries({
        upColor: '#2be58b', downColor: '#ff5b6e',
        borderUpColor: '#2be58b', borderDownColor: '#ff5b6e',
        wickUpColor: '#2be58b', wickDownColor: '#ff5b6e',
        priceLineVisible: false,
      });
      mainSeries.setData(processed);
    }
  }

  function setVol(data) {
    if (volSeries) { try { mainChart.removeSeries(volSeries); } catch (e) {} volSeries = null; }
    volSeries = mainChart.addHistogramSeries({
      color: 'rgba(40,224,255,0.25)',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    mainChart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
    volSeries.setData(data.map(d => ({
      time: d.time, value: d.volume,
      color: d.close >= d.open ? 'rgba(43,229,139,0.35)' : 'rgba(255,91,110,0.35)',
    })));
  }

  // ── INDICATORS ───────────────────────────────────────────────
  function clearOverlays() {
    for (const key in overlayLines) {
      overlayLines[key].forEach(s => { try { mainChart.removeSeries(s); } catch (e) {} });
    }
    overlayLines = {};
    activeInds   = {};
    updateIndBadges();
  }

  function removeOverlay(key) {
    if (!overlayLines[key]) return;
    overlayLines[key].forEach(s => { try { mainChart.removeSeries(s); } catch (e) {} });
    delete overlayLines[key];
    delete activeInds[key];
    updateIndBadges();
  }

  function addOverlay(id, params, color) {
    const p  = { ...OVERLAY_INDICATORS.find(x => x.id === id)?.params, ...params };
    const c  = color || OVERLAY_INDICATORS.find(x => x.id === id)?.color || '#fff';
    const key = `${id}_${JSON.stringify(p)}`;
    if (overlayLines[key]) return;

    const closes = rawData.map(d => d.close);
    const series = [];

    const addLine = (data, col, lw = 1, dash = 0) => {
      const s = mainChart.addLineSeries({ color: col, lineWidth: lw, lineStyle: dash, priceLineVisible: false, lastValueVisible: false });
      s.setData(data);
      series.push(s);
      return s;
    };

    if (id === 'EMA') {
      const v = ema(closes, p.period); addLine(rawData.map((d, i) => ({ time: d.time, value: v[i] })), c);
    } else if (id === 'SMA') {
      const v = sma(closes, p.period); addLine(rawData.map((d, i) => v[i] !== null ? { time: d.time, value: v[i] } : null).filter(Boolean), c);
    } else if (id === 'WMA') {
      const v = wma(closes, p.period); addLine(rawData.map((d, i) => v[i] !== null ? { time: d.time, value: v[i] } : null).filter(Boolean), c);
    } else if (id === 'DEMA') {
      const v = dema(closes, p.period); addLine(rawData.map((d, i) => ({ time: d.time, value: v[i] })), c);
    } else if (id === 'BB') {
      const bb = calcBB(rawData, p.period, p.mult);
      addLine(bb.map(d => ({ time: d.time, value: d.upper })), c, 1);
      addLine(bb.map(d => ({ time: d.time, value: d.mid   })), c, 1, 2);
      addLine(bb.map(d => ({ time: d.time, value: d.lower })), c, 1);
    } else if (id === 'VWAP') {
      addLine(calcVWAP(rawData), c);
    } else if (id === 'PSAR') {
      const v = calcPSAR(rawData); addLine(v, c, 1);
    }

    overlayLines[key] = series;
    activeInds[key]   = { id, params: p, color: c };
    updateIndBadges();
  }

  function reapplyOverlays() {
    const prev = { ...activeInds };
    clearOverlays();
    for (const { id, params, color } of Object.values(prev)) addOverlay(id, params, color);
  }

  function updateIndBadges() {
    const wrap = document.getElementById('cv-active-inds');
    if (!wrap) return;
    wrap.innerHTML = Object.entries(activeInds).map(([key, ind]) =>
      `<span class="cv-ind-badge" data-key="${key}" style="border-color:${ind.color}">
        <span style="color:${ind.color}">${ind.id}</span>
        <span class="cv-ind-badge-rm" data-key="${key}">✕</span>
      </span>`
    ).join('');
    wrap.querySelectorAll('.cv-ind-badge-rm').forEach(btn => {
      btn.onclick = (e) => { e.stopPropagation(); removeOverlay(btn.dataset.key); };
    });
  }

  // ── SUB-INDICATOR ────────────────────────────────────────────
  function setSubIndicator(type) {
    currentSub = type;
    if (syncSub) { syncSub(); syncSub = null; }
    if (subChart) { subChart.remove(); subChart = null; }
    const subCont  = document.getElementById('cv-sub-chart');
    const subPane  = document.getElementById('cv-sub-pane');
    const subLabel = document.getElementById('cv-sub-label');
    if (!subCont || !subPane) return;

    if (type === 'volume') {
      subPane.style.display = 'none';
      return;
    }
    subPane.style.display = 'flex';
    if (subLabel) subLabel.textContent = type.toUpperCase();

    if (!rawData.length) return;

    subChart = makeChart(subCont, { rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 } } });

    const syncFn = () => {
      let syncing = false;
      const ua = mainChart.timeScale().subscribeVisibleLogicalRangeChange(r => {
        if (!syncing && r && subChart) { syncing = true; subChart.timeScale().setVisibleLogicalRange(r); syncing = false; }
      });
      const ub = subChart.timeScale().subscribeVisibleLogicalRangeChange(r => {
        if (!syncing && r && mainChart) { syncing = true; mainChart.timeScale().setVisibleLogicalRange(r); syncing = false; }
      });
      return () => {};
    };
    syncSub = syncFn();

    const addL = (data, col, lw = 1, dash = 0) => {
      const s = subChart.addLineSeries({ color: col, lineWidth: lw, lineStyle: dash, priceLineVisible: false, lastValueVisible: true });
      s.setData(data); return s;
    };

    if (type === 'rsi') {
      const d = calcRSI(rawData, 14);
      addL(d, '#a06bff');
      addL(d.map(x => ({ time: x.time, value: 70 })), 'rgba(255,91,110,0.4)', 1, 2);
      addL(d.map(x => ({ time: x.time, value: 30 })), 'rgba(43,229,139,0.4)', 1, 2);
      addL(d.map(x => ({ time: x.time, value: 50 })), 'rgba(120,130,255,0.2)', 1, 2);
      subChart.priceScale('right').applyOptions({ autoScale: false });
      subChart.applyOptions({ rightPriceScale: { minimum: 0, maximum: 100 } });
    } else if (type === 'macd') {
      const d = calcMACD(rawData);
      addL(d.macd,   '#28e0ff');
      addL(d.signal, '#ff5ec4');
      const hs = subChart.addHistogramSeries({ priceLineVisible: false });
      hs.setData(d.hist.map(x => ({ ...x, color: x.value >= 0 ? 'rgba(43,229,139,0.55)' : 'rgba(255,91,110,0.55)' })));
    } else if (type === 'stoch') {
      const d = calcStoch(rawData);
      addL(d.k, '#28e0ff');
      addL(d.d, '#ff5ec4', 1, 2);
      addL(d.k.map(x => ({ time: x.time, value: 80 })), 'rgba(255,91,110,0.4)', 1, 2);
      addL(d.k.map(x => ({ time: x.time, value: 20 })), 'rgba(43,229,139,0.4)', 1, 2);
      subChart.priceScale('right').applyOptions({ autoScale: false });
    } else if (type === 'cci') {
      const d = calcCCI(rawData);
      addL(d, '#ff9800');
      addL(d.map(x => ({ time: x.time, value:  100 })), 'rgba(255,91,110,0.4)', 1, 2);
      addL(d.map(x => ({ time: x.time, value: -100 })), 'rgba(43,229,139,0.4)', 1, 2);
    }

    if (subChart) subChart.timeScale().fitContent();
  }

  // ── DRAWING OVERLAY ──────────────────────────────────────────
  function initCanvas() {
    if (!chartWrap) return;
    const old = chartWrap.querySelector('.cv-draw-canvas');
    if (old) old.remove();
    drawCanvas = document.createElement('canvas');
    drawCanvas.className = 'cv-draw-canvas';
    Object.assign(drawCanvas.style, { position:'absolute', inset:'0', zIndex:'10', pointerEvents:'none', cursor:'crosshair' });
    chartWrap.appendChild(drawCanvas);
    resize();

    drawCanvas.addEventListener('mousedown', onCvDown);
    drawCanvas.addEventListener('mousemove', onCvMove);
    drawCanvas.addEventListener('dblclick', () => { drawState = null; redraw(); });
  }

  function resize() {
    if (!drawCanvas || !chartWrap) return;
    drawCanvas.width  = chartWrap.clientWidth;
    drawCanvas.height = chartWrap.clientHeight;
    redraw();
  }

  function setDrawMode(mode) {
    drawMode = mode;
    drawState = null;
    if (drawCanvas) drawCanvas.style.pointerEvents = mode === 'cursor' ? 'none' : 'auto';
    document.querySelectorAll('.cv-tool-btn').forEach(b => b.classList.toggle('active', b.dataset.tool === mode));
    redraw();
  }

  function pxToChart(cx, cy) {
    if (!mainChart || !mainSeries || !drawCanvas) return null;
    const rect = drawCanvas.getBoundingClientRect();
    const x = cx - rect.left, y = cy - rect.top;
    const time  = mainChart.timeScale().coordinateToTime(x);
    const price = mainSeries.coordinateToPrice(y);
    return { x, y, time, price };
  }

  function chartToPx(time, price) {
    if (!mainChart || !mainSeries) return null;
    const x = mainChart.timeScale().timeToCoordinate(time);
    const y = price != null ? mainSeries.priceToCoordinate(price) : null;
    if (x === null || y === null) return null;
    return { x, y };
  }

  function redraw() {
    if (!drawCanvas) return;
    const ctx = drawCanvas.getContext('2d');
    ctx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);
    drawings.forEach(d => renderDrawing(ctx, d, false));
    if (drawState) renderDrawing(ctx, drawState, true);
  }

  function renderDrawing(ctx, d, isTemp) {
    ctx.save();
    ctx.globalAlpha = isTemp ? 0.65 : 1;
    const col = d.color || '#28e0ff';
    ctx.strokeStyle = col; ctx.fillStyle = col;
    ctx.lineWidth = d.width || 1.5;
    ctx.setLineDash([]);
    ctx.font = '12px "Space Grotesk",sans-serif';

    if (d.type === 'hline') {
      const pt = chartToPx(null, d.price); if (!pt) { ctx.restore(); return; }
      ctx.beginPath(); ctx.moveTo(0, pt.y); ctx.lineTo(drawCanvas.width, pt.y); ctx.stroke();
      ctx.fillText(d.price?.toFixed(4), drawCanvas.width - 65, pt.y - 4);
    } else if (d.type === 'vline') {
      if (!d.time) { ctx.restore(); return; }
      const x = mainChart.timeScale().timeToCoordinate(d.time);
      if (x === null) { ctx.restore(); return; }
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, drawCanvas.height); ctx.stroke();
    } else if (d.type === 'trendline' || d.type === 'ray') {
      if (!d.p1 || !d.p2) { ctx.restore(); return; }
      const a = chartToPx(d.p1.time, d.p1.price);
      const b = chartToPx(d.p2.time, d.p2.price);
      if (!a || !b) { ctx.restore(); return; }
      ctx.beginPath(); ctx.moveTo(a.x, a.y);
      if (d.type === 'ray') {
        const dx = b.x - a.x || 0.01, dy = b.y - a.y || 0;
        const t  = Math.max((drawCanvas.width - a.x) / dx, (drawCanvas.height - a.y) / dy, 0);
        ctx.lineTo(a.x + dx * t, a.y + dy * t);
      } else {
        ctx.lineTo(b.x, b.y);
      }
      ctx.stroke();
      dot(ctx, a.x, a.y, col); dot(ctx, b.x, b.y, col);
    } else if (d.type === 'rect') {
      if (!d.p1 || !d.p2) { ctx.restore(); return; }
      const a = chartToPx(d.p1.time, d.p1.price);
      const b = chartToPx(d.p2.time, d.p2.price);
      if (!a || !b) { ctx.restore(); return; }
      ctx.fillStyle = 'rgba(40,224,255,0.07)';
      ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
      ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
    } else if (d.type === 'fib') {
      if (!d.p1 || !d.p2) { ctx.restore(); return; }
      const a = chartToPx(d.p1.time, d.p1.price);
      const b = chartToPx(d.p2.time, d.p2.price);
      if (!a || !b) { ctx.restore(); return; }
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
      const pDiff = d.p2.price - d.p1.price;
      FIB_LEVELS.forEach((lvl, i) => {
        const price = d.p1.price + pDiff * lvl;
        const pt = chartToPx(d.p1.time, price); if (!pt) return;
        ctx.strokeStyle = FIB_COLORS[i % FIB_COLORS.length];
        ctx.setLineDash([4, 4]); ctx.globalAlpha = 0.75;
        ctx.beginPath(); ctx.moveTo(x0, pt.y); ctx.lineTo(x1, pt.y); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha = isTemp ? 0.65 : 1;
        ctx.fillStyle = FIB_COLORS[i % FIB_COLORS.length];
        ctx.fillText(`${(lvl * 100).toFixed(1)}% ${price.toFixed(3)}`, x1 + 4, pt.y + 4);
      });
      ctx.strokeStyle = '#28e0ff'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    } else if (d.type === 'longpos' || d.type === 'shortpos') {
      const isLong = d.type === 'longpos';
      if (!d.p1) { ctx.restore(); return; }
      const ep  = chartToPx(d.p1.time, d.entry); if (!ep) { ctx.restore(); return; }
      const slP = chartToPx(d.p1.time, d.sl);
      const tpP = chartToPx(d.p1.time, d.tp);
      const x0 = ep.x, x1 = drawCanvas.width;
      if (tpP) {
        ctx.fillStyle = isLong ? 'rgba(43,229,139,0.14)' : 'rgba(255,91,110,0.14)';
        ctx.fillRect(x0, Math.min(ep.y, tpP.y), x1 - x0, Math.abs(tpP.y - ep.y));
        ctx.strokeStyle = isLong ? '#2be58b' : '#ff5b6e';
        line(ctx, x0, tpP.y, x1, tpP.y);
        ctx.fillStyle = isLong ? '#2be58b' : '#ff5b6e';
        ctx.fillText(`TP ${d.tp?.toFixed(2)}`, x1 - 90, tpP.y - 4);
      }
      if (slP) {
        ctx.fillStyle = isLong ? 'rgba(255,91,110,0.14)' : 'rgba(43,229,139,0.14)';
        ctx.fillRect(x0, Math.min(ep.y, slP.y), x1 - x0, Math.abs(slP.y - ep.y));
        ctx.strokeStyle = isLong ? '#ff5b6e' : '#2be58b';
        line(ctx, x0, slP.y, x1, slP.y);
        ctx.fillStyle = isLong ? '#ff5b6e' : '#2be58b';
        ctx.fillText(`SL ${d.sl?.toFixed(2)}`, x1 - 90, slP.y + 12);
      }
      ctx.strokeStyle = '#ffd600'; ctx.setLineDash([4, 4]);
      line(ctx, x0, ep.y, x1, ep.y);
      ctx.setLineDash([]); ctx.fillStyle = '#ffd600';
      ctx.fillText(`Entry ${d.entry?.toFixed(2)}`, x1 - 110, ep.y - 4);
      if (d.tp && d.sl) {
        const rr = Math.abs(d.tp - d.entry) / (Math.abs(d.entry - d.sl) || 1);
        ctx.fillStyle = '#fff'; ctx.fillText(`R/R ${rr.toFixed(2)}`, x0 + 6, ep.y - 4);
      }
    } else if (d.type === 'brush' && d.points?.length > 1) {
      ctx.beginPath();
      d.points.forEach((pt, i) => {
        const p = chartToPx(pt.time, pt.price); if (!p) return;
        i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y);
      });
      ctx.stroke();
    } else if (d.type === 'text') {
      if (!d.p1) { ctx.restore(); return; }
      const pt = chartToPx(d.p1.time, d.p1.price); if (!pt) { ctx.restore(); return; }
      ctx.fillStyle = d.color || '#fff';
      ctx.font = `${d.fontSize || 13}px "Space Grotesk",sans-serif`;
      ctx.fillText(d.text || '', pt.x, pt.y);
    }
    ctx.restore();
  }

  function dot(ctx, x, y, col) {
    ctx.save(); ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); ctx.restore();
  }
  function line(ctx, x1, y1, x2, y2) {
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }

  function onCvDown(e) {
    if (drawMode === 'cursor') return;
    const co = pxToChart(e.clientX, e.clientY); if (!co) return;

    if (drawMode === 'eraser') {
      drawings = drawings.slice(0, -1); redraw(); return;
    }
    if (drawMode === 'hline' && co.price != null) {
      drawings.push({ type: 'hline', price: co.price, color: '#28e0ff', width: 1 }); redraw(); return;
    }
    if (drawMode === 'vline' && co.time) {
      drawings.push({ type: 'vline', time: co.time, color: '#28e0ff', width: 1 }); redraw(); return;
    }
    if (drawMode === 'text' && co.price != null) {
      const txt = prompt('ข้อความ:'); if (!txt) return;
      drawings.push({ type: 'text', p1: { time: co.time, price: co.price }, text: txt }); redraw(); return;
    }
    if ((drawMode === 'longpos' || drawMode === 'shortpos') && co.price != null) {
      const risk = co.price * 0.02;
      drawings.push({
        type: drawMode, p1: { time: co.time, price: co.price },
        entry: co.price,
        tp: drawMode === 'longpos' ? co.price + risk * 2 : co.price - risk * 2,
        sl: drawMode === 'longpos' ? co.price - risk     : co.price + risk,
        color: drawMode === 'longpos' ? '#2be58b' : '#ff5b6e',
      }); redraw(); return;
    }
    if (drawMode === 'brush') {
      drawState = { type: 'brush', points: [{ time: co.time, price: co.price }] }; return;
    }

    if (!drawState) {
      drawState = { type: drawMode, p1: { time: co.time, price: co.price }, color: '#28e0ff' };
    } else {
      drawState.p2 = { time: co.time, price: co.price };
      drawings.push({ ...drawState });
      drawState = null;
      redraw();
    }
  }

  function onCvMove(e) {
    if (!drawState) return;
    const co = pxToChart(e.clientX, e.clientY); if (!co) return;
    if (drawState.type === 'brush') {
      drawState.points.push({ time: co.time, price: co.price });
    } else {
      drawState.p2 = { time: co.time, price: co.price };
    }
    redraw();
  }

  // ── LEGEND ───────────────────────────────────────────────────
  function updateLegend(param) {
    const el = document.getElementById('cv-legend'); if (!el) return;
    let d = param?.seriesData?.get(mainSeries) || rawData[rawData.length - 1];
    if (!d) return;
    const isOHLC = d.open != null;
    const c = isOHLC ? d.close : d.value;
    const chg = rawData.length > 1 ? c - rawData[rawData.length - 2].close : 0;
    const pct = rawData.length > 1 && rawData[rawData.length - 2].close ? chg / rawData[rawData.length - 2].close * 100 : 0;
    const up  = chg >= 0;
    el.innerHTML = `
      <span class="cv-leg-sym">${currentSymbol}</span>
      <span class="cv-leg-tf">${currentTF.label}</span>
      ${isOHLC ? `<span>O <b>${d.open?.toFixed(4)}</b></span><span>H <b>${d.high?.toFixed(4)}</b></span><span>L <b>${d.low?.toFixed(4)}</b></span>` : ''}
      <span>C <b class="${up ? 'up' : 'down'}">${c?.toFixed(4)}</b></span>
      ${isOHLC ? `<span>V <b>${bigN(d.volume ?? rawData[rawData.length - 1]?.volume ?? 0)}</b></span>` : ''}
      <span class="${up ? 'up' : 'down'}">${up ? '+' : ''}${pct.toFixed(2)}%</span>
    `;
  }

  function bigN(n) {
    if (!n) return '0';
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toFixed(0);
  }

  // ── WATCHLIST ────────────────────────────────────────────────
  async function loadWL() {
    try {
      const r = await fetch('/api/watchlist');
      const j = await r.json();
      return (j.watchlist || []).map(x => x.ticker);
    } catch (e) {
      return ['PTT.BK', 'AOT.BK', 'CPALL.BK', 'KBANK.BK', 'ADVANC.BK', 'AAPL', 'NVDA', 'TSLA', 'MSFT'];
    }
  }

  async function renderWL(tickers) {
    const panel = document.getElementById('cv-wl-body'); if (!panel) return;
    if (!tickers.length) { panel.innerHTML = '<div class="cv-wl-empty">เพิ่มหุ้นใน Watchlist</div>'; return; }
    panel.innerHTML = '<div class="cv-wl-loader">กำลังโหลด…</div>';
    try {
      const r = await fetch('/api/quotes', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tickers: tickers.slice(0, 30) }),
      });
      const j = await r.json();
      const qs = j.quotes || [];
      panel.innerHTML = qs.map(q => {
        const up = (q.change_pct || 0) >= 0;
        return `<div class="cv-wl-item${q.ticker === currentSymbol ? ' active' : ''}" data-t="${q.ticker}">
          <div class="cv-wl-top"><span class="cv-wl-sym">${q.ticker}</span><span class="cv-wl-px">${q.price?.toFixed(2) ?? '—'}</span></div>
          <div class="cv-wl-bot"><span class="cv-wl-name">${(q.name || '').slice(0, 16)}</span><span class="cv-wl-chg ${up ? 'up' : 'down'}">${up ? '+' : ''}${(q.change_pct || 0).toFixed(2)}%</span></div>
        </div>`;
      }).join('');
      panel.querySelectorAll('.cv-wl-item').forEach(item => item.onclick = () => loadSym(item.dataset.t));
    } catch (e) {
      panel.innerHTML = '<div class="cv-wl-empty">โหลดไม่ได้</div>';
    }
  }

  // ── SEARCH ───────────────────────────────────────────────────
  function initSearch() {
    const inp = document.getElementById('cv-search');
    const dd  = document.getElementById('cv-search-dd');
    if (!inp || !dd) return;

    inp.oninput = () => {
      clearTimeout(searchTid);
      const q = inp.value.trim();
      if (!q) { dd.style.display = 'none'; return; }
      searchTid = setTimeout(async () => {
        const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const j = await r.json();
        const rs = j.results || [];
        if (!rs.length) { dd.style.display = 'none'; return; }
        dd.innerHTML = rs.slice(0, 8).map(x =>
          `<div class="cv-dd-item" data-t="${x.symbol}">
            <span class="cv-dd-sym">${x.symbol}</span>
            <span class="cv-dd-name">${(x.name || '').slice(0, 28)}</span>
            <span class="cv-dd-ex">${x.exchange || ''}</span>
          </div>`
        ).join('');
        dd.style.display = 'block';
        dd.querySelectorAll('.cv-dd-item').forEach(item => item.onclick = () => {
          loadSym(item.dataset.t); inp.value = ''; dd.style.display = 'none';
        });
      }, 280);
    };

    inp.onkeydown = (e) => {
      if (e.key === 'Escape') { dd.style.display = 'none'; inp.value = ''; }
      if (e.key === 'Enter') {
        const q = inp.value.trim();
        if (q) { loadSym(q.toUpperCase()); inp.value = ''; dd.style.display = 'none'; }
      }
    };

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.cv-search-wrap')) dd.style.display = 'none';
    }, { capture: false });
  }

  // ── LOAD SYMBOL ──────────────────────────────────────────────
  async function loadSym(sym) {
    currentSymbol = sym;
    const st = document.getElementById('cv-status');
    if (st) st.textContent = `Loading ${sym}…`;

    try {
      rawData = await fetchData(sym, currentTF);

      setSeries(rawData);
      setVol(rawData);
      reapplyOverlays();
      initCanvas();
      mainChart.subscribeCrosshairMove(updateLegend);
      if (mainChart) { mainChart.subscribeCrosshairMove(() => redraw()); mainChart.timeScale().subscribeVisibleLogicalRangeChange(() => redraw()); }
      setSubIndicator(currentSub);
      mainChart.timeScale().fitContent();
      updateLegend(null);

      // Mark active in watchlist
      document.querySelectorAll('.cv-wl-item').forEach(x => x.classList.toggle('active', x.dataset.t === sym));

      if (st) st.textContent = '';
    } catch (err) {
      if (st) st.textContent = `ไม่พบข้อมูล ${sym}`;
      console.warn('loadSym error:', err);
    }
  }

  // ── SCREENSHOT ───────────────────────────────────────────────
  function screenshot() {
    if (!mainChart) return;
    const canvas = mainChart.takeScreenshot();
    const a = document.createElement('a');
    a.download = `${currentSymbol}_${currentTF.label}.png`;
    a.href = canvas.toDataURL('image/png');
    a.click();
  }

  // ── KEYBOARD ─────────────────────────────────────────────────
  function onKey(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.altKey) {
      const m = { c: 'candle', l: 'line', a: 'area', b: 'bar', h: 'ha' };
      if (m[e.key]) { setType(m[e.key]); return; }
    }
    const dm = { v: 'cursor', t: 'trendline', h: 'hline', f: 'fib', r: 'rect' };
    if (!e.altKey && !e.ctrlKey && dm[e.key]) { setDrawMode(dm[e.key]); return; }
    if (e.key === 'Escape') { setDrawMode('cursor'); drawState = null; redraw(); }
    if (e.key === 'Delete' || e.key === 'Backspace') { if (drawings.length) { drawings.pop(); redraw(); } }
    if ((e.ctrlKey || e.metaKey) && e.key === 'z') { if (drawings.length) { drawings.pop(); redraw(); } }
  }

  // ── SET TYPE ─────────────────────────────────────────────────
  function setType(t) {
    currentType = t;
    if (rawData.length) { setSeries(rawData); reapplyOverlays(); initCanvas(); mainChart.timeScale().fitContent(); }
    document.querySelectorAll('.cv-ct-btn').forEach(b => b.classList.toggle('active', b.dataset.type === t));
  }

  // ── RESIZE ───────────────────────────────────────────────────
  function onResize() {
    const mc = document.getElementById('cv-main-chart');
    const sc = document.getElementById('cv-sub-chart');
    if (mainChart && mc) mainChart.resize(mc.clientWidth, mc.clientHeight);
    if (subChart  && sc) subChart.resize(sc.clientWidth, sc.clientHeight);
    resize();
  }

  // ── MULTI-LAYOUT ─────────────────────────────────────────────
  function setLayout(n) {
    // Placeholder — shows visual indication of multi-layout
    document.querySelectorAll('.cv-layout-btn').forEach(b => b.classList.toggle('active', +b.dataset.layout === n));
  }

  // ── INDICATOR PANEL ──────────────────────────────────────────
  function renderIndPanel() {
    const cont = document.getElementById('cv-ind-panel-list'); if (!cont) return;
    cont.innerHTML = OVERLAY_INDICATORS.map(ind => `
      <div class="cv-ind-row">
        <span class="cv-ind-dot" style="background:${ind.color}"></span>
        <span class="cv-ind-label">${ind.label}</span>
        <button class="cv-ind-add" data-id="${ind.id}" data-params='${JSON.stringify(ind.params)}'>＋</button>
      </div>
      <div class="cv-ind-params" id="cvip-${ind.id}"></div>
    `).join('') + `
    <div class="cv-ind-section">Sub-Indicators (ด้านล่าง)</div>
    ${SUB_INDICATORS.map(s => `
      <div class="cv-ind-row">
        <span class="cv-ind-dot" style="background:#8b91c4"></span>
        <span class="cv-ind-label">${s.label}</span>
        <button class="cv-sub-add" data-sub="${s.id}">＋</button>
      </div>`).join('')}
    `;
    cont.querySelectorAll('.cv-ind-add').forEach(btn => btn.onclick = () => {
      const id = btn.dataset.id;
      const p  = JSON.parse(btn.dataset.params || '{}');
      addOverlay(id, p, null);
      document.getElementById('cv-ind-panel')?.classList.remove('show');
    });
    cont.querySelectorAll('.cv-sub-add').forEach(btn => btn.onclick = () => {
      const sub = btn.dataset.sub;
      document.querySelectorAll('.cv-sub-btn').forEach(b => b.classList.toggle('active', b.dataset.sub === sub));
      setSubIndicator(sub);
      document.getElementById('cv-ind-panel')?.classList.remove('show');
    });
  }

  // ── VIEW ENTRY ───────────────────────────────────────────────
  window.routes = window.routes || {};

  window.routes.chart = async function (app) {
    document.body.classList.add('chart-mode');
    const mainEl = document.querySelector('.main');
    if (mainEl) { mainEl.dataset.prevPad = mainEl.style.padding; mainEl.style.padding = '0'; mainEl.style.overflow = 'hidden'; }
    document.querySelector('.topbar')?.style.setProperty('display', 'none');

    window._viewCleanup = () => {
      document.body.classList.remove('chart-mode');
      if (mainEl) { mainEl.style.padding = mainEl.dataset.prevPad || ''; mainEl.style.overflow = ''; }
      document.querySelector('.topbar')?.style.removeProperty('display');
      if (mainChart) { mainChart.remove(); mainChart = null; }
      if (subChart)  { subChart.remove();  subChart  = null; }
      if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
      document.removeEventListener('keydown', onKey);
    };

    // Build HTML
    app.innerHTML = `
    <div class="cv-root">
      <!-- Topbar -->
      <div class="cv-topbar">
        <div class="cv-search-wrap">
          <span class="cv-search-ic">⌕</span>
          <input id="cv-search" type="text" placeholder="ค้นหาหุ้น…" autocomplete="off" spellcheck="false" />
          <div id="cv-search-dd" class="cv-search-dd"></div>
        </div>

        <div class="cv-sep"></div>

        <div class="cv-tfs" id="cv-tfs">
          ${TF_LIST.map(tf => `<button class="cv-tf-btn${tf.label === '1D' ? ' active' : ''}" data-tf="${tf.label}">${tf.label}</button>`).join('')}
        </div>

        <div class="cv-sep"></div>

        <div class="cv-cts">
          ${CHART_TYPES.map(ct => `<button class="cv-ct-btn${ct.id === 'candle' ? ' active' : ''}" data-type="${ct.id}" title="${ct.label}">${ct.label}</button>`).join('')}
        </div>

        <div class="cv-sep"></div>
        <button class="cv-tb-btn" id="cv-ind-btn">Indicators ＋</button>
        <div id="cv-active-inds" class="cv-active-inds"></div>

        <div class="cv-sep"></div>
        <div class="cv-sub-tabs">
          ${SUB_INDICATORS.map(s => `<button class="cv-sub-btn${s.id === 'volume' ? ' active' : ''}" data-sub="${s.id}">${s.label}</button>`).join('')}
        </div>

        <div style="flex:1"></div>
        <span id="cv-status" class="cv-status"></span>

        <div class="cv-sep"></div>
        <div class="cv-layouts">
          ${[1,2,4].map(n => `<button class="cv-layout-btn${n===1?' active':''}" data-layout="${n}" title="${n} กราฟ">${'▪'.repeat(n)}</button>`).join('')}
        </div>
        <button class="cv-tb-btn" id="cv-screenshot" title="บันทึกกราฟ">📷</button>
      </div>

      <!-- Body -->
      <div class="cv-body">
        <!-- Left toolbar -->
        <div class="cv-left-toolbar" id="cv-left-toolbar">
          ${DRAW_TOOLS.map(t => `<button class="cv-tool-btn${t.id === 'cursor' ? ' active' : ''}" data-tool="${t.id}" title="${t.tip}">${t.icon}</button>`).join('')}
        </div>

        <!-- Chart + sub -->
        <div class="cv-chart-area">
          <div class="cv-chart-wrap" id="cv-chart-wrap">
            <div id="cv-main-chart" class="cv-main-chart"></div>
            <div class="cv-legend" id="cv-legend"></div>
          </div>
          <div class="cv-sub-pane" id="cv-sub-pane" style="display:none">
            <div class="cv-sub-label" id="cv-sub-label">RSI</div>
            <div id="cv-sub-chart" class="cv-sub-chart-inner"></div>
          </div>
        </div>

        <!-- Right panel -->
        <div class="cv-right-panel">
          <div class="cv-panel-hdr">
            <span>Watchlist</span>
            <button class="cv-tb-btn" id="cv-wl-refresh" title="Refresh">↻</button>
          </div>
          <div id="cv-wl-body" class="cv-wl-body"></div>
        </div>
      </div>

      <!-- Indicator panel -->
      <div class="cv-ind-panel glass" id="cv-ind-panel">
        <div class="cv-ind-hdr">
          <span>เพิ่ม Indicator</span>
          <button id="cv-ind-close">✕</button>
        </div>
        <div id="cv-ind-panel-list" class="cv-ind-panel-list"></div>
      </div>
    </div>`;

    // Init chart
    const mc = document.getElementById('cv-main-chart');
    chartWrap = document.getElementById('cv-chart-wrap');
    mainChart = makeChart(mc);
    mainChart.subscribeCrosshairMove(updateLegend);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(() => redraw());
    mainChart.subscribeCrosshairMove(() => redraw());

    initCanvas();
    initSearch();
    renderIndPanel();

    // Resize observer
    resizeObs = new ResizeObserver(onResize);
    resizeObs.observe(app);

    // Keyboard
    document.addEventListener('keydown', onKey);

    // Timeframes
    document.querySelectorAll('.cv-tf-btn').forEach(btn => btn.onclick = () => {
      const tf = TF_LIST.find(t => t.label === btn.dataset.tf); if (!tf) return;
      currentTF = tf;
      document.querySelectorAll('.cv-tf-btn').forEach(b => b.classList.toggle('active', b === btn));
      loadSym(currentSymbol);
    });

    // Chart types
    document.querySelectorAll('.cv-ct-btn').forEach(btn => btn.onclick = () => setType(btn.dataset.type));

    // Drawing tools
    document.querySelectorAll('.cv-tool-btn').forEach(btn => btn.onclick = () => setDrawMode(btn.dataset.tool));

    // Sub-indicators
    document.querySelectorAll('.cv-sub-btn').forEach(btn => btn.onclick = () => {
      document.querySelectorAll('.cv-sub-btn').forEach(b => b.classList.toggle('active', b === btn));
      setSubIndicator(btn.dataset.sub);
    });

    // Indicator panel
    document.getElementById('cv-ind-btn').onclick = (e) => {
      e.stopPropagation();
      document.getElementById('cv-ind-panel')?.classList.toggle('show');
    };
    document.getElementById('cv-ind-close').onclick = () => document.getElementById('cv-ind-panel')?.classList.remove('show');
    document.getElementById('cv-ind-panel').addEventListener('click', (e) => e.stopPropagation());
    document.addEventListener('click', () => document.getElementById('cv-ind-panel')?.classList.remove('show'));

    // Layout buttons
    document.querySelectorAll('.cv-layout-btn').forEach(btn => btn.onclick = () => setLayout(+btn.dataset.layout));

    // Screenshot
    document.getElementById('cv-screenshot').onclick = screenshot;

    // Watchlist refresh
    document.getElementById('cv-wl-refresh').onclick = async () => {
      const tickers = await loadWL(); renderWL(tickers);
    };

    // Load watchlist and initial symbol
    const tickers = await loadWL();
    renderWL(tickers);
    await loadSym(currentSymbol);
  };

})();
