
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
    modalEngine: (() => { try { return localStorage.getItem('dp-modal-engine') === 'echarts' ? 'echarts' : 'lwc'; } catch (_) { return 'lwc'; } })(),
    echartsInstance: null,
    lwcInstance: null,
  };

  function _roomsRec() { return S.sale || S.rent; }

  const PERIODS = [
    { k: '1y',  months: 12  },
    { k: '3y',  months: 36  },
    { k: '5y',  months: 60  },
    { k: '10y', months: 120 },
    { k: 'all', months: null },
  ];
  const ROOM_ORDER    = ['all','apartments','studio','1br','2br','3br','4br+','villa','other'];
  const ROOM_BREAKDOWN = ['studio','1br','2br','3br','4br+','villa','other'];
  const ROOM_COLORS   = { all:'#1d4ed8', apartments:'#16a34a', studio:'#9ca3af', '1br':'#60a5fa', '2br':'#3b82f6', '3br':'#1d4ed8', '4br+':'#1e3a8a', villa:'#d97706', other:'#a78bfa' };
  // Rooms that make up the "apartments" tab — everything except villa/other.
  const APARTMENT_ROOMS = ['studio','1br','2br','3br','4br+'];
  const KNOWN_BAD_POINTS = [
    { d: '2004-10', vol: 6278200 },
  ];
  function _stripKnownBadPoints(arr) {
    if (!arr || !arr.length) return arr;
    for (const bad of KNOWN_BAD_POINTS) {
      const i = arr.findIndex(p => p.d === bad.d && p.vol === bad.vol);
      if (i >= 0) arr.splice(i, 1);
    }
    return arr;
  }
  function _stripKnownBadFromRecord(a) {
    if (!a) return;
    _stripKnownBadPoints(a.timeline);
    if (a.timeline_by_rooms) {
      for (const room of Object.keys(a.timeline_by_rooms)) _stripKnownBadPoints(a.timeline_by_rooms[room]);
    }
  }
  function avgPrice(p) {
    return p.n ? Math.round(p.vol / p.n) : 0;
  }
  function medPrice(p, monthly) {
    return monthly ? Math.round((p.med || 0) / 12) : (p.med || 0);
  }

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
    if (k==='all')        return t('room_chip_all');
    if (k==='apartments') return t('room_all'); // reuses the "All apartments" string — accurate here, unlike for 'all'
    if (k==='villa')  return t('ru_villa');
    if (k==='other')  return t('ru_other');
    return {studio:'Studio','1br':'1BR','2br':'2BR','3br':'3BR','4br+':'4BR+'}[k];
  }

  // Client-side approximation: sums n/vol exactly across the apartment room
  // buckets, but med/ppsqm are an n-weighted average of each bucket's median —
  // not a true recomputed median. Good enough for a filter tab; not swapped
  // into the server-computed room buckets that feed vintage/breakdown charts.
  function _addApartmentsBucket(a) {
    if (!a) return;
    const tbr = a.timeline_by_rooms;
    const bu  = a.by_rooms_unit;
    if (tbr && !tbr.apartments) {
      const byDate = new Map();
      for (const room of APARTMENT_ROOMS) {
        for (const p of (tbr[room] || [])) {
          let e = byDate.get(p.d);
          if (!e) { e = { d: p.d, n: 0, vol: 0, medSum: 0, ppsqmSum: 0 }; byDate.set(p.d, e); }
          e.n   += p.n || 0;
          e.vol += p.vol || 0;
          e.medSum   += (p.med   || 0) * (p.n || 0);
          e.ppsqmSum += (p.ppsqm || 0) * (p.n || 0);
        }
      }
      tbr.apartments = Array.from(byDate.values())
        .sort((x, y) => x.d < y.d ? -1 : x.d > y.d ? 1 : 0)
        .map(e => ({
          d: e.d, n: e.n, vol: Math.round(e.vol),
          med:   e.n ? Math.round(e.medSum / e.n)   : 0,
          ppsqm: e.n ? Math.round(e.ppsqmSum / e.n) : 0,
        }));
    }
    if (bu && !bu.apartments) {
      let n = 0, vol = 0, medSum = 0, ppsqmSum = 0;
      for (const room of APARTMENT_ROOMS) {
        const r = bu[room];
        if (!r) continue;
        n += r.n || 0; vol += r.vol || 0;
        medSum   += (r.med   || 0) * (r.n || 0);
        ppsqmSum += (r.ppsqm || 0) * (r.n || 0);
      }
      bu.apartments = {
        n, vol: Math.round(vol),
        med:   n ? Math.round(medSum / n)   : 0,
        ppsqm: n ? Math.round(ppsqmSum / n) : 0,
      };
    }
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
    const today = new Date();
    const todayMonth = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`;
    // Current month is partial (DLD lags 1-2 weeks) — show only full months
    if (S.period === 'all') return series.filter(p => p.d.slice(0,7) < todayMonth);
    const monthsBack = PERIODS.find(p => p.k === S.period).months;
    const cutoffDate = new Date(today.getFullYear(), today.getMonth() - monthsBack, 1);
    const cutoff = `${cutoffDate.getFullYear()}-${String(cutoffDate.getMonth()+1).padStart(2,'0')}`;
    return series.filter(p => {
      const month = p.d.length === 10 ? p.d.slice(0,7) : p.d;
      return month >= cutoff && month < todayMonth;
    });
  }
  // Partial as_of month scaled by Mon–Fri working days (DLD doesn't register on weekends)
  function _projectedPoint(series, asOf) {
    if (!asOf || !series.length) return null;
    const last = series[series.length - 1];
    if (last.d !== asOf.slice(0, 7)) return null;
    const [y, m, day] = asOf.split('-').map(Number);
    const dim = new Date(y, m, 0).getDate();
    let done = 0, total = 0;
    for (let i = 1; i <= dim; i++) {
      const wd = new Date(y, m - 1, i).getDay();
      if (wd === 0 || wd === 6) continue;
      total++;
      if (i <= day) done++;
    }
    if (!done) return null;
    if (done >= total) return last;
    const f = total / done;
    return { ...last, n: Math.round(last.n * f), vol: Math.round((last.vol || 0) * f), est: { a: done, b: total } };
  }
  function _workdays(from, to) {
    let n = 0;
    for (const d = new Date(from); d <= to; d.setDate(d.getDate() + 1)) {
      const wd = d.getDay();
      if (wd !== 0 && wd !== 6) n++;
    }
    return n;
  }
  function _estNote(est) {
    return t('ch_est').replace('{a}', est.a).replace('{b}', est.b);
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
      return `<button class="rb-chip" type="button" data-dp-toggle-room="${_h(k)}" style="${style}" aria-pressed="${hidden ? 'false' : 'true'}">${roomLabel(k)}<span class="rb-chip-n">${fmtInt(total)}</span></button>`;
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
  const _monthIdx = d => +d.slice(0, 4) * 12 + (+d.slice(5, 7) - 1);
  // Group YYYY-MM months into calendar buckets (quarters, halves, years); drops the leading bucket the period cut through
  function _calendarBuckets(months, size) {
    const groups = new Map();
    for (const d of months) {
      const key = Math.floor(_monthIdx(d) / size);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(d);
    }
    let keys = [...groups.keys()].sort((x, y) => x - y);
    const per = PERIODS.find(x => x.k === S.period);
    if (per && per.months && keys.length > 1) {
      const now = new Date();
      if (keys[0] * size < now.getFullYear() * 12 + now.getMonth() - per.months) keys = keys.slice(1);
    }
    return keys.map(key => {
      const first = key * size, y = Math.floor(first / 12), yy = String(y % 100).padStart(2, '0');
      const sub = Math.floor((first % 12) / size) + 1;
      const label = size === 1 ? `${yy}-${String(first % 12 + 1).padStart(2, '0')}`
        : size === 3 ? `Q${sub} '${yy}`
        : size === 6 ? `H${sub} '${yy}`
        : size === 12 ? String(y)
        : `${y}–${String((y + 1) % 100).padStart(2, '0')}`;
      return { key, slab: groups.get(key), label };
    });
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

    function indexToYM(idx) {
      return `${Math.floor(idx / 12)}-${String((idx % 12) + 1).padStart(2,'0')}`;
    }
    const startIdx = _monthIdx(sparseLabels[0]);
    const endIdx = _monthIdx(sparseLabels[sparseLabels.length - 1]);
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
    const cal = _calendarBuckets(refLabels, bucketSize);
    const buckets = cal.map(({ key, slab, label }, i) => {
      const totals = {};
      for (const d of slab) {
        const cell = matrix.get(d) || {};
        for (const k of used) totals[k] = (totals[k] || 0) + (cell[k] || 0);
      }
      // Bucket still running at as_of → scale by elapsed working days, same rule as _projectedPoint (≤1y buckets only)
      let est = null;
      if (a.as_of && i === cal.length - 1 && bucketSize <= 12) {
        const [ay, am, ad] = a.as_of.split('-').map(Number);
        const [ly, lm] = slab[slab.length - 1].split('-').map(Number);
        // periodSlice drops the partial current month, so count only up to the last month we actually have
        const upTo = new Date(Math.min(new Date(ay, am - 1, ad), new Date(ly, lm, 0)));
        const start = new Date(Math.floor(key * bucketSize / 12), key * bucketSize % 12, 1);
        const end = new Date(start.getFullYear(), start.getMonth() + bucketSize, 0);
        if (upTo >= start && upTo < end) {
          const done = _workdays(start, upTo), total = _workdays(start, end);
          if (done) est = { a: done, b: total, f: total / done };
        }
      }
      return { label, totals, est };
    });
    return { labels: buckets.map(b => b.label), buckets, used };
  }
  function _roomForecast(ser, hidden) {
    const last = ser.buckets[ser.buckets.length - 1];
    if (!last || !last.est) return null;
    const actual = ser.used.filter(k => !hidden.has(k)).reduce((s, k) => s + (last.totals[k] || 0), 0);
    const extra = Math.round(actual * (last.est.f - 1));
    if (extra <= 0) return null;
    const idx = ser.buckets.length - 1;
    return {
      idx, actual, extra, est: last.est,
      dataset: {
        type: 'bar', label: t('ch_forecast'), stack: 'rooms', _forecast: true,
        data: ser.buckets.map((_, i) => i === idx ? extra : null),
        backgroundColor: 'rgba(148,163,184,0.12)', borderWidth: 0,
      },
    };
  }
  function _roomForecastTooltip(fc) {
    return {
      afterTitle: items => fc && items.length && items[0].dataIndex === fc.idx ? _estNote(fc.est) : '',
      label: c => ' ' + c.dataset.label + ': ' + (c.dataset._forecast ? '+' : '') + fmtInt(Math.round(c.parsed.y)),
      footer: items => fc && items.length && items[0].dataIndex === fc.idx ? t('ch_forecast_total') + ': ≈' + fmtInt(fc.actual + fc.extra) : '',
    };
  }
  // Dashed outline for the projected remainder of the running period
  const _forecastOutline = {
    id: 'forecastOutline',
    afterDatasetsDraw(chart) {
      chart.data.datasets.forEach((ds, i) => {
        if (!ds._forecast || !chart.isDatasetVisible(i)) return;
        chart.getDatasetMeta(i).data.forEach((bar, j) => {
          if (!ds.data[j]) return;
          const { x, y, base, width } = bar.getProps(['x', 'y', 'base', 'width'], true);
          const c = chart.ctx;
          c.save();
          c.setLineDash([4, 3]);
          c.strokeStyle = '#64748b';
          c.lineWidth = 1.2;
          c.strokeRect(x - width / 2 + 0.6, y + 0.6, width - 1.2, base - y - 1.2);
          c.restore();
        });
      });
    },
  };
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
    const fc = _roomForecast(ser, hidden);
    if (fc) datasets.push(fc.dataset);
    const ch = new Chart(ctx, {
      type: 'bar',
      data: { labels: ser.labels, datasets },
      plugins: [_forecastOutline],
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: false },  
          tooltip: { callbacks: _roomForecastTooltip(fc) },
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
    const fc = _roomForecast(ser, hidden);
    const trend = linearTrend(ser.buckets.map((b, i) => b.est ? totals[i] * b.est.f : totals[i]));
    const trendLine = trend ? totals.map((_, i) => Math.max(0, trend.intercept + trend.slope * i)) : null;
    const grand = totals.reduce((s,v)=>s+v,0);
    const badges = [];
    badges.push(`<span class="cm-badge muted">Σ ${fmtInt(grand)}</span>`);
    if (trend) badges.push(`<span class="cm-badge ${trend.slope>=0?'pos':'neg'}">${t('ch_trend')}: ${trend.slope>=0?'↑':'↓'} ${Math.abs(trend.slope).toFixed(1)}/bin</span>`);
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');
    delete el.dataset.metric;
    delete el.dataset.source;
    const ctx = _useCanvasPane(el);
    el.classList.add('open');
    const datasets = ser.used.map(k => ({
      type: 'bar',
      label: roomLabel(k),
      data: ser.buckets.map(b => b.totals[k] || 0),
      backgroundColor: ROOM_COLORS[k] || '#94a3b8',
      borderWidth: 0,
      stack: 'rooms',
      hidden: hidden.has(k),
    }));
    if (fc) datasets.push(fc.dataset);
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
      plugins: [_forecastOutline],
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: true, position: 'bottom', labels: { boxWidth: 14, font: { size: 11 } } },
          tooltip: { callbacks: _roomForecastTooltip(fc) },
        },
        scales: {
          x: { stacked: true, ticks: { font: { size: 11 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 20 } },
          y: { stacked: true, ticks: { font: { size: 11 } }, beginAtZero: true },
        },
      },
    });
  }

  const VINTAGE_ORDER = ['v0_1', 'v2_4', 'v5_10', 'v11p'];
  const VINTAGE_COLORS = { v0_1: '#16a34a', v2_4: '#0ea5e9', v5_10: '#f59e0b', v11p: '#64748b' };
  function _vintageBuckets(rec) {
    const v = rec && rec.vintage;
    if (!v) return null;
    const present = VINTAGE_ORDER.filter(b => v[b] && v[b].ppsqm);
    return present.length >= 2 ? present : null;
  }
  function renderVintageSection(rec, kind) {
    if (!_vintageBuckets(rec)) return '';
    const paths = (rec.vintage_paths && Object.keys(rec.vintage_paths).length >= 2) ? `
        <div style="margin-top:10px">
          <div class="dp-chart-title">${t(kind === 'rent' ? 'vin_paths_rent' : 'vin_paths')}</div>
          <div class="dp-chart" style="height:210px">
            <button class="chart-expand-btn" type="button" data-dp-expand="vintage_paths" data-dp-source="${kind}" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
            <canvas id="ch-vintage-paths-${kind}"></canvas>
          </div>
        </div>` : '';
    return `
      <div class="dp-section">
        <h3>${t('dp_section_vintage')}</h3>
        <div class="dp-chart" style="height:170px"><canvas id="ch-vintage-${kind}"></canvas></div>
        ${paths}
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
    for (const { slab, label } of _calendarBuckets(ref, bs)) {
      labels.push(label);
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
  function renderVintageChart(rec, kind) {
    const ctx = document.getElementById('ch-vintage-' + kind);
    const present = _vintageBuckets(rec);
    if (!ctx || !present) return;
    const labels = { v0_1: t('vin_0_1'), v2_4: t('vin_2_4'), v5_10: t('vin_5_10'), v11p: t('vin_11p') };
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
            const relTxt = i === 0 ? '' : ' · ' + (rel >= 0 ? '+' : '') + rel + '% vs ≤1 г.';
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
        <div class="dp-timeline-grid">
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
        <div class="dp-timeline-grid">
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
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("rent_sc_ppsqm")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="ppsqm" data-dp-source="rent" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-rent-ppsqm"></canvas>
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

  function calendarMA(fullDates, fullValues, w) {
    const out = new Array(fullValues.length).fill(NaN);
    if (!fullDates || !fullDates.length) return out;
    const monthIdx = fullDates.map(d => { const [y, m] = d.slice(0, 7).split('-').map(Number); return y * 12 + (m - 1); });
    const minCount = Math.max(3, Math.round(w * 0.25));
    let start = 0;
    for (let i = 0; i < fullValues.length; i++) {
      const startMonth = monthIdx[i] - (w - 1);
      while (start < i && monthIdx[start] < startMonth) start++;
      let s = 0, c = 0;
      for (let j = start; j <= i; j++) if (Number.isFinite(fullValues[j])) { s += fullValues[j]; c++; }
      out[i] = c >= minCount ? s / c : NaN;
    }
    return out;
  }
  // Align by date, not tail: rent timelines run past the displayed window (forward-dated contracts)
  function alignedMA(fullDates, fullValues, displayDates, w) {
    if (!fullValues || !fullValues.length) return new Array(displayDates.length).fill(NaN);
    const full = calendarMA(fullDates, fullValues, w);
    const byDate = new Map(fullDates.map((d, i) => [d, full[i]]));
    return displayDates.map(d => byDate.has(d) ? byDate.get(d) : NaN);
  }
  function crossState(ma50, ma200, labels) {
    let prevSign = null, crossIdx = -1, crossDir = 0, lastSign = null;
    for (let i = 0; i < ma50.length; i++) {
      if (!Number.isFinite(ma50[i]) || !Number.isFinite(ma200[i])) continue;
      const sign = ma50[i] > ma200[i] ? 1 : (ma50[i] < ma200[i] ? -1 : 0);
      if (sign !== 0) {
        if (prevSign !== null && sign !== prevSign) { crossIdx = i; crossDir = sign; }
        prevSign = sign;
        lastSign = sign;
      }
    }
    if (lastSign == null) return null;
    return { lastSign, crossIdx, crossDir, crossDate: crossIdx >= 0 ? labels[crossIdx] : null };
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
    if (!Number.isFinite(last) || !prev) return null;
    return ((last - prev) / prev) * 100;
  }
  function renderTimelineCharts(a) {
    const raw = roomTimelineFor(a);
    const pt = _projectedPoint(raw, a.as_of);
    const withPt = arr => pt ? arr.filter(p => p.d < pt.d).concat(pt) : arr;
    const fullSeries = withPt(raw);
    const series = withPt(periodSlice(raw));
    const est = pt && pt.est ? { idx: series.length - 1, label: pt.d, note: _estNote(pt.est) } : null;
    const labels = series.map(p => p.d.length === 10 ? p.d.slice(5) : p.d);
    const baseColor = ROOM_COLORS[S.roomFilter] || '#1d4ed8';
    // Per-metric colors: avg=indigo (price), count=sky (activity), volume=teal (accumulated money).
    // Kept independent of the room filter so the three timeline charts always read as three
    // distinct series regardless of whether you're looking at Все / Studio / 1BR / 2BR / …
    const perMetric = { avg: '#4f46e5', count: '#0284c7', volume: '#0d9488' };
    S.chartData = {
      labels: labels.slice(),
      fullLabels: series.map(p => p.d),
      fullDates: fullSeries.map(p => p.d),
      count:  { values: series.map(p => p.n),                                    fullValues: fullSeries.map(p => p.n),                                fmtY: v => v,        fmtTip: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(), label: t('sp_subsection_count'),  color: perMetric.count },
      volume: { values: series.map(p => p.vol || 0),                             fullValues: fullSeries.map(p => p.vol || 0),                         fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                                label: t('sp_subsection_volume'), color: perMetric.volume },
      avg:    { values: series.map(avgPrice),                                     fullValues: fullSeries.map(avgPrice),                                fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                                label: t('sp_subsection_avg'),    color: perMetric.avg },
      color: baseColor,
      est,
    };
    // secondary: {values, fmtY, fmtTip, label, color} — deal count riding on a right-hand
    // axis behind the price line, so the two series' divergence (price is sticky, volume
    // isn't) is visible on one chart instead of requiring a manual cross-reference.
    const mkChart = (id, data, fmtY, tooltipFmt, color, label, secondary) => {
      const ctx = document.getElementById(id);
      if (!ctx) return;
      const bg = rgba(color, .14);
      const estIdx = est ? est.idx : -1;
      const datasets = [];
      if (secondary) {
        datasets.push({
          type:'bar', label: secondary.label, data: secondary.values,
          backgroundColor: c => rgba(secondary.color, c.dataIndex === estIdx ? .1 : .25), borderWidth: 0,
          yAxisID: 'y1', barPercentage: .6, categoryPercentage: .7, order: 2,
        });
      }
      datasets.push({ label, data, borderColor:color, backgroundColor:bg, tension:.3, fill:true, order: 1,
        pointRadius: c => c.dataIndex === estIdx ? 3 : 1.5,
        pointBackgroundColor: c => c.dataIndex === estIdx ? '#fff' : color,
        segment: { borderDash: c => c.p1DataIndex === estIdx ? [4, 3] : undefined } });
      const scales = {
        y:{ticks:{font:{size:10}, callback: fmtY}, beginAtZero:true},
        x:{ticks:{font:{size:10}, maxRotation:0, autoSkip:true, maxTicksLimit:6}},
      };
      if (secondary) {
        scales.y1 = { position:'right', ticks:{font:{size:10}, callback: secondary.fmtY}, beginAtZero:true, grid:{drawOnChartArea:false} };
      }
      const ch = new Chart(ctx, {
        type:'line',
        data:{ labels, datasets },
        options:{
          responsive:true, maintainAspectRatio:false,
          interaction:{intersect:false, mode:'index'},
          plugins:{
            legend:{ display: !!secondary, labels:{ font:{size:9}, boxWidth:10, padding:6 } },
            tooltip:{callbacks:{
              afterTitle: items => items.length && items[0].dataIndex === estIdx ? est.note : '',
              label: c => c.dataset.type === 'bar' ? ' ' + secondary.fmtTip(c.parsed.y) : ' ' + tooltipFmt(c.parsed.y),
            }},
          },
          scales,
        }
      });
      S.activeCharts.push(ch);
      S.timelineCharts.push(ch);
    };
    mkChart('ch-timeline-avg',    S.chartData.avg.values,    S.chartData.avg.fmtY,    S.chartData.avg.fmtTip,    S.chartData.avg.color,    S.chartData.avg.label,    S.chartData.count);
    mkChart('ch-timeline-count',  S.chartData.count.values,  S.chartData.count.fmtY,  S.chartData.count.fmtTip,  S.chartData.count.color,  S.chartData.count.label);
    mkChart('ch-timeline-volume', S.chartData.volume.values, S.chartData.volume.fmtY, S.chartData.volume.fmtTip, S.chartData.volume.color, S.chartData.volume.label);
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
            <button class="cm-engine active" type="button" data-dp-engine="lwc">Lightweight</button>
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
          <div id="dp-cm-lwc" class="chart-modal-lwc" style="display:none"></div>
        </div>
      </div>`;
    document.body.appendChild(el);
    return el;
  }
  // Chart.js modals (rooms, donuts, vintage) draw on the canvas; tear down the engine panes they share it with
  function _useCanvasPane(el) {
    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    if (S.echartsInstance) {
      if (S.echartsInstance._measureTeardown) S.echartsInstance._measureTeardown();
      S.echartsInstance.dispose();
      S.echartsInstance = null;
    }
    _disposeLwc();
    const overlay = document.getElementById('dp-cm-measure-overlay');
    if (overlay) overlay.remove();
    el.querySelector('#dp-cm-echarts').style.display = 'none';
    el.querySelector('#dp-cm-lwc').style.display = 'none';
    el.querySelector('#dp-cm-engines').style.display = 'none';
    const canvas = el.querySelector('#dp-cm-canvas');
    canvas.style.display = '';
    return canvas;
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
    _disposeLwc();
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

    const axis = [...new Set(cohorts.flatMap(c => vp[c].map(p => p.d)))].sort();
    const m = cohorts.length;
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

    const canvas = _useCanvasPane(el);
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

    const ma50 = alignedMA(cd.fullDates, m.fullValues, cd.fullLabels, 50);
    const ma200 = alignedMA(cd.fullDates, m.fullValues, cd.fullLabels, 200);
    const cross = crossState(ma50, ma200, labels);
    const w = 50;
    const ma = ma50;
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
    const lastSpread = Number.isFinite(lastVal) && Number.isFinite(lastMa) && lastMa ? ((lastVal - lastMa) / lastMa) * 100 : null;
    const validData = data.filter(Number.isFinite);
    const meanVal = validData.length ? validData.reduce((a,b)=>a+b,0)/validData.length : 0;
    const stdAll = validData.length ? Math.sqrt(validData.reduce((s,v)=>s+(v-meanVal)**2,0)/validData.length) : 0;
    const vol = meanVal ? (stdAll / meanVal) * 100 : null;

    const color = m.color || cd.color || '#1d4ed8';
    // Same deal-count-behind-price overlay as the small inline chart, carried into the
    // fullscreen modal so it doesn't disappear when the user expands the price chart.
    const secondary = (metric === 'avg' && source === 'sale' && cd.count) ? cd.count : null;

    const el = _modalDOM();
    el.dataset.metric = metric;
    el.dataset.source = source;
    el.querySelector('#dp-cm-title').textContent = m.label;
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = '';
    el.querySelector('#dp-cm-engines').style.display = '';
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
    if (cross) {
      if (cross.crossIdx >= 0) {
        const dead = cross.crossDir < 0;
        badges.push(badge(dead?'neg':'pos', t('bd_cross'), (dead?t('bd_cross_death'):t('bd_cross_golden')) + ' · ' + cross.crossDate, t('bd_cross_tip')));
      } else {
        badges.push(badge('muted', t('bd_cross'), cross.lastSign < 0 ? t('bd_cross_below') : t('bd_cross_above'), t('bd_cross_tip')));
      }
    }
    badges.push(badge('muted', t('bd_n'), validData.length, t('bd_n_tip')));
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');

    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    if (S.echartsInstance) {
      if (S.echartsInstance._measureTeardown) S.echartsInstance._measureTeardown();
      S.echartsInstance.dispose();
      S.echartsInstance = null;
    }
    _disposeLwc();
    const _oldOverlay = document.getElementById('dp-cm-measure-overlay');
    if (_oldOverlay) _oldOverlay.remove();
    el.classList.add('open');

    // Sync engine toggle UI
    el.querySelectorAll('.cm-engine').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.dpEngine === S.modalEngine);
    });
    const canvasEl = el.querySelector('#dp-cm-canvas');
    const echartsEl = el.querySelector('#dp-cm-echarts');
    const lwcEl = el.querySelector('#dp-cm-lwc');
    const engine = S.modalEngine;
    const useEc = engine === 'echarts';
    const target = useEc ? echartsEl : lwcEl;
    canvasEl.style.display = 'none';
    echartsEl.style.display = useEc ? '' : 'none';
    lwcEl.style.display = useEc ? 'none' : '';
    target.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-size:13px">${t('chart_loading') || 'Loading…'}</div>`;
    (useEc ? _ensureECharts() : _ensureLwc()).then(() => {
      // Bail out if the modal was closed or switched while the library was loading
      const still = document.getElementById('dp-chart-modal');
      if (!still || !still.classList.contains('open') || S.modalEngine !== engine || still.dataset.metric !== metric || (still.dataset.source || 'sale') !== source) return;
      target.innerHTML = '';
      if (useEc) _renderModalECharts({ el: echartsEl, labels, data, ma, ma50, ma200, median, color, m, secondary, est: cd.est });
      else _renderModalLwc({ el: lwcEl, dates: cd.fullLabels, data, ma50, ma200, median, color, m, secondary, cross, est: cd.est });
    }).catch(err => {
      target.innerHTML = `<div style="padding:20px;color:#dc2626;font-size:12px">${useEc ? 'ECharts' : 'Lightweight Charts'} failed to load.</div>`;
      console.error('Chart library load failed:', err);
    });
  }

  const _libPromises = {};
  function _loadLib(key, isLoaded, src, integrity) {
    if (isLoaded()) return Promise.resolve();
    if (_libPromises[key]) return _libPromises[key];
    return (_libPromises[key] = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.crossOrigin = 'anonymous';
      s.integrity = integrity;
      s.onload = () => resolve();
      s.onerror = e => { delete _libPromises[key]; s.remove(); reject(e); };
      document.head.appendChild(s);
    }));
  }
  const _ensureECharts = () => _loadLib('echarts', () => typeof echarts !== 'undefined',
    'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js',
    'sha384-Mx5lkUEQPM1pOJCwFtUICyX45KNojXbkWdYhkKUKsbv391mavbfoAmONbzkgYPzR');
  const _ensureLwc = () => _loadLib('lwc', () => typeof LightweightCharts !== 'undefined',
    'https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js',
    'sha384-KkYqTZlM13Zya6fVUF3IGCBOQ1ehFeJVVgxaVvD/0MebineF9EI8Jkd3NnWNChqN');

  function _disposeLwc() {
    if (S.lwcInstance) { S.lwcInstance.remove(); S.lwcInstance = null; }
  }

  function _renderModalLwc({ el, dates, data, ma50, ma200, median, color, m, secondary, cross, est }) {
    const L = LightweightCharts;
    const lang = document.documentElement.lang || 'en';
    const daily = dates.some(d => d.length === 10);
    const dateFmt = new Intl.DateTimeFormat(lang, daily
      ? { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }
      : { month: 'long', year: 'numeric', timeZone: 'UTC' });
    const toDate = tm => typeof tm === 'string' ? new Date(tm + 'T00:00:00Z')
      : typeof tm === 'object' ? new Date(Date.UTC(tm.year, tm.month - 1, tm.day))
      : new Date(tm * 1000);
    const fmtTime = tm => dateFmt.format(toDate(tm));
    const toTime = d => d.length === 7 ? d + '-01' : d;
    // Nulls are dropped so the line connects across empty months instead of breaking
    const pts = arr => dates.flatMap((d, i) => Number.isFinite(arr[i]) ? [{ time: toTime(d), value: arr[i] }] : []);
    const hasFinite = arr => arr.some(v => Number.isFinite(v));
    const estTime = est ? toTime(est.label) : null;
    const estStyle = (arr, style) => arr.map(p => p.time === estTime ? { ...p, ...style } : p);
    const fmtAxis = v => { const r = m.fmtY(Math.round(v)); return typeof r === 'number' ? fmtInt(r) : r; };
    const pf = { type: 'custom', minMove: 1, formatter: fmtAxis };
    const crossLine = { color: '#94a3b8', width: 1, style: L.LineStyle.Dashed, labelBackgroundColor: '#0f172a' };

    const chart = L.createChart(el, {
      autoSize: true,
      layout: {
        background: { type: 'solid', color: '#ffffff' },
        textColor: '#64748b', fontSize: 11,
        fontFamily: getComputedStyle(document.body).fontFamily,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: '#f1f5f9' } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.14, bottom: secondary ? 0.3 : 0.05 } },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: L.CrosshairMode.Magnet, vertLine: crossLine, horzLine: crossLine },
      localization: { locale: lang, timeFormatter: fmtTime },
      // Drag is reserved for the measure tool; wheel zooms, trackpad swipe pans
      handleScroll: { pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false, mouseWheel: true },
    });
    S.lwcInstance = chart;

    const legendRows = [];
    if (secondary) {
      const vol = chart.addSeries(L.HistogramSeries, {
        priceScaleId: 'vol', color: 'rgba(148,163,184,0.4)',
        priceLineVisible: false, lastValueVisible: false,
      });
      vol.setData(estStyle(pts(secondary.values), { color: 'rgba(148,163,184,0.15)' }));
      chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.58, bottom: 0 }, visible: false });
      legendRows.push({ s: vol, label: secondary.label, swatch: 'rgba(148,163,184,0.6)', fmt: secondary.fmtTip });
    }
    const maOpts = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, priceFormat: pf };
    if (hasFinite(ma200)) {
      const s200 = chart.addSeries(L.LineSeries, { ...maOpts, color: '#94a3b8', lineStyle: L.LineStyle.Dashed });
      s200.setData(pts(ma200));
      legendRows.push({ s: s200, label: t('ch_ma200'), swatch: '#94a3b8', fmt: m.fmtTip, dashed: true });
    }
    if (hasFinite(ma50)) {
      const s50 = chart.addSeries(L.LineSeries, { ...maOpts, color: '#475569' });
      s50.setData(pts(ma50));
      legendRows.push({ s: s50, label: t('ch_ma50'), swatch: '#475569', fmt: m.fmtTip });
    }
    const main = chart.addSeries(L.AreaSeries, {
      lineColor: color, lineWidth: 2,
      topColor: rgba(color, 0.22), bottomColor: rgba(color, 0),
      priceFormat: pf, priceLineVisible: false,
      crosshairMarkerRadius: 4, crosshairMarkerBorderColor: '#ffffff', crosshairMarkerBorderWidth: 2,
    });
    const mainPts = pts(data);
    main.setData(estStyle(mainPts, { lineColor: rgba(color, 0.4), topColor: rgba(color, 0.08) }));
    legendRows.unshift({ s: main, label: m.label, swatch: color, fmt: m.fmtTip, main: true });

    if (median != null) {
      main.createPriceLine({
        price: median, color: '#cbd5e1', lineWidth: 1, lineStyle: L.LineStyle.Dotted,
        axisLabelVisible: false, title: t('ch_median'),
      });
    }
    if (cross && cross.crossIdx >= 0 && Number.isFinite(data[cross.crossIdx])) {
      const up = cross.crossDir > 0;
      L.createSeriesMarkers(main, [{
        time: toTime(dates[cross.crossIdx]),
        position: up ? 'belowBar' : 'aboveBar',
        shape: up ? 'arrowUp' : 'arrowDown',
        color: up ? '#16a34a' : '#dc2626',
        text: up ? t('bd_cross_golden') : t('bd_cross_death'),
      }]);
    }
    chart.timeScale().fitContent();

    // Floating legend: tracks the crosshair, falls back to the latest values
    const legend = document.createElement('div');
    legend.className = 'cm-lwc-legend';
    el.appendChild(legend);
    const lastOf = s => { const d = s.data(); return d.length ? d[d.length - 1] : null; };
    const paintLegend = param => {
      const hover = param && param.time !== undefined && param.seriesData && param.seriesData.size;
      const mainPt = hover ? param.seriesData.get(main) : lastOf(main);
      const time = hover ? param.time : (mainPt && mainPt.time);
      const rows = legendRows.map(r => {
        const pt = hover ? param.seriesData.get(r.s) : lastOf(r.s);
        if (!pt || !Number.isFinite(pt.value)) return '';
        const sw = r.dashed
          ? `border-top:2px dashed ${r.swatch};height:0`
          : `background:${r.swatch};height:${r.main ? 3 : 2}px`;
        return `<div class="cm-lwc-row${r.main ? ' main' : ''}"><i style="${sw}"></i><span>${_h(r.label)}</span><b>${r.fmt(Math.round(pt.value))}</b></div>`;
      }).join('');
      const isEst = est && time != null && fmtTime(time) === fmtTime(estTime);
      legend.innerHTML = (time !== undefined && time !== null ? `<div class="cm-lwc-date">${fmtTime(time)}${isEst ? ` · ${_h(est.note)}` : ''}</div>` : '') + rows;
    };
    chart.subscribeCrosshairMove(paintLegend);
    paintLegend(null);

    _installLwcMeasure({ el, chart, main, mainPts, m, color, fmtTime, legend });
  }

  function _installLwcMeasure({ el, chart, main, mainPts, m, color, fmtTime, legend }) {
    if (mainPts.length < 2) return;
    const ts = chart.timeScale();
    const layer = document.createElement('div');
    layer.className = 'cm-lwc-measure';
    el.appendChild(layer);
    const monthNo = tm => +tm.slice(0, 4) * 12 + +tm.slice(5, 7);
    let a = null, c = null, dragging = false;

    const plotWidth = () => el.clientWidth - chart.priceScale('right').width();
    const nearestIdx = x => {
      let best = -1, bestD = Infinity;
      mainPts.forEach((p, i) => {
        const px = ts.timeToCoordinate(p.time);
        if (px == null) return;
        const d = Math.abs(px - x);
        if (d < bestD) { bestD = d; best = i; }
      });
      return best < 0 ? null : best;
    };
    const localX = e => e.clientX - el.getBoundingClientRect().left;

    const paint = () => {
      if (a == null) { layer.innerHTML = ''; return; }
      const pa = mainPts[a], pc = mainPts[c];
      const ax = ts.timeToCoordinate(pa.time), cx = ts.timeToCoordinate(pc.time);
      if (ax == null || cx == null) { layer.innerHTML = ''; return; }
      const ay = main.priceToCoordinate(pa.value), cy = main.priceToCoordinate(pc.value);
      const isRange = a !== c;
      const info = _measureInfo({
        aLabel: fmtTime(pa.time), aVal: pa.value, cLabel: fmtTime(pc.time), cVal: pc.value,
        months: monthNo(pc.time) - monthNo(pa.time), isRange, m,
      });
      const h = el.clientHeight - ts.height();
      const vline = (x, col) => `<div class="cm-m-vline" style="left:${x}px;height:${h}px;border-color:${col}"></div>`;
      const dot = (x, y, col) => y == null ? '' : `<div class="cm-m-dot" style="left:${x}px;top:${y}px;background:${col}"></div>`;
      const left = Math.min(ax, cx), right = Math.max(ax, cx);

      // Panel goes right of the range, else left of it, else docks top-right; drops below the legend if they'd collide
      const panelW = 200, gap = 12, W = plotWidth();
      let px = right + gap + panelW + 8 <= W ? right + gap
        : left - gap - panelW - 8 >= 0 ? left - gap - panelW
        : W - panelW - gap;
      const lr = legend.getBoundingClientRect(), er = el.getBoundingClientRect();
      const py = px < lr.right - er.left + 8 ? lr.bottom - er.top + 8 : 8;

      layer.innerHTML =
        (isRange ? `<div class="cm-m-span" style="left:${left}px;width:${right - left}px;height:${h}px"></div>` : '') +
        vline(ax, color) + dot(ax, ay, color) +
        (isRange ? vline(cx, info.deltaColor) + dot(cx, cy, info.deltaColor) : '') +
        `<div class="cm-m-panel" style="left:${px}px;top:${py}px;width:${panelW}px">${info.html}</div>`;
    };

    el.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      const x = localX(e);
      if (x > plotWidth() || e.clientY - el.getBoundingClientRect().top > el.clientHeight - ts.height()) return;
      const i = nearestIdx(x);
      if (i == null) return;
      a = c = i;
      dragging = true;
      el.setPointerCapture(e.pointerId);
      paint();
    });
    el.addEventListener('pointermove', e => {
      if (!dragging) return;
      const i = nearestIdx(localX(e));
      if (i != null && i !== c) { c = i; paint(); }
    });
    const stop = () => { dragging = false; };
    el.addEventListener('pointerup', stop);
    el.addEventListener('pointercancel', stop);
    ts.subscribeVisibleLogicalRangeChange(paint);
    ts.subscribeSizeChange(paint);
  }

  function _renderModalECharts({ el, labels, data, ma, ma50, ma200, median, color, m, secondary, est }) {
    const clean = arr => arr.map(v => Number.isFinite(v) ? v : null);
    const hasFinite = arr => arr.some(v => Number.isFinite(v));
    const inst = echarts.init(el, null, { renderer: 'canvas' });
    S.echartsInstance = inst;

    const above = data.map((v, i) => (Number.isFinite(ma[i]) && v >= ma[i]) ? v : null);
    const below = data.map((v, i) => (Number.isFinite(ma[i]) && v <  ma[i]) ? v : null);

    inst.setOption({
      grid: { left: 56, right: secondary ? 56 : 24, top: 18, bottom: 44 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: '#94a3b8' } },
        backgroundColor: 'rgba(15,23,42,0.94)',
        borderColor: 'transparent',
        textStyle: { color: '#f1f5f9', fontSize: 12 },
        padding: [8, 12],
        formatter: params => {
          const pName = params[0].name;
          const hidden = new Set(['above-ma', 'below-ma']);
          const rows = params
            .filter(p => p.value != null && !hidden.has(p.seriesName))
            .map(p => `<div style="display:flex;justify-content:space-between;gap:12px">
              <span>${p.marker} ${p.seriesName}</span>
              <span style="font-variant-numeric:tabular-nums;font-weight:600">${secondary && p.seriesName === secondary.label ? secondary.fmtTip(Math.round(p.value)) : m.fmtTip(Math.round(p.value))}</span>
            </div>`)
            .join('');
          const note = est && pName === est.label ? ` · ${_h(est.note)}` : '';
          return `<div style="opacity:.75;font-size:11px;margin-bottom:4px">${pName}${note}</div>${rows}`;
        },
      },
      legend: {
        bottom: 0, itemGap: 16, textStyle: { fontSize: 11, color: '#475569' },
        icon: 'roundRect', itemWidth: 12, itemHeight: 8,
        data: [
          m.label,
          ...(hasFinite(ma200) ? [t('ch_ma200')] : []),
          ...(hasFinite(ma50) ? [t('ch_ma50')] : []),
          ...(median != null ? [t('ch_median')] : []),
          ...(secondary ? [secondary.label] : []),
        ],
      },
      xAxis: {
        type: 'category', data: labels,
        axisLabel: { fontSize: 10, color: '#64748b' },
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisTick: { show: false },
      },
      yAxis: [{
        type: 'value',
        axisLabel: { fontSize: 10, color: '#64748b', formatter: m.fmtY },
        splitLine: { lineStyle: { color: '#f1f5f9' } },
        axisLine: { show: false }, axisTick: { show: false },
      },
      ...(secondary ? [{
        type: 'value',
        axisLabel: { fontSize: 10, color: '#64748b', formatter: secondary.fmtY },
        splitLine: { show: false },
        axisLine: { show: false }, axisTick: { show: false },
      }] : []),
      ],
      series: [
        ...(secondary ? [{
          name: secondary.label, type: 'bar', yAxisIndex: 1, data: secondary.values,
          itemStyle: { color: secondary.color, opacity: .25 },
          barMaxWidth: 14,
        }] : []),
        ...(hasFinite(ma200) ? [{
          name: t('ch_ma200'), type: 'line', data: clean(ma200),
          smooth: true, symbol: 'none',
          itemStyle: { color: '#7c3aed' },
          lineStyle: { color: '#7c3aed', width: 1.6 },
        }] : []),
        ...(hasFinite(ma50) ? [{
          name: t('ch_ma50'), type: 'line', data: clean(ma50),
          smooth: true, symbol: 'none',
          itemStyle: { color: '#f59e0b' },
          lineStyle: { color: '#f59e0b', width: 1.6 },
        }] : []),
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
          connectNulls: true,
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
      const info = _measureInfo({ aLabel: labels[anchorIdx], aVal, cLabel: labels[cIdx], cVal, months: cIdx - anchorIdx, isRange, m });
      const deltaColor = info.deltaColor;

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
      _paintMeasureHtml(inst, panelX, panelY, panelW, info.html);
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

  // Shared "from → to" readout for the drag-to-measure tool (both chart engines)
  function _measureInfo({ aLabel, aVal, cLabel, cVal, months, isRange, m }) {
    const delta = (Number.isFinite(aVal) && Number.isFinite(cVal)) ? cVal - aVal : null;
    const pctDelta = (delta != null && aVal) ? (delta / aVal) * 100 : null;
    const deltaColor = delta == null ? '#334155' : (delta >= 0 ? '#16a34a' : '#dc2626');
    const deltaBg = delta == null ? '#f1f5f9' : (delta >= 0 ? '#dcfce7' : '#fee2e2');

    // Info panel content
    const fmt = v => Number.isFinite(v) ? m.fmtTip(Math.round(v)) : '—';
    const sign = v => v == null ? '' : (v > 0 ? '+' : '');
    const lines = [];
    lines.push(`<div style="opacity:.7;font-size:10px">${t('ch_measure_from') || 'От'}</div>`);
    lines.push(`<div style="font-weight:600">${aLabel}</div>`);
    lines.push(`<div style="font-variant-numeric:tabular-nums">${fmt(aVal)}</div>`);
    if (isRange) {
      lines.push(`<div style="opacity:.7;font-size:10px;margin-top:6px">${t('ch_measure_to') || 'До'}</div>`);
      lines.push(`<div style="font-weight:600">${cLabel}</div>`);
      lines.push(`<div style="font-variant-numeric:tabular-nums">${fmt(cVal)}</div>`);
      if (delta != null) {
        lines.push(`<div style="margin-top:8px;padding:4px 6px;border-radius:4px;background:${deltaBg};color:${deltaColor};font-weight:600;font-variant-numeric:tabular-nums">
          ${sign(delta)}${fmt(delta)} (${sign(pctDelta)}${pctDelta.toFixed(1)}%)
        </div>`);
      }
      const monthsLabel = Math.abs(months) === 1
        ? (t('ch_measure_month') || 'мес.')
        : (t('ch_measure_months') || 'мес.');
      lines.push(`<div style="opacity:.65;font-size:10px;margin-top:4px">Δ ${Math.abs(months)} ${monthsLabel}</div>`);
    } else {
      lines.push(`<div style="opacity:.55;font-size:10px;margin-top:8px;line-height:1.4">${t('ch_measure_hint') || 'Тяните курсор в сторону для сравнения'}</div>`);
    }
    return { html: lines.join(''), deltaColor };
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
    const named = list.filter(p => p.proj);
    const unnamed = list.filter(p => !p.proj);
    if (!named.length) return null;
    const N = 8;
    const top = named.slice(0, N);
    const tail = named.slice(N).concat(unnamed);
    const tailN = tail.reduce((s,p) => s + (p.n||0), 0);
    const items = top.map(p => ({ name: p.proj, n: p.n, total: p.total }));
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
    delete el.dataset.metric;
    delete el.dataset.source;
    const ctx = _useCanvasPane(el);
    el.classList.add('open');
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
    const medVals = series.map(p => medPrice(p, monthly));
    const cntVals = series.map(p => p.n);
    const fullMedVals = tlSource.map(p => medPrice(p, monthly));
    const fullCntVals = tlSource.map(p => p.n);

    S.rentChartData = {
      labels: labels.slice(),
      fullLabels,
      fullDates: tlSource.map(p => p.d),
      count: { values: cntVals, fullValues: fullCntVals, fmtY: v => v,        fmtTip: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(), label: t('sp_subsection_count') },
      med:   { values: medVals, fullValues: fullMedVals, fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                            label: t('rent_th_med') },
      ppsqm: { values: series.map(p => p.ppsqm || null), fullValues: tlSource.map(p => p.ppsqm || null), fmtY: v => fmtInt(v), fmtTip: v => fmtInt(v) + ' AED', label: t('rent_sc_ppsqm') },
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
    mkChart('ch-rent-ppsqm', S.rentChartData.ppsqm.values, S.rentChartData.ppsqm.fmtY, S.rentChartData.ppsqm.fmtTip);

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
    _stripKnownBadFromRecord(S.sale);
    _stripKnownBadFromRecord(S.rent);
    _addApartmentsBucket(S.sale);
    _addApartmentsBucket(S.rent);
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
