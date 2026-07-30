/* ============================================================
   ve-view.js — พอร์ต MT5 จริง (เชื่อมกับ volume-edge ที่บ้าน)
   จุดเด่น: เอาไม้จริงที่ถืออยู่ มาผ่านเครื่องอ่านข่าวโลกของ NEBULA
   ============================================================ */

routes.mt5 = async (app) => {
  app.innerHTML = `
    <div class="view active">
      <div class="page-title">พอร์ต MT5 จริง 🤖</div>
      <div class="page-sub">ไม้ที่ระบบ volume-edge เปิดอยู่จริง · พร้อมมุมมองข่าวโลกจากเครื่องเรียนรู้</div>
      <div id="veBody">${loader('กำลังต่อกับเครื่องที่บ้าน…')}</div>
    </div>`;

  const r = await api('/ve/overview');
  if (!$('#veBody')) return;

  if (!r.configured) {
    setHTML('#veBody', `<div class="card">
      <div class="card-title">ยังไม่ได้เชื่อมระบบเทรด MT5</div>
      <div class="small" style="line-height:1.8">
        ระบบเทรดของคุณ (volume-edge) รันอยู่ที่บ้านและเปิดออกเน็ตผ่าน tunnel อยู่แล้ว<br>
        เชื่อมได้โดยตั้งค่า 2 ตัวใน Render → Settings → Environment:<br><br>
        <span class="mono">VE_BASE_URL</span> = ที่อยู่เว็บระบบเทรดของคุณ<br>
        <span class="mono">VE_AUTH_KEY</span> = กุญแจเดียวกับ <span class="mono">AUTH_KEY</span> ใน <span class="mono">.env</span> ของ volume-edge<br><br>
        ⚠️ NEBULA <b>อ่านอย่างเดียว</b> — สั่งซื้อขายข้ามระบบไม่ได้ (ฝั่ง volume-edge ล็อกไว้อีกชั้น)
      </div></div>`);
    return;
  }

  const st = r.status || {};
  if (!st.ok) {
    setHTML('#veBody', `<div class="card" style="border-color:var(--down)">
      ${emptyState('🔌', st.error || 'ต่อเครื่องที่บ้านไม่ได้')}
      <div class="small muted" style="text-align:center">
        เครื่องที่บ้านต้องเปิดอยู่ + tunnel ทำงาน · ที่อยู่: <span class="mono">${r.base_url || '—'}</span>
      </div>
      <div style="text-align:center;margin-top:10px"><button class="btn" id="veRetry">ลองใหม่</button></div>
    </div>`);
    const b = $('#veRetry'); if (b) b.onclick = () => routes.mt5(app);
    return;
  }

  const mt5 = st.mt5 || {};
  const acct = (r.positions || {}).summary || {};
  const pos = (r.positions || {}).positions || [];
  const sigs = (r.signals || {}).signals || [];
  const stats = (r.setup_stats || {}).rows || [];

  const pill = (ok, yes, no) =>
    `<span class="pill ${ok ? 'buy' : 'sell'}" style="font-size:12px">${ok ? yes : no}</span>`;

  setHTML('#veBody', `
    <div class="grid cols-3" style="margin-bottom:14px">
      <div class="card">
        <div class="card-title">สถานะระบบเทรด</div>
        <div class="stat-row"><span class="k">MT5</span><span class="v">
          ${pill(mt5.connected, 'เชื่อมต่อแล้ว', 'ไม่ได้เชื่อม')}
          ${mt5.demo === false ? '<span class="pill sell" style="font-size:11px">บัญชีจริง!</span>'
                               : '<span class="small muted">demo</span>'}</span></div>
        <div class="stat-row"><span class="k">ยิงออเดอร์อัตโนมัติ</span><span class="v">
          ${pill(st.auto_trade === 'on' || st.auto_trade === true, 'เปิด', 'ปิด (ดูอย่างเดียว)')}</span></div>
        <div class="stat-row"><span class="k">ปุ่มหยุดฉุกเฉิน</span><span class="v">
          ${st.halted ? '<span class="down">กดค้างอยู่ — ไม่รับไม้ใหม่</span>' : '<span class="up">ปกติ</span>'}</span></div>
        <div class="stat-row"><span class="k">ตลาดสหรัฐ</span><span class="v">
          ${st.market_open === true ? '<span class="up">เปิด</span>'
            : st.market_open === false ? '<span class="muted">ปิด</span>' : '—'}</span></div>
        ${st.regime && st.regime.detail ? `<div class="small muted" style="margin-top:8px">
          สภาพตลาด: ${st.regime.detail}</div>` : ''}
      </div>

      <div class="card">
        <div class="card-title">บัญชี</div>
        <div class="stat-row"><span class="k">เงินทุน (equity)</span>
          <span class="v mono">${nf(acct.equity)} ${acct.currency || ''}</span></div>
        <div class="stat-row"><span class="k">ยอดคงเหลือ</span>
          <span class="v mono">${nf(acct.balance)}</span></div>
        <div class="stat-row"><span class="k">มาร์จิ้นว่าง</span>
          <span class="v mono">${nf(acct.free_margin)}</span></div>
        <div class="stat-row"><span class="k">กำไร/ขาดทุนลอย</span>
          <span class="v mono ${cls(r.positions.total_pnl)}">${nf(r.positions.total_pnl)}</span></div>
      </div>

      <div class="card">
        <div class="card-title">สถิติจริงต่อ setup</div>
        ${stats.length ? `<div class="table-scroll"><table class="tbl">
          <thead><tr><th>setup</th><th>ไม้</th><th>แม่น</th><th>คาดหวัง/ไม้</th></tr></thead>
          <tbody>${stats.map(s => `<tr>
            <td class="mono">${s.setup_code}</td>
            <td class="mono">${s.n}</td>
            <td class="mono">${s.n ? nf(s.wins / s.n * 100, 0) + '%' : '—'}</td>
            <td class="mono ${cls(s.exp_r)}">${s.exp_r != null ? nf(s.exp_r, 3) + 'R' : '—'}</td>
          </tr>`).join('')}</tbody></table></div>`
          : '<div class="small muted">ยังไม่มีไม้ที่ปิดแล้ว</div>'}
      </div>
    </div>

    <div class="card" style="margin-bottom:14px">
      <div class="card-title">ไม้ที่ถืออยู่ (${pos.length}) — ข่าวโลกว่ายังไงกับไม้พวกนี้</div>
      ${pos.length ? `<div class="table-scroll"><table class="tbl">
        <thead><tr><th>หุ้น</th><th>setup</th><th>เข้า</th><th>ตอนนี้</th><th>กำไร</th>
        <th>R</th><th>ข่าวโลกตอนนี้</th></tr></thead>
        <tbody>${pos.map(p => {
          const nw = p.news || {};
          const col = nw.adjust > 1 ? 'var(--up)' : nw.adjust < -1 ? 'var(--down)' : 'var(--muted)';
          return `<tr>
            <td class="mono" style="font-weight:600">${p.symbol}
              <div class="small muted">${p.volume} หุ้น</div></td>
            <td class="mono">${p.setup_code || '—'}
              ${p.reason_th ? `<div class="small muted" style="max-width:260px">${p.reason_th}</div>` : ''}</td>
            <td class="mono">${nf(p.entry)}</td>
            <td class="mono">${nf(p.current)}</td>
            <td class="mono ${cls(p.profit)}">${nf(p.profit)}
              <div class="small ${cls(p.pnl_pct)}">${p.pnl_pct != null ? nf(p.pnl_pct, 1) + '%' : ''}</div></td>
            <td class="mono ${cls(p.pnl_r)}">${p.pnl_r != null ? nf(p.pnl_r, 2) + 'R' : '—'}</td>
            <td style="color:${col};max-width:280px">
              ${nw.learned ? `<b>${nw.label}</b> (${nw.adjust > 0 ? '+' : ''}${nf(nw.adjust, 1)})` :
                `<span class="small muted">${nw.label || 'ยังไม่ได้เรียนรู้หุ้นตัวนี้'}</span>`}
              ${(nw.reasons || []).map(t => `<div class="small muted">· ${t}</div>`).join('')}
            </td></tr>`;
        }).join('')}</tbody></table></div>
        <div class="small muted" style="margin-top:10px">
          คอลัมน์ "ข่าวโลกตอนนี้" มาจากเครื่องเรียนรู้ของ NEBULA — ใช้เฉพาะความสัมพันธ์ที่ผ่านเกณฑ์สถิติแล้ว
          (ถ้าเขียนว่ายังไม่ได้เรียนรู้ ให้ไปกดวิเคราะห์ที่เมนูเครื่องเรียนรู้ก่อน)
        </div>`
        : `<div class="small muted">ตอนนี้ไม่มีไม้เปิด</div>`}
    </div>

    <div class="card">
      <div class="card-title">สัญญาณล่าสุด — ทั้งที่ซื้อและที่ "ไม่ซื้อ" พร้อมเหตุผล</div>
      ${sigs.length ? `<div class="table-scroll"><table class="tbl">
        <thead><tr><th>เวลา</th><th>หุ้น</th><th>setup</th><th>ทำอะไร</th><th>เหตุผล</th></tr></thead>
        <tbody>${sigs.map(s => `<tr>
          <td class="small mono">${(s.ts || '').toString().slice(0, 16).replace('T', ' ')}</td>
          <td class="mono">${s.symbol || ''}</td>
          <td class="mono">${s.setup_code || ''}</td>
          <td>${s.action === 'enter' ? '<span class="up">เข้าไม้</span>' : `<span class="muted">${s.action || 'ข้าม'}</span>`}</td>
          <td class="small">${s.skip_reason_th || ''}</td>
        </tr>`).join('')}</tbody></table></div>`
        : '<div class="small muted">ยังไม่มีสัญญาณ</div>'}
      <div class="small muted" style="margin-top:10px">
        ที่มา: <span class="mono">${r.base_url || ''}</span> · NEBULA อ่านอย่างเดียว สั่งซื้อขายจากที่นี่ไม่ได้
      </div>
    </div>`);
};
