/* ============================================================
   crisis-view.js — บทเรียนจากวิกฤต + สัญญาณเตือนล่วงหน้า
   ============================================================ */

routes.crisis = async (app, ticker) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">บทเรียนจากวิกฤต ⚠️</div>
      <div class="page-sub">วิกฤตแต่ละแบบทำให้หุ้นร่วงแค่ไหน · ก่อนเกิดมีสัญญาณอะไรเตือน · วันนี้เราอยู่ตรงไหน</div>

      <div class="card" style="margin-bottom:14px;border-color:var(--down)">
        <div class="card-title">อ่านก่อนใช้</div>
        <div class="small" style="line-height:1.7">
          · วิกฤตใน 25 ปีมีแค่ <b>8 ครั้ง</b> — ตัวอย่างน้อยมาก สรุปเป็นกฎเหล็กไม่ได้<br>
          · สัญญาณพวกนี้ <b>เคยเตือนถูกบ้างผิดบ้าง</b> และเคยเตือนหลายครั้งที่ไม่เกิดวิกฤตจริง<br>
          · ทุกวิกฤตสาเหตุไม่เหมือนกัน สิ่งที่เคยเตือนได้ครั้งก่อนอาจเงียบครั้งหน้า<br>
          · ข่าว GDELT ย้อนหลังได้ถึงราวปี 2017 เท่านั้น หน้านี้จึงใช้ <b>ราคา + ตัวชี้วัดมหภาค</b> ซึ่งย้อนได้ถึงปี 1990s
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">หุ้น/กองทุนของคุณเจอวิกฤตแล้วเป็นยังไง</div>
        <div class="form-grid">
          <div>
            <label class="small muted">สัญลักษณ์</label>
            <input id="crTicker" type="text" placeholder="เช่น AAPL, SPY, QQQ, PTT.BK" value="${ticker || ''}" />
          </div>
          <div style="display:flex;align-items:flex-end">
            <button class="btn" id="crRun">ดูผลกระทบ</button>
          </div>
        </div>
        <div class="chips" style="margin-top:10px" id="crQuick"></div>
      </div>

      <div id="crImpact"></div>

      <div class="card">
        <div class="card-title">สัญญาณเตือนล่วงหน้า — วันนี้เทียบกับก่อนวิกฤตในอดีต</div>
        <div id="crSignals">${loader('')}</div>
      </div>
    </div>`;

  $('#crQuick').innerHTML = ['SPY', 'QQQ', 'VOO', 'AAPL', 'NVDA', 'XLF']
    .map(t => `<span class="chip" data-t="${t}">${t}</span>`).join('');
  $$('#crQuick .chip').forEach(c => c.onclick = () => {
    $('#crTicker').value = c.dataset.t; runImpact();
  });

  $('#crRun').onclick = runImpact;
  $('#crTicker').onkeydown = e => { if (e.key === 'Enter') runImpact(); };

  loadSignals();
  if (ticker) runImpact();

  // ---------- ผลกระทบต่อหุ้นที่เลือก ----------
  async function runImpact() {
    const t = ($('#crTicker').value || '').trim().toUpperCase();
    if (!t) { toast('ใส่สัญลักษณ์ก่อน'); return; }
    $('#crImpact').innerHTML = `<div class="card">${loader('กำลังดึงราคาย้อนหลัง 20+ ปี…')}</div>`;

    const r = await api(`/crisis/impact/${encodeURIComponent(t)}`);
    if (!r.ok) {
      $('#crImpact').innerHTML = `<div class="card">${emptyState('⚠️', r.error || 'ดึงข้อมูลไม่ได้')}</div>`;
      return;
    }

    const rows = (r.crises || []).map(c => {
      if (!c.covered) {
        return `<tr style="opacity:.4">
          <td>${c.name}<div class="small muted">${c.cause}</div></td>
          <td colspan="4" class="small muted">${c.note_extra || 'ไม่มีข้อมูล'}</td></tr>`;
      }
      const rec = c.recovery_months ? `${c.recovery_months} เดือน`
        : '<span class="down">ยังไม่ฟื้น</span>';
      const vs = c.vs_market === null || c.vs_market === undefined ? '—'
        : `<span class="${cls(c.vs_market)}">${c.vs_market > 0 ? '+' : ''}${nf(c.vs_market, 1)}%</span>`;
      return `<tr>
        <td>${c.name}<div class="small muted">${c.cause} · ${c.start}</div></td>
        <td class="mono down" style="font-weight:600">${nf(c.drawdown_pct, 1)}%</td>
        <td class="mono">${nf(c.benchmark_drawdown_pct, 1)}%</td>
        <td>${vs}</td>
        <td>${rec}</td>
      </tr>`;
    }).join('');

    $('#crImpact').innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="card-title">${r.ticker} เจอวิกฤตมาแล้ว</div>
        <div style="font-weight:600;line-height:1.6;margin-bottom:10px">${r.summary || ''}</div>
        <div class="small muted" style="margin-bottom:10px">
          มีข้อมูลราคาตั้งแต่ ${r.data_from} · เทียบกับ S&P 500
        </div>
        <div class="table-scroll"><table class="tbl">
          <thead><tr>
            <th>วิกฤต</th><th>${r.ticker} ร่วง</th><th>ตลาดร่วง</th><th>ต่างจากตลาด</th><th>ฟื้นใน</th>
          </tr></thead><tbody>${rows}</tbody></table></div>
        <div class="small muted" style="margin-top:10px">
          "ต่างจากตลาด" ติดลบ = ร่วงแรงกว่าตลาด · ตัวเลขนี้บอกว่าหุ้นตัวนี้ทนวิกฤตได้แค่ไหน
        </div>
      </div>`;
  }

  // ---------- สัญญาณเตือนล่วงหน้า ----------
  async function loadSignals() {
    const r = await api('/crisis/signals');
    const rows = (r.rows || []);
    if (!rows.length) { $('#crSignals').innerHTML = emptyState('📡', 'ดึงข้อมูลไม่ได้'); return; }

    const lvlCol = { high: 'var(--down)', medium: 'var(--neon-purple)', low: 'var(--up)' };

    $('#crSignals').innerHTML = rows.map(s => {
      if (!s.ok) {
        return `<div class="card" style="margin-bottom:10px;opacity:.5">
          <b>${s.label}</b><div class="small muted">${s.error || 'ดึงข้อมูลไม่ได้'}</div></div>`;
      }
      const col = lvlCol[s.danger?.level] || 'var(--muted)';
      const hist = (s.before_crises || []).map(h => `<tr>
          <td class="small">${h.crisis}<div class="muted" style="font-size:11px">${h.cause}</div></td>
          <td class="mono">${nf(h.d180, 2)}</td>
          <td class="mono">${nf(h.d90, 2)}</td>
          <td class="mono">${nf(h.d30, 2)}</td>
          <td class="mono">${nf(h.at_start, 2)}</td>
        </tr>`).join('');

      return `<div class="card" style="margin-bottom:12px;border-color:${col}">
        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline">
          <b>${s.label}</b>
          <span style="color:${col};font-weight:600">
            ตอนนี้ ${nf(s.current, 2)} · ${s.danger?.text || ''}
          </span>
        </div>
        <div class="small muted" style="margin:6px 0">${s.hint} · ข้อมูลตั้งแต่ ${s.data_from}
          ${s.percentile !== null && s.percentile !== undefined
            ? ` · ค่าปัจจุบันสูงกว่า ${nf(s.percentile, 0)}% ของประวัติทั้งหมด` : ''}</div>
        ${hist ? `<div class="table-scroll"><table class="tbl">
          <thead><tr><th>ก่อนวิกฤต</th><th>180 วัน</th><th>90 วัน</th><th>30 วัน</th><th>วันที่เริ่ม</th></tr></thead>
          <tbody>${hist}</tbody></table></div>` : '<div class="small muted">ไม่มีข้อมูลย้อนหลังพอ</div>'}
      </div>`;
    }).join('') + `<div class="small muted" style="margin-top:8px">⚠️ ${r.caveat || ''}</div>`;
  }
};
