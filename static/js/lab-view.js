/* ============================================================
   lab-view.js — แล็บกลยุทธ์ (Strategy Lab)
   หลายกลยุทธ์ → ประตูความซื่อสัตย์เดียวกัน → league table
   ============================================================ */

routes.lab = async (app, ticker) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">แล็บกลยุทธ์ 🧪</div>
      <div class="page-sub">ทดสอบกลยุทธ์หลายตระกูลแบบ Renaissance-style — เก็บเฉพาะที่รอดสถิติ ตัวที่ตกโดนปิด</div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">กติกาของแล็บ (เหมือนกันทุกกลยุทธ์)</div>
        <div class="small" style="line-height:1.7">
          · <b>walk-forward</b>: หาเกณฑ์จากช่วงเรียนรู้ (60%) เท่านั้น แล้วเทรดในช่วงทดสอบ (40%) ที่เครื่องไม่เคยเห็น<br>
          · หักค่าธรรมเนียม 0.1% ทุกขา · เทียบกับ <b>ซื้อแล้วถือ</b> เสมอ · ตรวจร่องรอย overfit ก่อนโชว์ตัวเลขสวย<br>
          · ผ่านแล็บ = "มีหลักฐานพอให้ลองด้วยเงินส่วนน้อย" — <b>ไม่ใช่</b>การันตีอนาคต
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">กลยุทธ์ในแล็บ</div>
        <div id="labList">${loader('')}</div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">ทดสอบรายตัว</div>
        <div class="form-grid">
          <div>
            <label class="small muted">สัญลักษณ์</label>
            <input id="labTicker" type="text" placeholder="เช่น AAPL, SPY, NVDA, PTT.BK" value="${ticker || 'SPY'}" />
          </div>
          <div>
            <label class="small muted">กลยุทธ์</label>
            <select id="labKey"></select>
          </div>
          <div style="display:flex;align-items:flex-end">
            <button class="btn" id="labRun">รันผ่านประตูความซื่อสัตย์</button>
          </div>
        </div>
        <div class="small muted" style="margin-top:8px">ใช้ข้อมูล ~3.5 ปี · กลยุทธ์ข่าวจะช้ากว่า (ดึง GDELT)</div>
      </div>

      <div id="labResult"></div>

      <div class="card">
        <div class="card-title">League table — จัดอันดับข้ามตะกร้าหุ้น</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
          <button class="btn" id="labLeague">รันทุกกลยุทธ์ (SPY QQQ AAPL MSFT NVDA)</button>
          <button class="btn ghost" id="labLeagueWl">ใช้ watchlist ของฉัน</button>
          <span class="small muted">ใช้เวลา 1-3 นาที (รันหลายสิบ backtest)</span>
        </div>
        <div id="labLeagueBody"></div>
      </div>
    </div>`;

  const VLVL = {
    good:    { col: 'var(--up)',   txt: '✅ ผ่าน' },
    weak:    { col: '#e8c14d',     txt: '🟡 ก้ำกึ่ง' },
    bad:     { col: 'var(--down)', txt: '❌ ตกรอบ' },
    overfit: { col: 'var(--down)', txt: '⚠️ overfit' },
    none:    { col: 'var(--muted)', txt: '— ไม่มีสัญญาณ' },
    unknown: { col: 'var(--muted)', txt: '— เทรดน้อยไป' },
  };

  loadStrategies();
  $('#labRun').onclick = runOne;
  $('#labTicker').onkeydown = e => { if (e.key === 'Enter') runOne(); };
  $('#labLeague').onclick = () => runLeague({});
  $('#labLeagueWl').onclick = () => runLeague({ source: 'watchlist' });

  async function loadStrategies() {
    const r = await api('/lab/strategies');
    const list = r.strategies || [];
    $('#labKey').innerHTML = list.filter(s => s.runnable)
      .map(s => `<option value="${s.key}">${s.name}</option>`).join('');

    $('#labList').innerHTML = list.map(s => {
      const badge = s.runnable
        ? '<span class="chip" style="border-color:var(--up);color:var(--up)">รันได้</span>'
        : (s.planned
          ? '<span class="chip muted">อยู่ในแผน</span>'
          : '<span class="chip" style="border-color:var(--neon-purple)">มีหลักฐานแล้ว</span>');
      const ev = s.evidence ? `<div class="small muted" style="margin-top:4px">ผล backtest เดิม: ${
        Object.entries(s.evidence).map(([k, v]) =>
          `${k} ${v.oos_r >= 0 ? '+' : ''}${v.oos_r}R (n=${v.n}${v.gated ? ' · ปิดใช้งาน' : ''})`).join(' · ')
      }</div>` : '';
      return `<div style="padding:8px 0;border-bottom:1px solid var(--stroke)">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <b>${s.name}</b><span class="small muted">${s.family}</span>${badge}
        </div>
        <div class="small muted" style="margin-top:2px">${s.desc}</div>${ev}
      </div>`;
    }).join('') + `<div class="small muted" style="margin-top:8px">${r.note || ''}</div>`;
  }

  // ---------- รันกลยุทธ์เดียว ----------
  async function runOne() {
    const t = ($('#labTicker').value || '').trim().toUpperCase();
    const key = $('#labKey').value;
    if (!t) { toast('ใส่สัญลักษณ์ก่อน'); return; }
    $('#labRun').disabled = true;
    $('#labResult').innerHTML = `<div class="card" style="margin-bottom:14px">${loader('กำลังรัน walk-forward backtest…')}</div>`;
    const r = await api(`/lab/run/${encodeURIComponent(key)}/${encodeURIComponent(t)}`);
    $('#labRun').disabled = false;

    if (!r.ok) {
      $('#labResult').innerHTML = `<div class="card" style="margin-bottom:14px">${emptyState('⚠️', r.error || 'รันไม่สำเร็จ')}</div>`;
      return;
    }

    const v = r.verdict || {};
    const lvl = VLVL[v.level] || VLVL.unknown;
    const oos = r.out_of_sample, ins = r.in_sample, bh = r.buyhold;
    const row = (label, o) => o ? `<tr>
        <td>${label}</td>
        <td class="mono ${cls(o.total_return_pct)}">${o.total_return_pct > 0 ? '+' : ''}${nf(o.total_return_pct, 1)}%</td>
        <td class="mono">${o.num_trades ?? '—'}</td>
        <td class="mono">${o.win_rate != null ? nf(o.win_rate, 0) + '%' : '—'}</td>
        <td class="mono down">${o.max_drawdown_pct != null ? nf(o.max_drawdown_pct, 1) + '%' : '—'}</td>
        <td class="mono">${o.exposure_pct != null ? nf(o.exposure_pct, 0) + '%' : '—'}</td>
      </tr>` : '';

    $('#labResult').innerHTML = `
      <div class="card" style="margin-bottom:14px;border-color:${lvl.col}">
        <div class="card-title">${r.strategy?.name || key} × ${r.ticker}</div>
        <div style="color:${lvl.col};font-weight:600;line-height:1.6;margin-bottom:10px">${v.text || ''}</div>
        ${oos ? `<div class="table-scroll"><table class="tbl">
          <thead><tr><th>ช่วง</th><th>ผลตอบแทน</th><th>ไม้</th><th>แม่น</th><th>ร่วงลึกสุด</th><th>ถือหุ้น</th></tr></thead>
          <tbody>
            ${row(`ทดสอบ (${r.test?.from} → ${r.test?.to}) ← <b>เชื่อได้</b>`, oos)}
            ${row('ซื้อแล้วถือ (ช่วงเดียวกัน)', bh ? { ...bh, num_trades: 1, win_rate: null, exposure_pct: 100 } : null)}
            ${row('ช่วงเรียนรู้ (สวยเสมอ — ห้ามเชื่อ)', ins)}
          </tbody></table></div>` : ''}
        ${r.params?.rule ? `<div class="small muted" style="margin-top:8px">กติกา: ${r.params.rule}${
          r.params.query ? ` · ข่าวจาก query "${r.params.query}"` : ''}</div>` : ''}
        ${r.signal ? `<div class="small muted" style="margin-top:4px">สัญญาณที่ใช้: ${r.signal.label} (lag ${r.signal.lag} วัน, r=${r.signal.r})</div>` : ''}
      </div>`;
  }

  // ---------- league ----------
  async function runLeague(body) {
    $('#labLeague').disabled = $('#labLeagueWl').disabled = true;
    $('#labLeagueBody').innerHTML = loader('กำลังรันทุกกลยุทธ์กับทุกหุ้นในตะกร้า…');
    const r = await api('/lab/league', { method: 'POST', body });
    $('#labLeague').disabled = $('#labLeagueWl').disabled = false;

    if (!r.ok || !(r.rows || []).length) {
      $('#labLeagueBody').innerHTML = emptyState('⚠️', 'รันไม่สำเร็จ');
      return;
    }

    const SLVL = {
      follow:  'var(--up)', mixed: '#e8c14d',
      overfit: 'var(--down)', fail: 'var(--down)', no_data: 'var(--muted)',
    };

    $('#labLeagueBody').innerHTML = `
      <div class="small muted" style="margin-bottom:8px">ตะกร้า: ${(r.tickers || []).join(' · ')}</div>
      ${r.rows.map((s, i) => `
        <div class="card" style="margin-bottom:10px;border-color:${SLVL[s.status?.level] || 'var(--stroke)'}">
          <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline">
            <b>#${i + 1} ${s.name}</b>
            <span style="color:${SLVL[s.status?.level] || 'var(--muted)'};font-weight:600">${s.status?.text || ''}</span>
          </div>
          <div class="small muted" style="margin:4px 0 8px">
            edge เฉลี่ย ${s.avg_edge != null ? (s.avg_edge > 0 ? '+' : '') + nf(s.avg_edge, 1) + '%' : '—'}
            · ชนะตลาด ${s.beat_market}/${s.runs} ตัว
            · ผ่าน ${s.good} · overfit ${s.overfit}
          </div>
          <div class="table-scroll"><table class="tbl">
            <thead><tr><th>หุ้น</th><th>กลยุทธ์ (test)</th><th>ซื้อถือ</th><th>edge</th><th>ไม้</th><th>คำตัดสิน</th></tr></thead>
            <tbody>${(s.per_ticker || []).map(p => p.ok ? `<tr>
                <td class="mono">${p.ticker}</td>
                <td class="mono ${cls(p.oos)}">${p.oos > 0 ? '+' : ''}${nf(p.oos, 1)}%</td>
                <td class="mono ${cls(p.buyhold)}">${p.buyhold > 0 ? '+' : ''}${nf(p.buyhold, 1)}%</td>
                <td class="mono ${cls(p.edge)}" style="font-weight:600">${p.edge > 0 ? '+' : ''}${nf(p.edge, 1)}%</td>
                <td class="mono">${p.trades ?? '—'}</td>
                <td style="color:${(VLVL[p.verdict] || VLVL.unknown).col}">${(VLVL[p.verdict] || VLVL.unknown).txt}</td>
              </tr>` : `<tr style="opacity:.45">
                <td class="mono">${p.ticker}</td>
                <td colspan="5" class="small">${p.error || (VLVL[p.verdict] || VLVL.none).txt}</td>
              </tr>`).join('')}</tbody></table></div>
        </div>`).join('')}
      <div class="small muted" style="margin-top:6px">⚠️ ${r.caveat || ''}</div>`;
  }
};
