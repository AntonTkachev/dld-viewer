
(function () {

  const S = {
    container: null,
    sale: null,
    rent: null,
    isDubai: false,
    period: 'all',
    roomFilter: 'all',

    rentUnit: 'annual',
    activeCharts: [],
    timelineCharts: [],
    rentTimelineCharts: [],
    modalChart: null,
    modalEngine: (typeof localStorage !== 'undefined' && localStorage.getItem('dp-modal-engine')) || 'chartjs',
    echartsInstance: null,
  };

  function _roomsRec() { return S.sale || S.rent; }

  const PERIODS = [
    { k: '1y',  months: 12  },
    { k: '3y',  months: 36  },
    { k: '5y',  months: 60  },
    { k: '10y', months: 120 },
    { k: 'all', months: null },
  ];
  const ROOM_ORDER    = ['all','studio','1br','2br','3br','4br+','villa','other'];
  const ROOM_BREAKDOWN = ['studio','1br','2br','3br','4br+','villa','other'];
  const ROOM_COLORS   = { all:'#1d4ed8', studio:'#9ca3af', '1br':'#60a5fa', '2br':'#3b82f6', '3br':'#1d4ed8', '4br+':'#1e3a8a', villa:'#d97706', other:'#a78bfa' };

  function t(k) { return (typeof window.t === 'function') ? window.t(k) : k; }

  function _h(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','`':'&#96;',
    })[c]);
  }

  function fmtInt(v) { return (v||0).toLocaleString('ru-RU'); }
  function fmtAedDP(v) {
    if (!v) return '—';
    if (v >= 1e9) return (v/1e9).toFixed(2) + ' ' + t('abbr_b');
    if (v >= 1e6) return (v/1e6).toFixed(2) + ' ' + t('abbr_m');
    if (v >= 1e3) return (v/1e3).toFixed(0) + t('abbr_k');
    return v.toLocaleString();
  }
  function fmtAxisAed(v) {
    if (v >= 1e9) return (v/1e9).toFixed(1) + 'B';
    if (v >= 1e6) return (v/1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v/1e3).toFixed(0) + 'K';
    return v;
  }
  function projName(p) { return _h(p || t('not_specified')); }
  function roomLabel(k){
    if (k==='all')    return t('room_chip_all');
    if (k==='villa')  return t('ru_villa');
    if (k==='other')  return t('ru_other');
    return {studio:'Studio','1br':'1BR','2br':'2BR','3br':'3BR','4br+':'4BR+'}[k];
  }
  function roomBreakdownIcon(k) {
    return (k === 'villa') ? '🏡' : (k === 'other') ? '·' : '🏢';
  }
  function medOf(arr) {
    if (!arr.length) return 0;
    const s = arr.slice().sort((a,b)=>a-b);
    const m = Math.floor(s.length/2);
    return s.length % 2 ? s[m] : Math.round((s[m-1]+s[m])/2);
  }

  function destroyCharts() {
    for (const c of S.activeCharts) c.destroy();
    S.activeCharts = [];
    S.timelineCharts = [];
    S.rentTimelineCharts = [];
    S.roomBreakdownChart = null;

    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    const ml = document.getElementById('dp-chart-modal');
    if (ml) ml.classList.remove('open');
  }
  function destroyTimelineCharts() {
    for (const c of S.timelineCharts) {
      c.destroy();
      const i = S.activeCharts.indexOf(c);
      if (i>=0) S.activeCharts.splice(i,1);
    }
    S.timelineCharts = [];
  }
  function destroyRentCharts() {
    for (const c of S.rentTimelineCharts) {
      c.destroy();
      const i = S.activeCharts.indexOf(c);
      if (i >= 0) S.activeCharts.splice(i, 1);
    }
    S.rentTimelineCharts = [];
  }

  function periodSlice(series) {
    if (!series.length) return series;
    if (S.period === 'all') return series;
    const today = new Date();
    const todayMonth = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`;
    const monthsBack = PERIODS.find(p => p.k === S.period).months;
    const cutoffDate = new Date(today.getFullYear(), today.getMonth() - monthsBack + 1, 1);
    const cutoff = `${cutoffDate.getFullYear()}-${String(cutoffDate.getMonth()+1).padStart(2,'0')}`;
    return series.filter(p => {
      const month = p.d.length === 10 ? p.d.slice(0,7) : p.d;
      return month >= cutoff && month <= todayMonth;
    });
  }
  function roomTimelineFor(a) {
    if (S.roomFilter === 'all') return a.timeline || [];
    return (a.timeline_by_rooms || {})[S.roomFilter] || [];
  }

  function renderPeriodChips() {
    return `<span class="pc-lbl">${t('sp_period_label')}:</span>` + PERIODS.map(p => {
      const cls = p.k === S.period ? ' active' : '';
      const label = t('period_'+p.k);
      if (S.periodHref) {
        return `<a class="period-chip${cls}" href="${_h(S.periodHref(p.k))}" data-dp-set-period="${_h(p.k)}">${_h(label)}</a>`;
      }
      return `<button class="period-chip${cls}" type="button" data-dp-set-period="${_h(p.k)}">${_h(label)}</button>`;
    }).join('');
  }
  function renderPeriodChipsRent() { return renderPeriodChips(); }

  function computeStatsSale(a) {
    const base = roomTimelineFor(a);
    const slice = periodSlice(base);
    let n = 0, total = 0;
    const meds = [], ppsqms = [];
    for (const p of slice) {
      n     += (p.n || 0);
      total += (p.vol || 0);
      if (p.med)   meds.push(p.med);
      if (p.ppsqm) ppsqms.push(p.ppsqm);
    }
    return { n, total, med: medOf(meds), med_ppsqm: medOf(ppsqms) };
  }
  function renderStatsSale(a) {
    const s = computeStatsSale(a);
    return `
        <div class="dp-stat dp-stat--avg"><div class="k">${t("sc_median_price")}</div><div class="v">${s.med ? fmtAedDP(s.med) : '—'}</div></div>
        <div class="dp-stat dp-stat--count"><div class="k">${t("sc_trans")}</div><div class="v">${fmtInt(s.n)}</div></div>
        <div class="dp-stat dp-stat--vol"><div class="k">${t("sc_volume")}</div><div class="v">${fmtAedDP(s.total)}</div></div>
        <div class="dp-stat dp-stat--ppsqm"><div class="k">${t("sc_price_psqm")}</div><div class="v">${s.med_ppsqm ? fmtInt(s.med_ppsqm)+' AED' : '—'}</div></div>
    `;
  }
  function computeStatsRent(r) {

    const slice = periodSlice(roomTimelineFor(r));
    let n = 0;
    const meds = [], ppsqms = [];
    for (const p of slice) {
      n += (p.n || 0);
      if (p.med)   meds.push(p.med);
      if (p.ppsqm) ppsqms.push(p.ppsqm);
    }
    return { n, med_annual: medOf(meds), med_ppsqm: medOf(ppsqms) };
  }
  function renderStatsRent(r) {
    const s = computeStatsRent(r);

    const monthly = (S.rentUnit === 'monthly');
    const med = monthly ? Math.round((s.med_annual || 0) / 12) : s.med_annual;
    const medLabel = monthly
      ? `${t("rent_sc_med_annual")} (${t("rent_toggle_monthly")})`
      : t("rent_sc_med_annual");
    const dur = r.med_dur_months;
    const durHtml = (dur && dur > 0) ? `
        <div class="dp-stat"><div class="k">${t("rent_sc_dur")}</div><div class="v">${dur.toFixed(0)} ${t("rent_unit_months")}</div></div>` : '';
    return `
        <div class="dp-stat"><div class="k">${t("rent_sc_contracts")}</div><div class="v">${fmtInt(s.n)}</div></div>
        <div class="dp-stat dp-stat-toggle">
          <div class="k">${medLabel}</div>
          <div class="v">${med ? fmtAedDP(med) : '—'}</div>
          <button class="dp-unit-toggle" type="button" data-dp-rent-unit="${monthly ? 'annual' : 'monthly'}" title="${t(monthly ? 'rent_toggle_annual' : 'rent_toggle_monthly')}" aria-label="${t(monthly ? 'rent_toggle_annual' : 'rent_toggle_monthly')}">${monthly ? t('rent_toggle_annual') : t('rent_toggle_monthly')}</button>
        </div>
        <div class="dp-stat"><div class="k">${t("rent_sc_ppsqm")}</div><div class="v">${s.med_ppsqm ? fmtInt(s.med_ppsqm)+' AED' : '—'}</div></div>
        ${durHtml}
    `;
  }

  function renderRoomChips(a) {
    const tbr = a.timeline_by_rooms || {};
    const bu  = a.by_rooms_unit || {};
    return ROOM_ORDER.map(k => {
      const n = k === 'all' ? a.n : (bu[k] ? bu[k].n : 0);
      const disabled = k !== 'all' && (!tbr[k] || !tbr[k].length);
      if (disabled) return '';
      const active = (k === S.roomFilter) ? ' active' : '';
      const color  = ROOM_COLORS[k];
      const style  = (k === S.roomFilter) ? ` style="background:${color};border-color:${color};color:#fff"` : '';
      return `<button class="room-chip${active}" data-dp-set-room="${k}"${style}>${roomLabel(k)}<span class="chip-n">${fmtInt(n)}</span></button>`;
    }).join('');
  }
  function renderRoomBreakdown(a) {
    
    const bu = a.by_rooms_unit || {};
    const tbr = a.timeline_by_rooms || {};
    const anyData = ROOM_BREAKDOWN.some(k => (bu[k] && bu[k].n > 0) || (tbr[k] && tbr[k].length));
    if (!anyData) return '';

    const chips = ROOM_BREAKDOWN.map(k => {
      const total = (bu[k] && bu[k].n) || 0;
      if (total === 0) return '';  
      const hidden = (S.roomBreakdownHidden && S.roomBreakdownHidden.has(k));
      const color  = ROOM_COLORS[k] || '#94a3b8';
      const style  = hidden
        ? `background:#f1f5f9;border-color:#cbd5e1;color:#94a3b8`
        : `background:${color};border-color:${color};color:#fff`;
      return `<button class="rb-chip" type="button" data-dp-toggle-room="${_h(k)}" style="${style}" aria-pressed="${hidden ? 'false' : 'true'}">${roomBreakdownIcon(k)} ${roomLabel(k)}<span class="rb-chip-n">${fmtInt(total)}</span></button>`;
    }).join('');
    return `
      <div class="dp-section">
        <h3>${t('rooms_breakdown_title')}</h3>
        <div class="rb-legend" id="dp-rb-legend">${chips}</div>
        <div class="dp-chart" style="height:240px">
          <button class="chart-expand-btn" type="button" data-dp-expand-rooms="1" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
          <canvas id="ch-room-breakdown"></canvas>
        </div>
      </div>
    `;
  }
  function _roomBreakdownSeries(a) {

    const tbr = a.timeline_by_rooms || {};
    const used = ROOM_BREAKDOWN.filter(k => tbr[k] && tbr[k].length);
    if (!used.length) return null;

    const labelSet = new Set();
    const slicesByRoom = {};
    for (const k of used) {
      const slice = periodSlice(tbr[k]);
      slicesByRoom[k] = slice;
      for (const row of slice) labelSet.add(row.d);
    }
    const sparseLabels = Array.from(labelSet).sort();

    function monthIndex(d) {
      const [y, m] = d.split('-').map(Number);
      return y * 12 + (m - 1);
    }
    function indexToYM(idx) {
      return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2,'0')}`;
    }
    const startIdx = monthIndex(sparseLabels[0]);
    const endIdx = monthIndex(sparseLabels[sparseLabels.length - 1]);
    const refLabels = [];
    for (let i = startIdx; i <= endIdx; i++) refLabels.push(indexToYM(i));
    const matrix = new Map();
    for (const d of refLabels) matrix.set(d, {});
    for (const k of used) {
      for (const row of slicesByRoom[k]) {
        const cell = matrix.get(row.d);
        if (cell) cell[k] = (cell[k] || 0) + (row.n || 0);
      }
    }

    const months = refLabels.length;
    const bucketSize = months <= 24 ? 1
                     : months <= 48 ? 3
                     : months <= 96 ? 6
                     : months <= 144 ? 12
                     : 24;
    const buckets = [];
    for (let i = 0; i < refLabels.length; i += bucketSize) {
      const slab = refLabels.slice(i, i + bucketSize);
      const label = bucketSize === 1
        ? slab[0].slice(2)  
        : bucketSize === 12
          ? slab[0].slice(0, 4)  
          : slab[0].slice(0,7) + '…' + slab[slab.length-1].slice(2,7);
      const totals = {};
      for (const d of slab) {
        const cell = matrix.get(d) || {};
        for (const k of used) totals[k] = (totals[k] || 0) + (cell[k] || 0);
      }
      buckets.push({ label, totals });
    }
    return { labels: buckets.map(b => b.label), buckets, used };
  }
  function renderRoomBreakdownChart(a) {
    const ctx = document.getElementById('ch-room-breakdown');
    if (!ctx) return;
    const ser = _roomBreakdownSeries(a);
    if (!ser) return;
    const hidden = S.roomBreakdownHidden || new Set();
    
    S.roomChartData = ser;
    const datasets = ser.used.map(k => ({
      label: roomLabel(k),
      data: ser.buckets.map(b => b.totals[k] || 0),
      backgroundColor: ROOM_COLORS[k] || '#94a3b8',
      borderWidth: 0,
      stack: 'rooms',
      hidden: hidden.has(k),
      _roomKey: k,
    }));
    const ch = new Chart(ctx, {
      type: 'bar',
      data: { labels: ser.labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: false },  
          tooltip: { callbacks: { label: c => ' ' + c.dataset.label + ': ' + fmtInt(c.parsed.y) } },
        },
        scales: {
          x: { stacked: true, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } },
          y: { stacked: true, ticks: { font: { size: 10 } }, beginAtZero: true },
        },
      },
    });
    S.activeCharts.push(ch);
    S.roomBreakdownChart = ch;
  }
  function refreshRoomBreakdown() {
    const rec = _roomsRec();
    if (!rec) return;
    const legend = S.container && S.container.querySelector('#dp-rb-legend');
    if (legend) {
      
      const tmp = document.createElement('div');
      tmp.innerHTML = renderRoomBreakdown(rec);
      const fresh = tmp.querySelector('#dp-rb-legend');
      if (fresh) legend.innerHTML = fresh.innerHTML;
    }

    if (S.roomBreakdownChart) {
      const idx = S.activeCharts.indexOf(S.roomBreakdownChart);
      if (idx >= 0) S.activeCharts.splice(idx, 1);
      S.roomBreakdownChart.destroy();
      S.roomBreakdownChart = null;
    }
    renderRoomBreakdownChart(rec);
  }
  function openRoomChartModal() {

    if (!S.roomChartData) return;
    const ser = S.roomChartData;
    const hidden = S.roomBreakdownHidden || new Set();
    const el = _modalDOM();
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = 'none';
    el.querySelector('#dp-cm-title').textContent = t('rooms_breakdown_title');
    
    const totals = ser.buckets.map(b => Object.values(b.totals).reduce((s,v)=>s+v,0));
    const trend = linearTrend(totals);
    const trendLine = trend ? totals.map((_, i) => Math.max(0, trend.intercept + trend.slope * i)) : null;
    const grand = totals.reduce((s,v)=>s+v,0);
    const badges = [];
    badges.push(`<span class="cm-badge muted">Σ ${fmtInt(grand)}</span>`);
    if (trend) badges.push(`<span class="cm-badge ${trend.slope>=0?'pos':'neg'}">${t('ch_trend')}: ${trend.slope>=0?'↑':'↓'} ${Math.abs(trend.slope).toFixed(1)}/bin</span>`);
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');
    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    el.classList.add('open');
    const ctx = el.querySelector('#dp-cm-canvas');
    const datasets = ser.used.map(k => ({
      type: 'bar',
      label: roomLabel(k),
      data: ser.buckets.map(b => b.totals[k] || 0),
      backgroundColor: ROOM_COLORS[k] || '#94a3b8',
      borderWidth: 0,
      stack: 'rooms',
      hidden: hidden.has(k),
    }));
    if (trendLine) {
      datasets.push({
        type: 'line',
        label: t('ch_trend'),
        data: trendLine,
        borderColor: '#0f172a',
        borderWidth: 1.5,
        borderDash: [5,4],
        pointRadius: 0,
        fill: false,
        order: 0,
      });
    }
    S.modalChart = new Chart(ctx, {
      data: { labels: ser.labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 14, font: { size: 11 } } },
          tooltip: { callbacks: { label: c => ' ' + c.dataset.label + ': ' + fmtInt(c.parsed.y) } },
        },
        scales: {
          x: { stacked: true, ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 20 } },
          y: { stacked: true, ticks: { font: { size: 11 } }, beginAtZero: true },
        },
      },
    });
  }

  const VINTAGE_ORDER = ['v0_3', 'v4_8', 'v9p'];
  const VINTAGE_COLORS = { v0_3: '#16a34a', v4_8: '#0ea5e9', v9p: '#64748b' };
  function _vintageBuckets(rec) {
    const v = rec && rec.vintage;
    if (!v) return null;
    const present = VINTAGE_ORDER.filter(b => v[b] && v[b].ppsqm);
    return present.length >= 2 ? present : null;
  }
  function renderVintageSection(rec, kind) {
    if (!_vintageBuckets(rec)) return '';
    const hasTl = kind === 'sale' && rec.vintage_timeline;
    const bars = `
          <div>
            ${hasTl ? `<div style="font-size:11px;color:#666;margin-bottom:2px">${t('vin_now')}</div>` : ''}
            <div class="dp-chart" style="height:170px"><canvas id="ch-vintage-${kind}"></canvas></div>
          </div>`;
    const tl = hasTl ? `
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t('vin_history')}</div>
            <div class="dp-chart" style="height:170px"><canvas id="ch-vintage-tl"></canvas></div>
          </div>` : '';
    const paths = (rec.vintage_paths && Object.keys(rec.vintage_paths).length >= 2) ? `
        <div style="margin-top:10px">
          <div style="font-size:11px;color:#666;margin-bottom:2px">${t(kind === 'rent' ? 'vin_paths_rent' : 'vin_paths')}</div>
          <div class="dp-chart" style="height:210px">
            <button class="chart-expand-btn" type="button" data-dp-expand="vintage_paths" data-dp-source="${kind}" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
            <canvas id="ch-vintage-paths-${kind}"></canvas>
          </div>
        </div>` : '';
    return `
      <div class="dp-section">
        <h3>${t('dp_section_vintage')}</h3>
        <div style="display:grid;grid-template-columns:${hasTl ? '1fr 2fr' : '1fr'};gap:10px">
          ${bars}${tl}
        </div>
        ${paths}
        <div style="font-size:11px;color:#666;margin-top:4px">${t('vintage_hint')}</div>
      </div>`;
  }
  function renderVintagePaths(rec, kind) {
    kind = kind || 'sale';
    const ctx = document.getElementById('ch-vintage-paths-' + kind);
    const vp = rec && rec.vintage_paths;
    if (!ctx || !vp) return;
    const unit = kind === 'rent' ? ' AED/м²/' + t('unit_year_short') : ' AED/м²';
    // Every 2nd cohort keeps the fan readable; each line = the buildings
    // that traded in year Y, followed from Y to today.
    const cohorts = Object.keys(vp).sort().filter(y => (+y) % 2 === 0 && vp[y].length >= 3);
    if (cohorts.length < 2) return;
    const years = [...new Set(cohorts.flatMap(c => vp[c].map(p => p.d)))].sort();
    const m = cohorts.length;
    const datasets = cohorts.map((c, i) => {
      const byYear = new Map(vp[c].map(p => [p.d, p]));
      const buy = vp[c][0].med;
      return {
        label: c,
        data: years.map(y => { const p = byYear.get(y); return p ? p.med : null; }),
        borderColor: `hsl(${255 - Math.round(i / Math.max(m - 1, 1) * 235)}, 62%, 46%)`,
        backgroundColor: 'transparent',
        borderWidth: 1.6,
        pointRadius: 0.5,
        tension: 0.25,
        spanGaps: true,
        _buy: buy,
      };
    });
    const ch = new Chart(ctx, {
      type: 'line',
      data: { labels: years, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 10, font: { size: 9 } } },
          tooltip: { callbacks: { label: c => {
            const buy = c.dataset._buy;
            const rel = buy ? Math.round((c.parsed.y / buy - 1) * 100) : null;
            return ' ' + c.dataset.label + ': ' + fmtInt(c.parsed.y) + unit
              + (rel === null || c.label === c.dataset.label ? '' : ' (' + (rel >= 0 ? '+' : '') + rel + '% ' + t('vin_since_buy') + ')');
          } } },
        },
        scales: {
          x: { ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true } },
          y: { ticks: { font: { size: 10 } } },
        },
      },
    });
    S.activeCharts.push(ch);
  }
  function _vintageTimelineSeries(a) {
    const vt = a.vintage_timeline;
    if (!vt) return null;
    const room = vt[S.roomFilter] ? S.roomFilter : 'all';
    const byB = vt[room];
    if (!byB) return null;
    const sliced = {};
    const months = new Set();
    for (const b of VINTAGE_ORDER) {
      const s = periodSlice(byB[b] || []);
      if (s.length) {
        sliced[b] = new Map(s.map(p => [p.d, p]));
        s.forEach(p => months.add(p.d));
      }
    }
    const keys = VINTAGE_ORDER.filter(b => sliced[b]);
    if (keys.length < 2) return null;
    const ref = [...months].sort();
    const bs = ref.length <= 24 ? 1 : ref.length <= 48 ? 3 : ref.length <= 96 ? 6 : 12;
    const labels = [];
    const data = {};
    keys.forEach(b => { data[b] = []; });
    for (let i = 0; i < ref.length; i += bs) {
      const slab = ref.slice(i, i + bs);
      labels.push(bs === 1 ? slab[0].slice(2) : bs === 12 ? slab[0].slice(0, 4) : slab[0].slice(2));
      for (const b of keys) {
        let n = 0, wsum = 0;
        for (const m of slab) {
          const p = sliced[b].get(m);
          if (p) { n += p.n; wsum += p.med * p.n; }
        }
        data[b].push(n ? Math.round(wsum / n) : null);
      }
    }
    return { labels, data, keys };
  }
  function renderVintageTimeline(a) {
    const ctx = document.getElementById('ch-vintage-tl');
    if (!ctx) return;
    const ser = _vintageTimelineSeries(a);
    if (!ser) return;
    const names = { v0_3: t('vin_new'), v4_8: t('vin_mid'), v9p: t('vin_old') };
    const ch = new Chart(ctx, {
      type: 'line',
      data: {
        labels: ser.labels,
        datasets: ser.keys.map(b => ({
          label: names[b],
          data: ser.data[b],
          borderColor: VINTAGE_COLORS[b],
          backgroundColor: 'transparent',
          borderWidth: 1.8,
          pointRadius: 0.5,
          tension: 0.3,
          spanGaps: true,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } },
          tooltip: { callbacks: { label: c => ' ' + c.dataset.label + ': ' + fmtInt(c.parsed.y) + ' AED/м²' } },
        },
        scales: {
          x: { ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
          y: { ticks: { font: { size: 10 } } },
        },
      },
    });
    S.activeCharts.push(ch);
  }
  function renderVintageChart(rec, kind) {
    const ctx = document.getElementById('ch-vintage-' + kind);
    const present = _vintageBuckets(rec);
    if (!ctx || !present) return;
    const labels = { v0_3: t('vin_new'), v4_8: t('vin_mid'), v9p: t('vin_old') };
    const vals = present.map(b => rec.vintage[b].ppsqm);
    const ns   = present.map(b => rec.vintage[b].n);
    const base = rec.vintage[present[0]].ppsqm;
    const unit = kind === 'rent' ? ' AED/м²/' + t('unit_year_short') : ' AED/м²';
    const ch = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: present.map(b => labels[b]),
        datasets: [{
          data: vals,
          backgroundColor: present.map(b => VINTAGE_COLORS[b]),
          borderWidth: 0,
          barPercentage: 0.55,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => {
            const i = c.dataIndex;
            const rel = base ? Math.round((vals[i] / base - 1) * 100) : 0;
            const relTxt = i === 0 ? '' : ' · ' + (rel >= 0 ? '+' : '') + rel + '% ' + t('vin_vs_new');
            return ' ' + fmtInt(vals[i]) + unit + ' · n=' + fmtInt(ns[i]) + relTxt;
          } } },
        },
        scales: {
          x: { ticks: { font: { size: 11 } } },
          y: { ticks: { font: { size: 10 } }, beginAtZero: true },
        },
      },
    });
    S.activeCharts.push(ch);
  }
  function renderBodySale(a) {
    return `
      <div class="period-chips" id="dp-period-chips">${renderPeriodChips()}</div>
      <div class="dp-stats" id="dp-stats-sale">${renderStatsSale(a)}</div>

      <div class="dp-section">
        <h3>${t("sp_section_timeline")}</h3>
        <div class="room-chips" id="dp-room-chips">${renderRoomChips(a)}</div>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px">
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_avg")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="avg" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-timeline-avg"></canvas>
            </div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_count")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="count" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-timeline-count"></canvas>
            </div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_volume")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="volume" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-timeline-volume"></canvas>
            </div>
          </div>
        </div>
      </div>

      ${renderRoomBreakdown(a)}

      ${renderVintageSection(a, 'sale')}

      <div class="dp-section">
        <h3>${t("sp_section_insights")}</h3>
        <div class="dp-donut-grid">
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("sp_section_offplan")}</div>
            <div class="dp-chart dp-donut" style="height:160px">
              <button class="chart-expand-btn" type="button" data-dp-expand-donut="offplan" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-offplan"></canvas>
            </div>
            <div class="dp-donut-foot">${t('donut_offplan_hint')}</div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("donut_proj_title")}</div>
            <div class="dp-chart dp-donut" style="height:160px">
              <button class="chart-expand-btn" type="button" data-dp-expand-donut="projects" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-donut-projects"></canvas>
            </div>
            <div class="dp-donut-foot">${listLinkFooter('top_projects', t('open_full_top_projects'))}</div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("donut_deals_title")}</div>
            <div class="dp-chart dp-donut" style="height:160px">
              <button class="chart-expand-btn" type="button" data-dp-expand-donut="deals" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-donut-deals"></canvas>
            </div>
            <div class="dp-donut-foot">${listLinkFooter('top_deals', t('open_full_top_deals'))}</div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("donut_recent_title")}</div>
            <div class="dp-chart dp-donut" style="height:160px">
              <button class="chart-expand-btn" type="button" data-dp-expand-donut="recent" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-donut-recent"></canvas>
            </div>
            <div class="dp-donut-foot">${listLinkFooter('recent', t('open_full_recent'))}</div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("donut_payment_title")}</div>
            <div class="dp-chart dp-donut" style="height:160px">
              <button class="chart-expand-btn" type="button" data-dp-expand-donut="payment" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-donut-payment"></canvas>
            </div>
            <div class="dp-donut-foot">${t('donut_payment_hint')}</div>
          </div>
        </div>
      </div>
    `;
  }
  function listLinkFooter(field, label) {
    const href = S.listLinks && S.listLinks[field];
    if (!href) return '';
    return `<div class="dp-section-more"><a href="${href}">${label} →</a></div>`;
  }
  function renderBodyRent(r) {
    if (!r || !r.n) {
      return `<div class="dp-empty">${t('rent_no_data')}</div>`;
    }

    const sub = r.by_subtype || {};
    const subSorted = Object.entries(sub).sort((a,b) => b[1].n - a[1].n);
    const sub_rows = subSorted.map(([k, v]) => `
      <tr><td>${_h(k)}</td><td class="num">${fmtInt(v.n)}</td><td class="num">${fmtAedDP(v.med)}</td><td class="num">${fmtInt(v.med_ppsqm)}</td></tr>`).join('');
    const proj_rows = (r.top_projects||[]).map(p => `<tr><td>${projName(p.proj)}</td><td class="num">${fmtInt(p.n)}</td><td class="num">${fmtAedDP(p.med)}</td></tr>`).join('');
    const recent_rows = (r.recent||[]).map(d => {
      const vTag = d.v === 'N' ? t('rent_v_new') : t('rent_v_renew');
      return `<tr><td>${_h(d.d)}</td><td>${projName(d.proj)}</td><td>${_h(d.sub)}</td><td class="num">${d.sqm ? fmtInt(d.sqm) : '—'}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-g dp-tag-g-${d.v==='N'?'O':'R'}">${_h(vTag)}</span></td></tr>`;
    }).join('');

    const hasRooms = !!(r.by_rooms_unit && Object.keys(r.by_rooms_unit).length);

    return `
      <div class="period-chips" id="dp-period-chips-rent">${renderPeriodChipsRent()}</div>
      <div class="dp-stats" id="dp-stats-rent">${renderStatsRent(r)}</div>

      <div class="dp-section">
        <h3>${t("rent_section_timeline")}</h3>
        ${hasRooms ? `<div class="room-chips" id="dp-room-chips-rent">${renderRoomChips(r)}</div>` : ''}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_count")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="count" data-dp-source="rent" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-rent-count"></canvas>
            </div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("rent_th_med")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="med" data-dp-source="rent" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-rent-med"></canvas>
            </div>
          </div>
        </div>
      </div>

      ${hasRooms ? renderRoomBreakdown(r) : ''}

      ${renderVintageSection(r, 'rent')}

      <div class="dp-section">
        <h3>${t("sp_section_insights")}</h3>
        <div class="dp-donut-grid">
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("rent_donut_subtype")}</div>
            <div class="dp-chart dp-donut" style="height:160px"><canvas id="ch-rent-donut-subtype"></canvas></div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("rent_donut_usage")}</div>
            <div class="dp-chart dp-donut" style="height:160px"><canvas id="ch-rent-donut-usage"></canvas></div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("rent_donut_tenant")}</div>
            <div class="dp-chart dp-donut" style="height:160px"><canvas id="ch-rent-donut-tenant"></canvas></div>
          </div>
          <div class="dp-donut-card">
            <div class="dp-donut-title">${t("rent_sc_versions")}</div>
            <div class="dp-chart dp-donut" style="height:160px"><canvas id="ch-rent-donut-newrenew"></canvas></div>
          </div>
        </div>
      </div>

      ${sub_rows ? `<details class="dp-collapsible">
        <summary>${t("rent_section_subtype")}</summary>
        <table class="dp-table"><thead><tr><th>${t("rent_th_subtype")}</th><th class="num">${t("th_n")}</th><th class="num">${t("rent_th_med")}</th><th class="num">${t("rent_th_ppsqm")}</th></tr></thead><tbody>${sub_rows}</tbody></table>
      </details>` : ''}

      ${proj_rows ? `<details class="dp-collapsible" data-tier="premium">
        <summary>${t("rent_section_top_projects")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_project")}</th><th class="num">${t("th_n")}</th><th class="num">${t("rent_th_med")}</th></tr></thead><tbody>${proj_rows}</tbody></table>
        ${listLinkFooter('top_projects', t('open_full_top_projects'))}
      </details>` : ''}

      ${recent_rows ? `<details class="dp-collapsible" data-tier="premium">
        <summary>${t("rent_section_recent")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("rent_th_subtype")}</th><th class="num">${t("th_sqm")}</th><th class="num">${t("th_aed")}</th><th>${t("rent_th_version")}</th></tr></thead><tbody>${recent_rows}</tbody></table>
        ${listLinkFooter('recent', t('open_full_recent'))}
      </details>` : ''}
    `;
  }
  function renderBody(sale, rent, mode) {
    if (mode === 'sale') {
      return `<div class="dp-tab-pane active" id="dp-pane-sale">${sale ? renderBodySale(sale) : `<div class="dp-empty">${t('alert_not_found')}</div>`}</div>`;
    }
    if (mode === 'rent') {
      return `<div class="dp-tab-pane active" id="dp-pane-rent">${renderBodyRent(rent)}</div>`;
    }
    
    const saleCount = sale ? sale.n : 0;
    const rentCount = rent ? rent.n : 0;
    return `
      <div class="dp-tabs">
        <button class="dp-tab active" data-dp-tab="sale" type="button">${t('tab_sale')}<span class="tab-n">${fmtInt(saleCount)}</span></button>
        <button class="dp-tab" data-dp-tab="rent" type="button">${t('tab_rent')}<span class="tab-n">${fmtInt(rentCount)}</span></button>
      </div>
      <div class="dp-tab-pane active" id="dp-pane-sale">${sale ? renderBodySale(sale) : `<div class="dp-empty">${t('alert_not_found')}</div>`}</div>
      <div class="dp-tab-pane" id="dp-pane-rent">${renderBodyRent(rent)}</div>
    `;
  }

  function rgba(hex, alpha) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return `rgba(29,78,216,${alpha})`;
    return `rgba(${parseInt(m[1],16)},${parseInt(m[2],16)},${parseInt(m[3],16)},${alpha})`;
  }

  function movingAverage(arr, w) {
    const out = new Array(arr.length).fill(NaN);
    let s = 0, c = 0;
    for (let i = 0; i < arr.length; i++) {
      s += arr[i]; c++;
      if (c > w) { s -= arr[i-w]; c--; }
      if (i >= w - 1) out[i] = s / w;
    }
    return out;
  }
  function rollingStddev(arr, ma, w) {
    const out = new Array(arr.length).fill(NaN);
    for (let i = w - 1; i < arr.length; i++) {
      let v = 0;
      for (let j = i - w + 1; j <= i; j++) v += (arr[j] - ma[i]) ** 2;
      out[i] = Math.sqrt(v / w);
    }
    return out;
  }
  
  function linearTrend(arr) {
    const xs = [], ys = [];
    for (let i = 0; i < arr.length; i++) {
      if (Number.isFinite(arr[i])) { xs.push(i); ys.push(arr[i]); }
    }
    if (xs.length < 2) return null;
    const n = xs.length;
    const mx = xs.reduce((a,b)=>a+b,0)/n;
    const my = ys.reduce((a,b)=>a+b,0)/n;
    let num=0, den=0;
    for (let k=0; k<n; k++) { num += (xs[k]-mx)*(ys[k]-my); den += (xs[k]-mx)**2; }
    if (den === 0) return null;
    const slope = num/den;
    const intercept = my - slope*mx;
    return { slope, intercept };
  }

  function yoyPercent(arr) {
    if (arr.length < 13) return null;
    const last = arr[arr.length - 1];
    const prev = arr[arr.length - 13];
    if (!prev) return null;
    return ((last - prev) / prev) * 100;
  }
  function renderTimelineCharts(a) {
    const series = periodSlice(roomTimelineFor(a));
    const labels = series.map(p => p.d.length === 10 ? p.d.slice(5) : p.d);
    const baseColor = ROOM_COLORS[S.roomFilter] || '#1d4ed8';
    // Per-metric colors: avg=indigo (price), count=sky (activity), volume=teal (accumulated money).
    // Kept independent of the room filter so the three timeline charts always read as three
    // distinct series regardless of whether you're looking at Все / Studio / 1BR / 2BR / …
    const perMetric = { avg: '#4f46e5', count: '#0284c7', volume: '#0d9488' };

    S.chartData = {
      labels: labels.slice(),
      fullLabels: series.map(p => p.d),
      count:  { values: series.map(p => p.n),                                    fmtY: v => v,        fmtTip: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(), label: t('sp_subsection_count'),  color: perMetric.count },
      volume: { values: series.map(p => p.vol || 0),                             fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                                label: t('sp_subsection_volume'), color: perMetric.volume },
      avg:    { values: series.map(p => p.n ? Math.round(p.vol / p.n) : 0),      fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                                label: t('sp_subsection_avg'),    color: perMetric.avg },
      color: baseColor,
    };
    const mkChart = (id, data, fmtY, tooltipFmt, color) => {
      const ctx = document.getElementById(id);
      if (!ctx) return;
      const bg = rgba(color, .14);
      const ch = new Chart(ctx, {
        type:'line',
        data:{ labels, datasets:[{ data, borderColor:color, backgroundColor:bg, tension:.3, pointRadius:1.5, fill:true }]},
        options:{
          responsive:true, maintainAspectRatio:false,
          interaction:{intersect:false, mode:'index'},
          plugins:{legend:{display:false}, tooltip:{callbacks:{label: c => ' ' + tooltipFmt(c.parsed.y)}}},
          scales:{
            y:{ticks:{font:{size:10}, callback: fmtY}, beginAtZero:true},
            x:{ticks:{font:{size:10}, maxRotation:0, autoSkip:true, maxTicksLimit:6}},
          }
        }
      });
      S.activeCharts.push(ch);
      S.timelineCharts.push(ch);
    };
    mkChart('ch-timeline-avg',    S.chartData.avg.values,    S.chartData.avg.fmtY,    S.chartData.avg.fmtTip,    S.chartData.avg.color);
    mkChart('ch-timeline-count',  S.chartData.count.values,  S.chartData.count.fmtY,  S.chartData.count.fmtTip,  S.chartData.count.color);
    mkChart('ch-timeline-volume', S.chartData.volume.values, S.chartData.volume.fmtY, S.chartData.volume.fmtTip, S.chartData.volume.color);
  }

  function _maWindow(n) {

    if (n <= 18) return 3;
    if (n <= 48) return 6;
    return 12;
  }
  function _modalDOM() {
    let el = document.getElementById('dp-chart-modal');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'dp-chart-modal';
    el.className = 'chart-modal';
    el.setAttribute('role','dialog');
    el.setAttribute('aria-modal','true');
    el.innerHTML = `
      <div class="chart-modal-inner">
        <div class="chart-modal-head">
          <h3 id="dp-cm-title">…</h3>
          <div class="chart-modal-badges" id="dp-cm-badges"></div>
          <div class="chart-modal-engines" id="dp-cm-engines">
            <button class="cm-engine active" type="button" data-dp-engine="chartjs">Chart.js</button>
            <button class="cm-engine" type="button" data-dp-engine="echarts">ECharts</button>
          </div>
          <button class="chart-modal-close" id="dp-cm-close" type="button" aria-label="Close">✕</button>
        </div>
        <div class="chart-modal-controls" id="dp-cm-controls">
          <div class="period-chips" id="dp-cm-periods"></div>
          <div class="room-chips" id="dp-cm-rooms"></div>
        </div>
        <div class="chart-modal-body">
          <canvas id="dp-cm-canvas"></canvas>
          <div id="dp-cm-echarts" class="chart-modal-echarts" style="display:none"></div>
        </div>
      </div>`;
    document.body.appendChild(el);
    return el;
  }
  function _closeChartModal() {
    const el = document.getElementById('dp-chart-modal');
    if (!el) return;
    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    if (S.echartsInstance) {
      if (S.echartsInstance._measureTeardown) S.echartsInstance._measureTeardown();
      S.echartsInstance.dispose();
      S.echartsInstance = null;
    }
    const overlay = document.getElementById('dp-cm-measure-overlay');
    if (overlay) overlay.remove();
    const engines = el.querySelector('#dp-cm-engines');
    if (engines) engines.style.display = '';
    el.classList.remove('open');
    delete el.dataset.metric;
    delete el.dataset.source;
  }
  function openVintagePathsModal(source) {
    source = source || 'sale';
    const rec = source === 'rent' ? S.rent : S.sale;
    const vp = rec && (rec.vintage_paths_m || rec.vintage_paths);
    if (!vp) return;
    const monthly = !!rec.vintage_paths_m;
    const unit = source === 'rent' ? ' AED/м²/' + t('unit_year_short') : ' AED/м²';
    const cohorts = Object.keys(vp).sort().filter(y => vp[y].length >= (monthly ? 12 : 3));
    if (cohorts.length < 2) return;

    const el = _modalDOM();
    el.dataset.metric = 'vintage_paths';
    el.dataset.source = source;
    el.querySelector('#dp-cm-title').textContent = t(source === 'rent' ? 'vin_paths_rent' : 'vin_paths');
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = 'none';
    const engines = el.querySelector('#dp-cm-engines');
    if (engines) engines.style.display = 'none';

    const axis = [...new Set(cohorts.flatMap(c => vp[c].map(p => p.d)))].sort();
    const m = cohorts.length;
    // NaN-tolerant trailing MA: cohort arrays live on a shared axis with
    // leading NaNs and gap months — the shared movingAverage() keeps a
    // running sum that a single NaN poisons permanently.
    const maNan = (arr, w) => arr.map((_, i) => {
      let s = 0, c = 0;
      for (let j = Math.max(0, i - w + 1); j <= i; j++) {
        const v = arr[j];
        if (Number.isFinite(v)) { s += v; c++; }
      }
      return c >= Math.max(2, Math.ceil(w / 2)) ? s / c : NaN;
    });
    const perf = [];
    const datasets = cohorts.map((c, i) => {
      const byD = new Map(vp[c].map(p => [p.d, p]));
      const raw = axis.map(d => { const p = byD.get(d); return p ? p.med : NaN; });
      // Purchase baseline = the cohort's first 12 months (its seed year).
      const seedVals = vp[c].filter(p => p.d.slice(0, 4) === c).map(p => p.med);
      const buy = seedVals.length
        ? seedVals.reduce((a, b) => a + b, 0) / seedVals.length
        : vp[c][0].med;
      const w = monthly ? _maWindow(vp[c].length) : 1;
      const smooth = w > 1 ? maNan(raw, w) : raw;
      const lastReal = [...vp[c]].reverse()[0];
      perf.push({ c, buy, last: lastReal.med, ret: buy ? (lastReal.med / buy - 1) * 100 : null });
      return {
        label: c,
        data: smooth.map(v => Number.isFinite(v) ? Math.round(v) : null),
        borderColor: `hsl(${255 - Math.round(i / Math.max(m - 1, 1) * 235)}, 62%, 46%)`,
        backgroundColor: 'transparent',
        borderWidth: 1.8,
        pointRadius: 0,
        tension: 0.25,
        spanGaps: true,
        _buy: buy,
        _raw: raw,
      };
    });

    const ranked = perf.filter(p => p.ret !== null).sort((a, b) => b.ret - a.ret);
    const badges = [];
    if (ranked.length) {
      const bst = ranked[0], wst = ranked[ranked.length - 1];
      badges.push(`<span class="cm-badge pos">${t('vin_best')}: ${bst.c} ${bst.ret >= 0 ? '+' : ''}${Math.round(bst.ret)}%</span>`);
      badges.push(`<span class="cm-badge ${wst.ret >= 0 ? 'muted' : 'neg'}">${t('vin_worst')}: ${wst.c} ${wst.ret >= 0 ? '+' : ''}${Math.round(wst.ret)}%</span>`);
    }
    if (monthly) badges.push(`<span class="cm-badge muted">${t('vin_smoothing')}</span>`);
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');

    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    if (S.echartsInstance) { S.echartsInstance.dispose(); S.echartsInstance = null; }
    const ec = el.querySelector('#dp-cm-echarts');
    if (ec) ec.style.display = 'none';
    const canvas = el.querySelector('#dp-cm-canvas');
    canvas.style.display = '';
    el.classList.add('open');

    S.modalChart = new Chart(canvas, {
      type: 'line',
      data: { labels: axis.map(d => monthly ? d : d), datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'nearest', axis: 'x' },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: c => {
            const rawV = c.dataset._raw && c.dataset._raw[c.dataIndex];
            const v = Number.isFinite(rawV) ? rawV : c.parsed.y;
            const buy = c.dataset._buy;
            const rel = buy ? Math.round((v / buy - 1) * 100) : null;
            return ' ' + c.dataset.label + ': ' + fmtInt(v) + unit
              + (rel === null ? '' : ' (' + (rel >= 0 ? '+' : '') + rel + '% ' + t('vin_since_buy') + ')');
          } } },
        },
        scales: {
          x: { ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 18 } },
          y: { ticks: { font: { size: 11 }, callback: v => fmtInt(v) } },
        },
      },
    });
  }
  function openChartModal(metric, source) {
    source = source || 'sale';
    if (metric === 'vintage_paths') { openVintagePathsModal(source); return; }
    const cd = source === 'rent' ? S.rentChartData : S.chartData;
    if (!cd || !cd[metric]) return;
    const m = cd[metric];
    const labels = cd.labels.slice();
    const data = m.values.slice();
    if (data.length < 2) return;  

    const w = _maWindow(data.length);
    const ma = movingAverage(data, w);
    const sd = rollingStddev(data, ma, w);
    const upper = ma.map((v, i) => Number.isFinite(v) ? v + 1.5 * sd[i] : NaN);
    const lower = ma.map((v, i) => Number.isFinite(v) ? v - 1.5 * sd[i] : NaN);
    const trend = linearTrend(data);
    const trendLine = trend ? data.map((_, i) => trend.intercept + trend.slope * i) : null;
    const median = (() => {
      const arr = data.filter(v => Number.isFinite(v) && v > 0).sort((a,b)=>a-b);
      if (!arr.length) return null;
      const mid = Math.floor(arr.length/2);
      return arr.length % 2 ? arr[mid] : (arr[mid-1]+arr[mid])/2;
    })();
    const yoy = yoyPercent(data);
    const lastVal = data[data.length - 1];
    const lastMa = ma[ma.length - 1];
    const lastSpread = Number.isFinite(lastMa) && lastMa ? ((lastVal - lastMa) / lastMa) * 100 : null;
    const meanVal = data.reduce((a,b)=>a+b,0)/data.length;
    const stdAll = Math.sqrt(data.reduce((s,v)=>s+(v-meanVal)**2,0)/data.length);
    const vol = meanVal ? (stdAll / meanVal) * 100 : null;

    const color = m.color || cd.color || '#1d4ed8';
    const grnLine = 'rgba(34,197,94,1)';
    const redLine = 'rgba(239,68,68,1)';
    const grnFill = 'rgba(34,197,94,0.16)';
    const redFill = 'rgba(239,68,68,0.18)';

    const el = _modalDOM();
    el.dataset.metric = metric;
    el.dataset.source = source;
    el.querySelector('#dp-cm-title').textContent = m.label;
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = '';
    const pchips = el.querySelector('#dp-cm-periods');
    if (pchips) pchips.innerHTML = renderPeriodChips();
    const rchips = el.querySelector('#dp-cm-rooms');
    const roomsSource = source === 'rent' ? S.rent : S.sale;
    if (rchips) rchips.innerHTML = roomsSource ? renderRoomChips(roomsSource) : '';
    const badges = [];
    const badge = (cls, label, val, tip) =>
      `<span class="cm-badge ${cls}" data-tip="${_h(tip)}"><span class="cm-badge-label">${_h(label)}</span> <span class="cm-badge-val">${val}</span></span>`;
    if (yoy != null)        badges.push(badge(yoy>=0?'pos':'neg',       t('bd_yoy'),   (yoy>=0?'+':'')+yoy.toFixed(1)+'%',                 t('bd_yoy_tip')));
    if (lastSpread != null) badges.push(badge(lastSpread>=0?'pos':'neg', t('bd_vsma').replace('{w}', w), (lastSpread>=0?'+':'')+lastSpread.toFixed(1)+'%', t('bd_vsma_tip').replace('{w}', w)));
    if (vol != null)        badges.push(badge('muted',                   t('bd_vol'),   vol.toFixed(0)+'%',                                 t('bd_vol_tip')));
    if (trend)              badges.push(badge(trend.slope>=0?'pos':'neg', t('bd_trend'), trend.slope>=0?t('bd_trend_up'):t('bd_trend_dn'), t('bd_trend_tip')));
    badges.push(badge('muted', t('bd_n'), data.length, t('bd_n_tip')));
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');

    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    if (S.echartsInstance) {
      if (S.echartsInstance._measureTeardown) S.echartsInstance._measureTeardown();
      S.echartsInstance.dispose();
      S.echartsInstance = null;
    }
    const _oldOverlay = document.getElementById('dp-cm-measure-overlay');
    if (_oldOverlay) _oldOverlay.remove();
    el.classList.add('open');

    // Sync engine toggle UI
    el.querySelectorAll('.cm-engine').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.dpEngine === S.modalEngine);
    });
    const canvasEl = el.querySelector('#dp-cm-canvas');
    const echartsEl = el.querySelector('#dp-cm-echarts');

    if (S.modalEngine === 'echarts') {
      canvasEl.style.display = 'none';
      echartsEl.style.display = '';
      echartsEl.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-size:13px">${t('chart_loading') || 'Loading…'}</div>`;
      _ensureECharts().then(() => {
        // If the modal was closed or switched to Chart.js while loading, bail out
        const still = document.getElementById('dp-chart-modal');
        if (!still || !still.classList.contains('open') || S.modalEngine !== 'echarts' || still.dataset.metric !== metric || (still.dataset.source || 'sale') !== source) return;
        echartsEl.innerHTML = '';
        _renderModalECharts({ el: echartsEl, labels, data, ma, upper, lower, trendLine, median, w, color, m });
      }).catch(err => {
        echartsEl.innerHTML = `<div style="padding:20px;color:#dc2626;font-size:12px">ECharts failed to load. Reverting to Chart.js.</div>`;
        console.error('ECharts load failed:', err);
        S.modalEngine = 'chartjs';
        el.querySelectorAll('.cm-engine').forEach(btn => btn.classList.toggle('active', btn.dataset.dpEngine === 'chartjs'));
        canvasEl.style.display = '';
        echartsEl.style.display = 'none';
        _renderModalChartJs({ ctx: canvasEl, labels, data, ma, upper, lower, trendLine, median, w, color, m, grnLine, redLine, grnFill, redFill });
      });
    } else {
      canvasEl.style.display = '';
      echartsEl.style.display = 'none';
      _renderModalChartJs({ ctx: canvasEl, labels, data, ma, upper, lower, trendLine, median, w, color, m, grnLine, redLine, grnFill, redFill });
    }
  }

  let _echartsPromise = null;
  function _ensureECharts() {
    if (typeof echarts !== 'undefined') return Promise.resolve();
    if (_echartsPromise) return _echartsPromise;
    _echartsPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-dp-echarts]');
      if (existing) {
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js';
      s.crossOrigin = 'anonymous';
      s.integrity = 'sha384-Mx5lkUEQPM1pOJCwFtUICyX45KNojXbkWdYhkKUKsbv391mavbfoAmONbzkgYPzR';
      s.setAttribute('data-dp-echarts', '1');
      s.onload = () => resolve();
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return _echartsPromise;
  }

  function _renderModalChartJs({ ctx, labels, data, ma, upper, lower, trendLine, median, w, color, m, grnLine, redLine, grnFill, redFill }) {
    S.modalChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'lower', data: lower, borderWidth: 0, pointRadius: 0, fill: false, order: 6 },
          { label: t('ch_channel'), data: upper, borderColor: 'rgba(148,163,184,0.55)', borderWidth: 1, borderDash:[3,3], pointRadius: 0, fill: '-1', backgroundColor: 'rgba(148,163,184,0.10)', order: 5 },
          { label: t('ch_ma') + ` (${w})`, data: ma, borderColor: '#64748b', borderWidth: 1.5, borderDash: [6,4], pointRadius: 0, fill: false, order: 4 },
          ...(trendLine ? [{ label: t('ch_trend'), data: trendLine, borderColor: '#0f172a', borderWidth: 1.2, borderDash:[2,3], pointRadius: 0, fill: false, order: 3 }] : []),
          ...(median != null ? [{ label: t('ch_median'), data: data.map(()=>median), borderColor: 'rgba(29,78,216,0.55)', borderWidth: 1, borderDash:[1,2], pointRadius: 0, fill: false, order: 2 }] : []),
          {
            label: m.label,
            data,
            borderColor: color,
            borderWidth: 2.5,
            pointRadius: 2.2,
            pointHoverRadius: 4,
            fill: { target: 2, above: grnFill, below: redFill },
            segment: {
              borderColor: ctx => {
                const i = ctx.p0DataIndex;
                if (i >= ma.length - 1) return color;
                const v1 = data[i+1];
                if (!Number.isFinite(ma[i+1])) return color;
                if (v1 > ma[i+1]) return grnLine;
                if (v1 < ma[i+1]) return redLine;
                return color;
              },
            },
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 14, font: { size: 11 }, filter: (item) => item.text !== 'lower' } },
          tooltip: { callbacks: { label: c => ' ' + (c.dataset.label || '') + ': ' + m.fmtTip(c.parsed.y) } },
        },
        scales: {
          y: { ticks: { font: { size: 11 }, callback: m.fmtY }, beginAtZero: true },
          x: { ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } },
        },
      },
    });
  }

  function _renderModalECharts({ el, labels, data, ma, upper, lower, trendLine, median, w, color, m }) {
    const clean = arr => arr.map(v => Number.isFinite(v) ? v : null);
    const bandOffset = ma.map((v, i) => Number.isFinite(v) && Number.isFinite(upper[i]) ? upper[i] - v : null);
    const inst = echarts.init(el, null, { renderer: 'canvas' });
    S.echartsInstance = inst;

    // Segmented main series: split into green (above MA) / red (below MA) sub-series
    const above = data.map((v, i) => (Number.isFinite(ma[i]) && v >= ma[i]) ? v : null);
    const below = data.map((v, i) => (Number.isFinite(ma[i]) && v <  ma[i]) ? v : null);

    inst.setOption({
      grid: { left: 56, right: 24, top: 18, bottom: 44 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: '#94a3b8' } },
        backgroundColor: 'rgba(15,23,42,0.94)',
        borderColor: 'transparent',
        textStyle: { color: '#f1f5f9', fontSize: 12 },
        padding: [8, 12],
        formatter: params => {
          const pName = params[0].name;
          const hidden = new Set(['band-anchor', t('ch_channel'), 'above-ma', 'below-ma']);
          const idx = params[0].dataIndex;
          const bandU = Number.isFinite(upper[idx]) ? Math.round(upper[idx]) : null;
          const bandL = Number.isFinite(lower[idx]) ? Math.round(lower[idx]) : null;
          const rows = params
            .filter(p => p.value != null && !hidden.has(p.seriesName))
            .map(p => `<div style="display:flex;justify-content:space-between;gap:12px">
              <span>${p.marker} ${p.seriesName}</span>
              <span style="font-variant-numeric:tabular-nums;font-weight:600">${m.fmtTip(Math.round(p.value))}</span>
            </div>`)
            .join('');
          const bandRow = (bandU != null && bandL != null)
            ? `<div style="display:flex;justify-content:space-between;gap:12px;opacity:.75">
                 <span>${t('ch_channel')}</span>
                 <span style="font-variant-numeric:tabular-nums">${m.fmtTip(bandL)} – ${m.fmtTip(bandU)}</span>
               </div>`
            : '';
          return `<div style="opacity:.75;font-size:11px;margin-bottom:4px">${pName}</div>${rows}${bandRow}`;
        },
      },
      legend: {
        bottom: 0, itemGap: 16, textStyle: { fontSize: 11, color: '#475569' },
        icon: 'roundRect', itemWidth: 12, itemHeight: 8,
        data: [
          m.label,
          t('ch_ma') + ` (${w})`,
          ...(trendLine ? [t('ch_trend')] : []),
          ...(median != null ? [t('ch_median')] : []),
          t('ch_channel'),
        ],
      },
      xAxis: {
        type: 'category', data: labels,
        axisLabel: { fontSize: 10, color: '#64748b' },
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { fontSize: 10, color: '#64748b', formatter: m.fmtY },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        axisLine: { show: false }, axisTick: { show: false },
      },
      series: [
        // Bollinger band (anchor + stackable delta = filled area between lower and upper)
        {
          name: 'band-anchor', type: 'line', data: clean(lower),
          lineStyle: { opacity: 0 }, symbol: 'none', stack: 'band', silent: true,
          areaStyle: { opacity: 0 },
        },
        {
          name: t('ch_channel'), type: 'line', data: clean(bandOffset),
          lineStyle: { opacity: 0 }, symbol: 'none', stack: 'band', silent: true,
          itemStyle: { color: 'rgba(148,163,184,0.7)' },
          areaStyle: { color: 'rgba(148,163,184,0.14)' },
        },
        // Moving average
        {
          name: t('ch_ma') + ` (${w})`, type: 'line', data: clean(ma),
          smooth: true, symbol: 'none',
          itemStyle: { color: '#64748b' },
          lineStyle: { color: '#64748b', width: 1.4, type: 'dashed' },
        },
        // Trend line
        ...(trendLine ? [{
          name: t('ch_trend'), type: 'line', data: clean(trendLine),
          smooth: false, symbol: 'none',
          itemStyle: { color: '#0f172a' },
          lineStyle: { color: '#0f172a', width: 1.2, type: [3, 4] },
        }] : []),
        // Median line
        ...(median != null ? [{
          name: t('ch_median'), type: 'line', data: data.map(() => median),
          symbol: 'none',
          itemStyle: { color: 'rgba(29,78,216,0.7)' },
          lineStyle: { color: 'rgba(29,78,216,0.5)', width: 1, type: [2, 3] },
        }] : []),
        // Main series with gradient area under
        {
          name: m.label, type: 'line', data,
          smooth: true, symbol: 'circle', symbolSize: 5,
          itemStyle: { color },
          lineStyle: { color, width: 2.5, shadowColor: color, shadowBlur: 6, shadowOffsetY: 2 },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: color + 'CC' },
              { offset: 1, color: color + '10' },
            ]),
          },
          emphasis: { focus: 'series', scale: 1.4 },
        },
        // Green overlay: points above MA (highlight)
        {
          name: 'above-ma', type: 'line', data: above,
          symbol: 'circle', symbolSize: 6, showSymbol: true,
          lineStyle: { opacity: 0 }, itemStyle: { color: '#22c55e' },
          tooltip: { show: false }, silent: true,
        },
        // Red overlay: points below MA
        {
          name: 'below-ma', type: 'line', data: below,
          symbol: 'circle', symbolSize: 6, showSymbol: true,
          lineStyle: { opacity: 0 }, itemStyle: { color: '#ef4444' },
          tooltip: { show: false }, silent: true,
        },
      ],
      animationDuration: 420, animationEasing: 'cubicOut',
    });

    // Auto-resize when window changes
    if (!el._echartsResizeHooked) {
      el._echartsResizeHooked = true;
      window.addEventListener('resize', () => S.echartsInstance && S.echartsInstance.resize());
    }

    _installEChartsMeasureTool(inst, { labels, data, color, m });
  }

  function _installEChartsMeasureTool(inst, { labels, data, color, m }) {
    let anchorIdx = null;
    let currentIdx = null;
    let dragging = false;

    const clampIdx = i => Math.max(0, Math.min(labels.length - 1, i));

    const idxAt = (offsetX, offsetY) => {
      if (!inst.containPixel({ gridIndex: 0 }, [offsetX, offsetY])) return null;
      const gridRect = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
      if (!gridRect || labels.length < 2) return null;
      const t = (offsetX - gridRect.x) / gridRect.width;
      const idx = t * (labels.length - 1);
      if (!Number.isFinite(idx)) return null;
      return clampIdx(Math.round(idx));
    };

    const paint = () => {
      if (anchorIdx == null) {
        inst.setOption({ graphic: [] }, { replaceMerge: 'graphic' });
        return;
      }
      const grid = inst.getModel().getComponent('grid', 0).coordinateSystem.getRect();
      const gTop = grid.y;
      const gBottom = grid.y + grid.height;

      const idxToPx = i => grid.x + (labels.length > 1 ? (i / (labels.length - 1)) * grid.width : grid.width / 2);
      const yToPx = v => {
        const px = inst.convertToPixel({ yAxisIndex: 0 }, v);
        return Number.isFinite(px) ? px : null;
      };

      const aPx = idxToPx(anchorIdx);
      const aVal = data[anchorIdx];
      const aValPx = Number.isFinite(aVal) ? yToPx(aVal) : null;

      const cIdx = currentIdx != null ? currentIdx : anchorIdx;
      const cPx = idxToPx(cIdx);
      const cVal = data[cIdx];
      const cValPx = Number.isFinite(cVal) ? yToPx(cVal) : null;

      const isRange = cIdx !== anchorIdx;
      const dx = cPx - aPx;
      const delta = (Number.isFinite(aVal) && Number.isFinite(cVal)) ? cVal - aVal : null;
      const pctDelta = (delta != null && aVal) ? (delta / aVal) * 100 : null;
      const monthsDelta = cIdx - anchorIdx;
      const deltaColor = delta == null ? '#334155' : (delta >= 0 ? '#16a34a' : '#dc2626');
      const deltaBg = delta == null ? '#f1f5f9' : (delta >= 0 ? '#dcfce7' : '#fee2e2');

      // Info panel content
      const fmt = v => Number.isFinite(v) ? m.fmtTip(Math.round(v)) : '—';
      const sign = v => v == null ? '' : (v > 0 ? '+' : '');
      const lines = [];
      lines.push(`<div style="opacity:.7;font-size:10px">${t('ch_measure_from') || 'От'}</div>`);
      lines.push(`<div style="font-weight:600">${labels[anchorIdx]}</div>`);
      lines.push(`<div style="font-variant-numeric:tabular-nums">${fmt(aVal)}</div>`);
      if (isRange) {
        lines.push(`<div style="opacity:.7;font-size:10px;margin-top:6px">${t('ch_measure_to') || 'До'}</div>`);
        lines.push(`<div style="font-weight:600">${labels[cIdx]}</div>`);
        lines.push(`<div style="font-variant-numeric:tabular-nums">${fmt(cVal)}</div>`);
        if (delta != null) {
          lines.push(`<div style="margin-top:8px;padding:4px 6px;border-radius:4px;background:${deltaBg};color:${deltaColor};font-weight:600;font-variant-numeric:tabular-nums">
            ${sign(delta)}${fmt(delta)} (${sign(pctDelta)}${pctDelta.toFixed(1)}%)
          </div>`);
        }
        const monthsLabel = Math.abs(monthsDelta) === 1
          ? (t('ch_measure_month') || 'мес.')
          : (t('ch_measure_months') || 'мес.');
        lines.push(`<div style="opacity:.65;font-size:10px;margin-top:4px">Δ ${Math.abs(monthsDelta)} ${monthsLabel}</div>`);
      } else {
        lines.push(`<div style="opacity:.55;font-size:10px;margin-top:8px;line-height:1.4">${t('ch_measure_hint') || 'Тяните курсор в сторону для сравнения'}</div>`);
      }

      // Position info panel — right of the range, else left of it, else pinned to a corner
      const chartW = inst.getWidth();
      const panelW = 200;
      const rightPx = Math.max(aPx, cPx);
      const leftPx  = Math.min(aPx, cPx);
      const gap = 12;
      let panelX;
      if (chartW - rightPx - gap >= panelW + 8) {
        panelX = rightPx + gap;
      } else if (leftPx - gap >= panelW + 8) {
        panelX = leftPx - panelW - gap;
      } else {
        // Both sides too tight — dock top-right of the chart above the range
        panelX = chartW - panelW - gap;
      }
      const panelY = gTop + 8;

      const graphics = [
        // Span rectangle (only when range)
        ...(isRange ? [{
          type: 'rect',
          shape: { x: Math.min(aPx, cPx), y: gTop, width: Math.abs(dx), height: gBottom - gTop },
          style: { fill: 'rgba(29,78,216,0.06)', stroke: 'transparent' },
          silent: true, z: 5,
        }] : []),
        // Anchor vertical line
        {
          type: 'line',
          shape: { x1: aPx, y1: gTop, x2: aPx, y2: gBottom },
          style: { stroke: color, lineWidth: 1.5, lineDash: [4, 3] },
          silent: true, z: 6,
        },
        // Anchor value dot
        ...(aValPx != null ? [{
          type: 'circle',
          shape: { cx: aPx, cy: aValPx, r: 5 },
          style: { fill: color, stroke: '#fff', lineWidth: 2 },
          silent: true, z: 7,
        }] : []),
        // Current vertical line + dot (when different)
        ...(isRange ? [
          {
            type: 'line',
            shape: { x1: cPx, y1: gTop, x2: cPx, y2: gBottom },
            style: { stroke: deltaColor, lineWidth: 1.5, lineDash: [4, 3] },
            silent: true, z: 6,
          },
          ...(cValPx != null ? [{
            type: 'circle',
            shape: { cx: cPx, cy: cValPx, r: 5 },
            style: { fill: deltaColor, stroke: '#fff', lineWidth: 2 },
            silent: true, z: 7,
          }] : []),
        ] : []),
      ];

      inst.setOption({ graphic: graphics }, { replaceMerge: 'graphic' });
      _paintMeasureHtml(inst, panelX, panelY, panelW, lines.join(''));
    };

    const zr = inst.getZr();

    zr.on('mousedown', (e) => {
      const idx = idxAt(e.offsetX, e.offsetY);
      if (idx == null) return;
      anchorIdx = idx;
      currentIdx = idx;
      dragging = true;
      paint();
    });

    zr.on('mousemove', (e) => {
      if (!dragging) return;
      const idx = idxAt(e.offsetX, e.offsetY);
      if (idx == null) return;
      currentIdx = idx;
      paint();
    });

    zr.on('mouseup', () => {
      dragging = false;
    });

    zr.on('globalout', () => {
      dragging = false;
    });

    // Store cleanup for engine switching
    inst._measureTeardown = () => {
      const overlay = document.getElementById('dp-cm-measure-overlay');
      if (overlay) overlay.remove();
      anchorIdx = null;
      currentIdx = null;
      dragging = false;
    };
  }

  function _paintMeasureHtml(inst, x, y, w, html) {
    const container = inst.getDom();
    // ensure relative positioning so absolute child is anchored correctly
    if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
    let overlay = document.getElementById('dp-cm-measure-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'dp-cm-measure-overlay';
      overlay.style.cssText = 'position:absolute;pointer-events:none;padding:10px;font-size:11px;line-height:1.35;color:#0f172a;box-sizing:border-box;background:rgba(255,255,255,0.98);border:1px solid #e2e8f0;border-radius:6px;box-shadow:0 3px 12px rgba(15,23,42,0.12)';
      container.appendChild(overlay);
    }
    overlay.style.left = x + 'px';
    overlay.style.top = y + 'px';
    overlay.style.width = w + 'px';
    overlay.innerHTML = html;
  }

  const DONUT_FALLBACK_COLORS = ['#1d4ed8','#0ea5e9','#22c55e','#eab308','#f97316','#ef4444','#a855f7','#ec4899','#14b8a6','#64748b'];
  const OP_COLORS = { 'Off-Plan': '#f0a020', 'Ready': '#21918c' };
  const ROOM_DONUT_COLORS = {
    'Studio': '#9ca3af',
    '1BR': '#60a5fa', '2BR': '#3b82f6', '3BR': '#1d4ed8', '4BR+': '#1e3a8a',
    'Villa': '#d97706',
    'Other': '#a78bfa',
  };

  function _donutEmpty(canvasId, msg) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    const c2 = ctx.getContext('2d');
    c2.save();
    c2.clearRect(0, 0, ctx.width, ctx.height);
    c2.fillStyle = '#94a3b8';
    c2.font = '13px system-ui, -apple-system, sans-serif';
    c2.textAlign = 'center';
    c2.textBaseline = 'middle';
    c2.fillText(msg || '—', ctx.width/2, ctx.height/2);
    c2.restore();
  }
  function _donutPalette(n, hint) {
    if (hint && hint.length >= n) return hint.slice(0, n);
    const out = [];
    for (let i = 0; i < n; i++) out.push(DONUT_FALLBACK_COLORS[i % DONUT_FALLBACK_COLORS.length]);
    return out;
  }

  function _offplanData(a) {
    const op = a.offplan || {};
    const labels = Object.keys(op).filter(k => op[k] > 0);
    if (!labels.length) return null;
    return {
      labels,
      values: labels.map(k => op[k]),
      colors: labels.map(k => OP_COLORS[k] || '#64748b'),
      fmt: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(),
    };
  }

  function _projectsDonutData(a) {
    const list = (a.top_projects || []).filter(p => p.n > 0);
    if (!list.length) return null;
    const N = 8;
    const top = list.slice(0, N);
    const tail = list.slice(N);
    const tailN = tail.reduce((s,p) => s + (p.n||0), 0);
    const items = top.map(p => ({ name: p.proj || t('not_specified'), n: p.n, total: p.total }));
    if (tailN > 0) items.push({ name: t('donut_others'), n: tailN, total: tail.reduce((s,p)=>s+(p.total||0),0) });
    return {
      labels: items.map(i => i.name),
      values: items.map(i => i.n),
      totals: items.map(i => i.total),
      colors: _donutPalette(items.length),
      fmt: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(),
    };
  }

  function _dealsByYearData(a) {
    const list = (a.top_deals || []).filter(d => d.val > 0 && d.d);
    if (!list.length) return null;
    const byYear = new Map();
    for (const d of list) {
      const y = String(d.d).slice(0, 4);
      byYear.set(y, (byYear.get(y) || 0) + d.val);
    }
    const sorted = [...byYear.entries()].sort((a,b) => a[0].localeCompare(b[0]));
    return {
      labels: sorted.map(([y]) => y),
      values: sorted.map(([, v]) => v),
      colors: _donutPalette(sorted.length),
      fmt: fmtAedDP,
    };
  }

  function _recentByRoomData(a) {
    const list = (a.recent || []).filter(d => d.room);
    if (!list.length) return null;
    const order = ['Studio','1BR','2BR','3BR','4BR+','Villa','Other'];
    const counts = new Map();
    for (const d of list) {
      const k = d.room;
      counts.set(k, (counts.get(k) || 0) + 1);
    }
    const labels = order.filter(k => counts.has(k));
    for (const k of counts.keys()) if (!order.includes(k)) labels.push(k);
    return {
      labels,
      values: labels.map(k => counts.get(k)),
      colors: labels.map(k => ROOM_DONUT_COLORS[k] || '#64748b'),
      fmt: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(),
    };
  }

  function _paymentData(a) {
    const p = a.payment || {};
    const cash = p.cash || 0;
    const fin  = p.financed || 0;
    if (!(cash + fin)) return null;
    return {
      labels: [t('donut_payment_cash'), t('donut_payment_financed')],
      values: [cash, fin],
      colors: ['#0ea5e9', '#f59e0b'],
      fmt: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(),
    };
  }
  function _renderDonut(canvasId, d, opts) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    if (!d) { _donutEmpty(canvasId, t('donut_empty')); return null; }
    const ch = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: d.colors, borderWidth: 1, borderColor: '#fff' }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '58%',
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 9, font: { size: 10.5 }, padding: 5 } },
          tooltip: {
            callbacks: {
              label: c => {
                const total = c.dataset.data.reduce((s,v)=>s+v,0);
                const pct = total ? ((c.parsed/total)*100).toFixed(1) : 0;
                return ' ' + c.label + ': ' + d.fmt(c.parsed) + ' (' + pct + '%)';
              },
            },
          },
        },
        ...(opts || {}),
      },
    });
    S.activeCharts.push(ch);
    return ch;
  }
  function renderInsightDonuts(a) {
    
    S.donutData = {
      offplan:  _offplanData(a),
      projects: _projectsDonutData(a),
      deals:    _dealsByYearData(a),
      recent:   _recentByRoomData(a),
      payment:  _paymentData(a),
    };
    _renderDonut('ch-offplan',           S.donutData.offplan);
    _renderDonut('ch-donut-projects',    S.donutData.projects);
    _renderDonut('ch-donut-deals',       S.donutData.deals);
    _renderDonut('ch-donut-recent',      S.donutData.recent);
    _renderDonut('ch-donut-payment',     S.donutData.payment);
  }

  function openDonutModal(kind) {
    if (!S.donutData || !S.donutData[kind]) return;
    const d = S.donutData[kind];
    const titleKey = {
      offplan:  'sp_section_offplan',
      projects: 'donut_proj_title_full',
      deals:    'donut_deals_title_full',
      recent:   'donut_recent_title_full',
      payment:  'donut_payment_title_full',
    }[kind];
    const el = _modalDOM();
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = 'none';
    el.querySelector('#dp-cm-title').textContent = t(titleKey);
    const total = d.values.reduce((s,v)=>s+v,0);
    const leadIdx = d.values.indexOf(Math.max(...d.values));
    const leadLabel = d.labels[leadIdx];
    const leadPct = total ? (d.values[leadIdx]/total*100).toFixed(1) : 0;
    const badges = [
      `<span class="cm-badge muted">Σ ${d.fmt(total)}</span>`,
      `<span class="cm-badge pos">${t('donut_leader')}: ${_h(leadLabel)} (${leadPct}%)</span>`,
      `<span class="cm-badge muted">n=${d.labels.length}</span>`,
    ];
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');
    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    el.classList.add('open');
    const ctx = el.querySelector('#dp-cm-canvas');
    S.modalChart = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: d.colors, borderWidth: 2, borderColor: '#fff' }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '52%',
        plugins: {
          legend: { position: 'right', labels: { boxWidth: 14, font: { size: 12 }, padding: 8 } },
          tooltip: {
            callbacks: {
              label: c => {
                const sub = c.dataset.data.reduce((s,v)=>s+v,0);
                const pct = sub ? ((c.parsed/sub)*100).toFixed(1) : 0;
                return ' ' + c.label + ': ' + d.fmt(c.parsed) + ' (' + pct + '%)';
              },
            },
          },
        },
      },
    });
  }
  function renderSaleCharts(a) {
    renderTimelineCharts(a);
    try { renderRoomBreakdownChart(a); } catch(e) { console.error('rooms chart:', e); }
    try { renderVintageChart(a, 'sale'); } catch(e) { console.error('vintage chart:', e); }
    try { renderVintageTimeline(a); } catch(e) { console.error('vintage timeline:', e); }
    try { renderVintagePaths(a, 'sale'); } catch(e) { console.error('vintage paths:', e); }
    try { renderInsightDonuts(a);    } catch(e) { console.error('donuts:', e); }
  }

  function _rentSubtypeDonutData(r) {
    const sub = r.by_subtype || {};
    const entries = Object.entries(sub).map(([k, v]) => [k, v.n || 0]).filter(([, n]) => n > 0);
    if (!entries.length) return null;
    entries.sort((a,b) => b[1] - a[1]);
    const N = 6;
    const top = entries.slice(0, N);
    const tail = entries.slice(N);
    const tailN = tail.reduce((s, [, n]) => s + n, 0);
    const items = top.map(([k, n]) => ({ name: k, n }));
    if (tailN > 0) items.push({ name: t('rent_subtype_other'), n: tailN });
    return {
      labels: items.map(i => i.name),
      values: items.map(i => i.n),
      colors: _donutPalette(items.length),
      fmt: v => fmtInt(v) + ' ' + t('rent_sc_contracts').toLowerCase(),
    };
  }
  function _rentUsageDonutData(r) {
    const usage = r.by_usage || {};
    const entries = Object.entries(usage).filter(([, n]) => n > 0);
    if (!entries.length) return null;
    entries.sort((a,b) => b[1] - a[1]);
    return {
      labels: entries.map(([k]) => k),
      values: entries.map(([, n]) => n),
      colors: _donutPalette(entries.length),
      fmt: v => fmtInt(v) + ' ' + t('rent_sc_contracts').toLowerCase(),
    };
  }

  function _rentNewRenewDonutData(r) {
    const ne = r.new || 0;
    const re = r.renewed || 0;
    if (ne + re === 0) return null;
    return {
      labels: [t('rent_v_new_label'), t('rent_v_renew_label')],
      values: [ne, re],
      colors: ['#10b981', '#a78bfa'],
      fmt: v => fmtInt(v) + ' ' + t('rent_sc_contracts').toLowerCase(),
    };
  }

  function _rentTenantDonutData(r) {
    const tn = r.by_tenant || {};
    const label = { 'Person': t('rent_tenant_person'), 'Authority': t('rent_tenant_authority'), 'Unknown': t('rent_tenant_unknown') };
    const color = { 'Person': '#0ea5e9', 'Authority': '#f59e0b', 'Unknown': '#94a3b8' };
    const entries = Object.entries(tn).filter(([, n]) => n > 0);
    if (!entries.length) return null;
    entries.sort((a,b) => b[1] - a[1]);
    return {
      labels: entries.map(([k]) => label[k] || k),
      values: entries.map(([, n]) => n),
      colors: entries.map(([k]) => color[k] || '#64748b'),
      fmt: v => fmtInt(v) + ' ' + t('rent_sc_contracts').toLowerCase(),
    };
  }
  function renderRentCharts(r) {

    const tlSource = (r.timeline_by_rooms && S.roomFilter !== 'all' && r.timeline_by_rooms[S.roomFilter])
      ? r.timeline_by_rooms[S.roomFilter]
      : (r.timeline || []);
    const series = periodSlice(tlSource);
    const labels = series.map(p => p.d.length === 10 ? p.d.slice(5) : p.d);
    const fullLabels = series.map(p => p.d);
    const color = '#0ea5e9';
    const bg = 'rgba(14,165,233,.14)';
    const monthly = (S.rentUnit === 'monthly');
    const medVals = series.map(p => monthly ? Math.round((p.med || 0) / 12) : (p.med || 0));
    const cntVals = series.map(p => p.n);

    S.rentChartData = {
      labels: labels.slice(),
      fullLabels,
      count: { values: cntVals, fmtY: v => v,        fmtTip: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(), label: t('sp_subsection_count') },
      med:   { values: medVals, fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                            label: t('rent_th_med') },
      color,
    };
    const mkChart = (id, data, fmtY, tooltipFmt) => {
      const ctx = document.getElementById(id);
      if (!ctx) return;
      const ch = new Chart(ctx, {
        type:'line',
        data:{ labels, datasets:[{ data, borderColor:color, backgroundColor:bg, tension:.3, pointRadius:1.2, fill:true }]},
        options:{
          responsive:true, maintainAspectRatio:false,
          interaction:{intersect:false, mode:'index'},
          plugins:{legend:{display:false}, tooltip:{callbacks:{label: c => ' ' + tooltipFmt(c.parsed.y)}}},
          scales:{
            y:{ticks:{font:{size:10}, callback: fmtY}, beginAtZero:true},
            x:{ticks:{font:{size:10}, maxRotation:0, autoSkip:true, maxTicksLimit:6}},
          }
        }
      });
      S.activeCharts.push(ch);
      S.rentTimelineCharts.push(ch);
    };
    mkChart('ch-rent-count', series.map(p => p.n), v => v,        v => v + ' ' + t('ch_count').toLowerCase());
    mkChart('ch-rent-med',   medVals, fmtAxisAed, fmtAedDP);

    if (r.by_rooms_unit && Object.keys(r.by_rooms_unit).length) {
      try { renderRoomBreakdownChart(r); } catch(e) { console.error('rent rooms chart:', e); }
    }
    try { renderVintageChart(r, 'rent'); } catch(e) { console.error('rent vintage chart:', e); }
    try { renderVintagePaths(r, 'rent'); } catch(e) { console.error('rent vintage paths:', e); }
    
    try {
      _renderDonut('ch-rent-donut-subtype',  _rentSubtypeDonutData(r));
      _renderDonut('ch-rent-donut-usage',    _rentUsageDonutData(r));
      _renderDonut('ch-rent-donut-tenant',   _rentTenantDonutData(r));
      _renderDonut('ch-rent-donut-newrenew', _rentNewRenewDonutData(r));
    } catch(e) { console.error('rent donuts:', e); }
  }

  function bindDelegates() {
    if (S._bound) return;
    S._bound = true;
    
    document.addEventListener('click', (e) => {
      
      const tabBtn = e.target.closest('[data-dp-tab]');
      if (tabBtn && S.container && S.container.contains(tabBtn)) {
        const which = tabBtn.dataset.dpTab;
        S.container.querySelectorAll('.dp-tab').forEach(b => b.classList.toggle('active', b === tabBtn));
        S.container.querySelectorAll('.dp-tab-pane').forEach(p => {
          p.classList.toggle('active', p.id === 'dp-pane-' + which);
        });
        if (which === 'rent' && S.rent) {
          destroyRentCharts();
          renderRentCharts(S.rent);
        }
        return;
      }
      
      const modalEl = document.getElementById('dp-chart-modal');
      const inPanel = (node) => (S.container && S.container.contains(node)) || (modalEl && modalEl.contains(node));

      const periodBtn = e.target.closest('[data-dp-set-period]');
      if (periodBtn && inPanel(periodBtn)) {

        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
        e.preventDefault();
        const p = periodBtn.dataset.dpSetPeriod;
        if (S.period !== p) {
          S.period = p;
          if (S.periodHref && history.pushState) {
            history.pushState({period: p}, '', S.periodHref(p));
          }
          refreshSale();
          refreshRent();
          if (S.onPeriodChange) S.onPeriodChange(p);
        }
        return;
      }

      const engineBtn = e.target.closest('[data-dp-engine]');
      if (engineBtn && modalEl && modalEl.contains(engineBtn)) {
        const eng = engineBtn.dataset.dpEngine;
        if (S.modalEngine !== eng) {
          S.modalEngine = eng;
          try { localStorage.setItem('dp-modal-engine', eng); } catch (_) {}
          if (modalEl.dataset.metric) openChartModal(modalEl.dataset.metric, modalEl.dataset.source || 'sale');
        }
        return;
      }

      const roomBtn = e.target.closest('[data-dp-set-room]');
      if (roomBtn && inPanel(roomBtn)) {
        const k = roomBtn.dataset.dpSetRoom;
        if (S.roomFilter !== k) {
          S.roomFilter = k;
          if (S.sale) refreshSale();
          if (S.rent) refreshRent();
        }
        return;
      }
      
      const unitBtn = e.target.closest('[data-dp-rent-unit]');
      if (unitBtn && S.container && S.container.contains(unitBtn)) {
        const next = unitBtn.dataset.dpRentUnit;
        if (S.rentUnit !== next) {
          S.rentUnit = next;
          refreshRent();
        }
        return;
      }
      
      const expandBtn = e.target.closest('[data-dp-expand]');
      if (expandBtn && S.container && S.container.contains(expandBtn)) {
        e.preventDefault();
        openChartModal(expandBtn.dataset.dpExpand, expandBtn.dataset.dpSource || 'sale');
        return;
      }
      
      const expandRoomBtn = e.target.closest('[data-dp-expand-rooms]');
      if (expandRoomBtn && S.container && S.container.contains(expandRoomBtn)) {
        e.preventDefault();
        openRoomChartModal();
        return;
      }
      
      const expandDonutBtn = e.target.closest('[data-dp-expand-donut]');
      if (expandDonutBtn && S.container && S.container.contains(expandDonutBtn)) {
        e.preventDefault();
        openDonutModal(expandDonutBtn.dataset.dpExpandDonut);
        return;
      }
      
      const rbToggle = e.target.closest('[data-dp-toggle-room]');
      if (rbToggle && S.container && S.container.contains(rbToggle)) {
        const k = rbToggle.dataset.dpToggleRoom;
        if (!S.roomBreakdownHidden) S.roomBreakdownHidden = new Set();
        if (S.roomBreakdownHidden.has(k)) S.roomBreakdownHidden.delete(k);
        else S.roomBreakdownHidden.add(k);
        refreshRoomBreakdown();
        return;
      }
      
      if (e.target.id === 'dp-cm-close' || e.target.id === 'dp-chart-modal') {
        _closeChartModal();
        return;
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const el = document.getElementById('dp-chart-modal');
        if (el && el.classList.contains('open')) _closeChartModal();
      }
    });
  }
  function refreshSale() {
    if (!S.sale) return;
    const pc = S.container.querySelector('#dp-period-chips');
    if (pc) pc.innerHTML = renderPeriodChips();
    const rc = S.container.querySelector('#dp-room-chips');
    if (rc) rc.innerHTML = renderRoomChips(S.sale);
    const stEl = S.container.querySelector('#dp-stats-sale');
    if (stEl) stEl.innerHTML = renderStatsSale(S.sale);
    destroyTimelineCharts();
    renderTimelineCharts(S.sale);
    refreshRoomBreakdown();

    const modalEl = document.getElementById('dp-chart-modal');
    if (modalEl && modalEl.classList.contains('open') && modalEl.dataset.metric && (modalEl.dataset.source || 'sale') === 'sale') {
      openChartModal(modalEl.dataset.metric, 'sale');
    }
  }
  function refreshRent() {
    if (!S.rent) return;
    const pc = S.container.querySelector('#dp-period-chips-rent');
    if (pc) pc.innerHTML = renderPeriodChipsRent();
    const stEl = S.container.querySelector('#dp-stats-rent');
    if (stEl) stEl.innerHTML = renderStatsRent(S.rent);
    const rc = S.container.querySelector('#dp-room-chips-rent');
    if (rc) rc.innerHTML = renderRoomChips(S.rent);

    if (S.container.querySelector('#ch-rent-count')) {
      destroyRentCharts();
      renderRentCharts(S.rent);
      refreshRoomBreakdown();
    }

    const modalEl = document.getElementById('dp-chart-modal');
    if (modalEl && modalEl.classList.contains('open') && modalEl.dataset.metric && modalEl.dataset.source === 'rent') {
      openChartModal(modalEl.dataset.metric, 'rent');
    }
  }

  function mount({ container, sale, rent, title, isDubai, mode, initialPeriod, periodHref, onPeriodChange }) {
    if (!container) throw new Error('DetailPanel.mount: container required');
    destroyCharts();
    S.container       = container;
    S.sale            = sale  || null;
    S.rent            = rent  || null;
    S.isDubai         = !!isDubai;
    S.mode            = mode || 'both';
    S.period          = (initialPeriod && PERIODS.find(p => p.k === initialPeriod)) ? initialPeriod : 'all';
    S.roomFilter      = 'all';
    S.roomBreakdownHidden = new Set();
    S.periodHref      = (typeof periodHref === 'function') ? periodHref : null;
    S.onPeriodChange  = (typeof onPeriodChange === 'function') ? onPeriodChange : null;
    S.listLinks       = arguments[0].listLinks || null;
    container.innerHTML = renderBody(S.sale, S.rent, S.mode);
    if (title) {
      const titleEl = document.getElementById('dp-title');
      if (titleEl) titleEl.textContent = title;
    }
    bindDelegates();
    if (S.mode !== 'rent' && S.sale) renderSaleCharts(S.sale);
    if (S.mode === 'rent' && S.rent) renderRentCharts(S.rent);
  }

  window.DetailPanel = { mount };
})();
