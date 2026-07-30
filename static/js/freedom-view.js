/* แผนอิสรภาพ + trailing stop
   สองเครื่องมือที่ต่อกับ "เงินจริง" จึงต้องระวังเรื่องการให้ความมั่นใจเกินจริง
   ทุกตัวเลขที่แสดงต้องบอกที่มา และตอบเป็นช่วงเมื่อเป็นการคาดการณ์ */
(function () {
  const money = n => (n === null || n === undefined || isNaN(n))
    ? '—' : Number(n).toLocaleString('th-TH', { maximumFractionDigits: 0 });

  routes.freedom = async (app) => {
    app.innerHTML = `<div class="view active">
      <div class="page-title">แผนอิสรภาพ 🕊️</div>
      <div class="page-sub">คำนวณทบต้นจาก <b>ผลงานจริงของคุณเอง</b> ไม่ใช่ตัวเลขที่อยากให้เป็น</div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-title">ทำไมเครื่องนี้ไม่ให้กรอกผลตอบแทนเอง</div>
        <div class="small muted" style="line-height:1.9">
          · เครื่องคำนวณทั่วไปให้กรอก "ผลตอบแทนต่อปี" เอง ซึ่งคนมักกรอกตัวเลขที่อยากได้<br>
          · ที่นี่ดึงผลตอบแทนรายวันจริงจากผลเทรด MT5 หรือมูลค่าพอร์ตที่ระบบเก็บไว้<br>
          · จำลองอนาคตด้วยการ <b>สุ่มลำดับผลตอบแทนจริงใหม่หลายพันรอบ</b>
            แล้วตอบเป็นช่วง เพราะอนาคตไม่ใช่เส้นตรง<br>
          · บอกด้วยว่าระหว่างทางต้องทนขาดทุนหนักแค่ไหน — ตัวที่ทำให้คนเลิกกลางคัน
        </div>
      </div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-title">ตั้งค่าแผน</div>
        <div class="form-grid">
          <div><label>เงินตั้งต้น (บาท)</label><input id="fStart" type="number" value="100000"></div>
          <div><label>เติมทุกเดือน (บาท)</label><input id="fMonthly" type="number" value="10000"></div>
          <div><label>เป้าหมาย (บาท)</label><input id="fTarget" type="number" value="10000000"></div>
          <div><label>มองไปข้างหน้า (ปี)</label><input id="fYears" type="number" value="10"></div>
          <div><button class="btn" id="fRun">คำนวณ</button></div>
        </div>
      </div>

      <div id="fResult">${loader('')}</div>
    </div>`;

    $('#fRun').onclick = run;
    run();

    async function run() {
      setHTML('#fResult', loader('กำลังคำนวณจากผลงานจริง…'));
      const qs = new URLSearchParams({
        start: $('#fStart').value || 0,
        monthly: $('#fMonthly').value || 0,
        target: $('#fTarget').value || 0,
        years: $('#fYears').value || 10,
      });
      const r = await api(`/freedom/plan?${qs}`);
      if (!$('#fResult')) return;

      if (!r.ok) {
        setHTML('#fResult', `<div class="card">
          ${emptyState('📉', r.error || 'ยังคำนวณไม่ได้')}
          <div class="small muted" style="text-align:center;max-width:520px;margin:0 auto">
            ${r.how_to_fix || ''}</div></div>`);
        return;
      }

      const p = r.performance || {};
      const j = r.projection || {};
      const t = r.to_target;

      const perf = p.ok ? `<div class="grid cols-4">
        <div class="card"><div class="card-title">ผลตอบแทนทบต้น/ปี</div>
          <div class="stat-big ${cls(p.cagr_pct)}">${pf(p.cagr_pct)}</div>
          <div class="small muted">จากผลงานจริง ${p.years} ปี</div></div>
        <div class="card"><div class="card-title">ขาดทุนหนักสุดที่เคยเจอ</div>
          <div class="stat-big down">${pf(p.max_drawdown_pct)}</div>
          <div class="small muted">ต้องทนให้ได้ถ้าจะเดินต่อ</div></div>
        <div class="card"><div class="card-title">ความผันผวน/ปี</div>
          <div class="stat-big">${pf(p.vol_annual_pct)}</div>
          <div class="small muted">Sharpe ${p.sharpe}</div></div>
        <div class="card"><div class="card-title">วันที่กำไร</div>
          <div class="stat-big">${pf(p.win_rate_pct)}</div>
          <div class="small muted">จาก ${p.samples} วัน</div></div>
      </div>` : `<div class="card">${emptyState('📊', p.error || 'ข้อมูลไม่พอ')}</div>`;

      const target = !t ? '' : (t.already_there
        ? `<div class="card"><div class="card-title">เป้าหมาย</div>
             <div>ถึงเป้าแล้วตั้งแต่ต้น 🎉</div></div>`
        : (t.reachable === false
          ? `<div class="card"><div class="card-title">อีกกี่ปีถึงเป้า</div>
               ${emptyState('🎯', 'จำลองแล้วยังไปไม่ถึงเป้าในกรอบเวลาที่ตั้งไว้')}
               <div class="small muted" style="text-align:center">${t.note}</div></div>`
          : `<div class="card"><div class="card-title">อีกกี่ปีถึงเป้า ${money(t.target)} บาท</div>
               <div class="grid cols-3" style="margin-top:8px">
                 <div><div class="small muted">ถ้าโชคดี (25%)</div>
                   <div class="stat-big up">${t.fast_years} ปี</div></div>
                 <div><div class="small muted">กลาง ๆ (50%)</div>
                   <div class="stat-big">${t.median_years} ปี</div></div>
                 <div><div class="small muted">ถ้าโชคร้าย (75%)</div>
                   <div class="stat-big down">${t.slow_years} ปี</div></div>
               </div>
               <div class="small muted" style="margin-top:10px">
                 โอกาสไปถึงภายในกรอบที่จำลอง: <b>${t.chance_pct}%</b> · ${t.note}</div>
             </div>`));

      const proj = j.ok ? `<div class="card" style="margin-bottom:16px">
        <div class="card-title">อีก ${j.years} ปี จะมีเท่าไหร่ (จำลอง ${j.sims} รอบ)</div>
        <div class="small muted" style="margin-bottom:10px">
          เงินที่ใส่เข้าไปทั้งหมด ${money(j.invested_total)} บาท</div>
        <div class="grid cols-5">
          <div><div class="small muted">แย่ (10%)</div><div class="stat-big down">${money(j.p10)}</div></div>
          <div><div class="small muted">ค่อนข้างแย่ (25%)</div><div class="stat-big">${money(j.p25)}</div></div>
          <div><div class="small muted">กลาง (50%)</div><div class="stat-big up">${money(j.median)}</div></div>
          <div><div class="small muted">ค่อนข้างดี (75%)</div><div class="stat-big">${money(j.p75)}</div></div>
          <div><div class="small muted">ดี (90%)</div><div class="stat-big">${money(j.p90)}</div></div>
        </div>
        <div class="stat-row" style="margin-top:14px">
          <span>โอกาสที่ปลายทางจะน้อยกว่าเงินที่ใส่ไป</span>
          <span class="${j.chance_of_loss_pct > 30 ? 'down' : ''}">${j.chance_of_loss_pct}%</span></div>
        <div class="stat-row"><span>ขาดทุนหนักสุดระหว่างทาง (กรณีกลาง)</span>
          <span class="down">${pf(j.worst_drawdown_median_pct)}</span></div>
        <div class="stat-row"><span>ขาดทุนหนักสุดระหว่างทาง (กรณีแย่ 10%)</span>
          <span class="down">${pf(j.worst_drawdown_p10_pct)}</span></div>
      </div>` : `<div class="card">${emptyState('🔮', j.error || 'จำลองไม่ได้')}</div>`;

      setHTML('#fResult', `
        <div class="card" style="margin-bottom:16px">
          <div class="card-title">ตัวเลขทั้งหมดมาจากไหน</div>
          <div>📊 <b>${r.source_label}</b></div>
          <div class="small muted" style="margin-top:6px">${r.disclaimer}</div>
        </div>
        ${perf}
        <div style="height:16px"></div>
        ${proj}
        ${target}`);
    }
  };

  /* ---------------- trailing stop ---------------- */
  routes.trailing = async (app) => {
    app.innerHTML = `<div class="view active">
      <div class="page-title">จุดตัดขาดทุนแบบเลื่อนตาม 🪜</div>
      <div class="page-sub">เลื่อนขึ้นตามราคาเพื่อล็อกกำไร แต่ไม่เลื่อนลงกลับเด็ดขาด</div>

      <div class="card" style="margin-bottom:16px">
        <div class="card-title">ลองคำนวณหุ้นตัวเดียว</div>
        <div class="form-grid">
          <div><label>สัญลักษณ์</label><input id="tsTicker" placeholder="AAPL"></div>
          <div><label>ราคาที่เข้า</label><input id="tsEntry" type="number" placeholder="180"></div>
          <div><label>วันที่เข้า</label><input id="tsDate" type="date"></div>
          <div><label>ระยะ (เท่าของ ATR)</label><input id="tsMult" type="number" step="0.5" value="2.5"></div>
          <div><button class="btn" id="tsRun">คำนวณ</button></div>
        </div>
        <div id="tsOne" style="margin-top:12px"></div>
      </div>

      <div class="card"><div class="card-title">ทุกไม้ในพอร์ต</div>
        <div id="tsAll">${loader('')}</div></div>
    </div>`;

    $('#tsRun').onclick = async () => {
      const t = ($('#tsTicker').value || '').trim();
      const e = $('#tsEntry').value;
      if (!t || !e) { toast('กรอกสัญลักษณ์และราคาที่เข้า'); return; }
      setHTML('#tsOne', loader(''));
      const qs = new URLSearchParams({ entry: e, date: $('#tsDate').value || '',
                                       mult: $('#tsMult').value || 2.5 });
      const r = await api(`/trailing/${encodeURIComponent(t)}?${qs}`);
      if (!$('#tsOne')) return;
      setHTML('#tsOne', r.ok ? card(r) : emptyState('⚠️', r.error || 'คำนวณไม่ได้'));
    };

    const all = await api('/trailing/portfolio');
    if (!$('#tsAll')) return;
    if (!all.rows || !all.rows.length) {
      setHTML('#tsAll', emptyState('💼', 'ยังไม่มีหุ้นในพอร์ต — เพิ่มที่เมนูพอร์ต'));
      return;
    }
    setHTML('#tsAll', all.rows.map(r => r.ok
      ? card(r)
      : `<div class="stat-row"><span>${r.ticker}</span>
           <span class="muted small">${r.error || 'คำนวณไม่ได้'}</span></div>`).join('')
      + `<div class="small muted" style="margin-top:12px">⚠️ ${all.note}</div>`);

    function card(r) {
      const tone = r.already_hit ? 'down' : (r.in_profit ? 'up' : '');
      return `<div class="card" style="margin-bottom:10px">
        <div class="stat-row">
          <span><b>${r.ticker || ''}</b> <span class="small muted">เข้าที่ ${r.entry ?? '—'}</span></span>
          <span class="${tone}">${r.advice || ''}</span></div>
        <div class="grid cols-4" style="margin-top:8px">
          <div><div class="small muted">ราคาปัจจุบัน</div><div class="stat-big">${r.price}</div></div>
          <div><div class="small muted">จุดตัดตอนนี้</div><div class="stat-big ${tone}">${r.stop}</div></div>
          <div><div class="small muted">เหลือระยะ</div><div class="stat-big">${pf(r.room_pct)}</div></div>
          <div><div class="small muted">ล็อกกำไรได้</div>
            <div class="stat-big ${cls(r.locked_pct)}">${pf(r.locked_pct)}</div></div>
        </div>
        <div class="small muted" style="margin-top:8px">
          จุดสูงสุดที่เคยทำ ${r.peak} · ATR(${r.atr_len}) = ${r.atr} · ระยะ ${r.mult}×ATR
        </div></div>`;
    }
  };
})();
