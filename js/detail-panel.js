// District detail panel core: state, helpers, chart theme, stats/chips, modal shell. Loads first; parts share window._dp.
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
  // 'homes' = the headline record itself (a.timeline / a.n); 'all' = every deal incl. offices, labor camps, land
  const SEGMENTS      = ['office','shop','warehouse','labor','land','commercial','other'];
  const ROOM_ORDER    = ['homes','apartments','studio','1br','2br','3br','4br+','villa', ...SEGMENTS, 'all'];
  const ROOM_BREAKDOWN = ['studio','1br','2br','3br','4br+','villa', ...SEGMENTS];
  const ROOM_COLORS   = { homes:'#0f766e', all:'#1d4ed8', apartments:'#16a34a', studio:'#9ca3af', '1br':'#60a5fa', '2br':'#3b82f6', '3br':'#1d4ed8', '4br+':'#1e3a8a', villa:'#d97706',
                          office:'#7c3aed', shop:'#db2777', warehouse:'#78716c', labor:'#b45309', land:'#65a30d', commercial:'#9333ea', other:'#a78bfa' };
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
  // Monthly median: one plot/tower sale can't swing it the way vol/n does; empty month = gap
  function avgPrice(p) {
    return p.n ? (p.med || Math.round(p.vol / p.n)) : null;
  }
  function _priceCap(vals) {
    const s = vals.filter(Number.isFinite).sort((a, b) => a - b);
    if (s.length < 12) return undefined;
    const q = f => s[Math.floor(f * (s.length - 1))];
    const cap = q(.75) + 3 * (q(.75) - q(.25));
    return s[s.length - 1] > cap ? cap : undefined;
  }
  // Pre-2009 land-plot era: drop leading months up to the last outlier if it sits in the first half
  // (on the full history, so MA50/MA200 and the modal badges don't inherit it either)
  function _trimLeadOutliers(series) {
    const vals = series.map(avgPrice), cap = _priceCap(vals);
    if (!cap) return series;
    let last = -1;
    vals.forEach((v, i) => { if (v > cap) last = i; });
    return last >= 0 && last < series.length / 2 ? series.slice(last + 1) : series;
  }
  // Axis cap for thin-month spikes left mid-series (they clip off the top); months with typical deal counts always fit
  function _robustMax(vals, ns) {
    const cap = _priceCap(vals);
    if (!cap) return undefined;
    const sn = (ns || []).filter(Number.isFinite).sort((a, b) => a - b);
    const medN = sn.length ? sn[Math.floor(sn.length / 2)] : Infinity;
    const top = Math.max(cap, ...vals.filter((v, i) => Number.isFinite(v) && ns && ns[i] >= medN));
    if (top >= Math.max(...vals.filter(Number.isFinite))) return undefined;
    const e = 10 ** Math.floor(Math.log10(top));
    return Math.ceil(top / e * 2) / 2 * e;
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
    if (v >= 1e12) return (v/1e12).toFixed(2) + ' ' + t('abbr_t');
    if (v >= 1e9) return (v/1e9).toFixed(2) + ' ' + t('abbr_b');
    if (v >= 1e6) return (v/1e6).toFixed(2) + ' ' + t('abbr_m');
    if (v >= 1e3) { const k = t('abbr_k'); return (v/1e3).toFixed(0) + (k.length > 1 ? ' ' : '') + k; }
    return v.toLocaleString();
  }
  function fmtAxisAed(v) {
    if (v >= 1e9) return (v/1e9).toFixed(1) + 'B';
    if (v >= 1e6) return (v/1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v/1e3).toFixed(0) + 'K';
    return v;
  }
  // Shared look for the panel's Chart.js charts: body font, muted ink, faint grid, dark rounded tooltips
  let _themed = false;
  function _chartTheme() {
    if (_themed || typeof Chart === 'undefined') return;
    _themed = true;
    const d = Chart.defaults;
    d.font.family = getComputedStyle(document.body).fontFamily;
    d.color = '#64748b';
    d.borderColor = '#eef2f6';
    Object.assign(d.plugins.tooltip, {
      backgroundColor: 'rgba(15,23,42,0.92)', padding: 8, cornerRadius: 6, boxPadding: 4,
      usePointStyle: true, titleFont: { size: 11, weight: '600' }, bodyFont: { size: 12 },
    });
    Object.assign(d.plugins.legend.labels, { usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7 });
  }
  // Minimal axes: no vertical grid, no axis lines, a handful of ticks
  function _xAxis(extra) {
    return Object.assign({ grid: { display: false }, border: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } }, extra || {});
  }
  function _yAxis(fmt, extra) {
    return Object.assign({ border: { display: false }, ticks: { font: { size: 10 }, maxTicksLimit: 5, callback: fmt } }, extra || {});
  }
  function _areaFill(color) {
    return ctx => {
      const a = ctx.chart.chartArea;
      if (!a) return rgba(color, 0.12);
      const g = ctx.chart.ctx.createLinearGradient(0, a.top, 0, a.bottom);
      g.addColorStop(0, rgba(color, 0.24));
      g.addColorStop(1, rgba(color, 0));
      return g;
    };
  }
  function _pill(c, text, x, y, bg) {
    c.font = '600 10px ' + _chartFont();
    const w = c.measureText(text).width + 10, h = 16;
    c.fillStyle = bg;
    c.beginPath();
    c.roundRect(x, y, w, h, 8);
    c.fill();
    c.fillStyle = '#fff';
    c.textAlign = 'left';
    c.fillText(text, x + 5, y + 11.5);
    return w;
  }
  // Latest value as a pill above the line's last point (dataset._tag = { fmt, color })
  const _lastValueTag = {
    id: 'lastValueTag',
    afterDatasetsDraw(chart) {
      chart.data.datasets.forEach((ds, i) => {
        if (!ds._tag || !chart.isDatasetVisible(i)) return;
        const pts = chart.getDatasetMeta(i).data;
        let j = ds.data.length - 1;
        while (j >= 0 && !Number.isFinite(ds.data[j])) j--;
        if (j < 0 || !pts[j]) return;
        const c = chart.ctx, text = ds._tag.fmt(ds.data[j]);
        c.save();
        c.font = '600 10px ' + _chartFont();
        const w = c.measureText(text).width + 10;
        const x = Math.min(pts[j].x - w / 2, chart.chartArea.right - w);
        // Above the point, unless that would hit the top edge / expand button
        const y = pts[j].y - 24 < chart.chartArea.top + 26 ? pts[j].y + 8 : pts[j].y - 24;
        _pill(c, text, x, y, ds._tag.color);
        c.restore();
      });
    },
  };
  // Stack total above each bar (includes a forecast segment, prefixed with ≈)
  const _stackTotals = {
    id: 'stackTotals',
    afterDatasetsDraw(chart) {
      const n = chart.data.labels.length, y = chart.scales.y, c = chart.ctx;
      const first = chart.getDatasetMeta(0).data[0];
      if (!first || first.width < 22) return;
      c.save();
      c.font = '600 10px ' + _chartFont();
      c.textAlign = 'center';
      c.fillStyle = '#475569';
      for (let k = 0; k < n; k++) {
        let sum = 0, fc = false, x = null;
        chart.data.datasets.forEach((ds, i) => {
          if (ds.type === 'line' || !chart.isDatasetVisible(i) || !ds.data[k]) return;
          sum += ds.data[k];
          if (ds._forecast) fc = true;
          x = chart.getDatasetMeta(i).data[k].x;
        });
        if (!sum || x == null) continue;
        c.fillText((fc ? '≈' : '') + fmtAxisAed(Math.round(sum)), x, y.getPixelForValue(sum) - 5);
      }
      c.restore();
    },
  };
  // Leading share in the donut hole (dataset._center = true)
  const _donutCenter = {
    id: 'donutCenter',
    afterDatasetsDraw(chart) {
      const ds = chart.data.datasets[0];
      if (!ds || !ds._center) return;
      const arc = chart.getDatasetMeta(0).data[0];
      if (!arc) return;
      let total = 0, best = -1;
      const others = new Set([t('donut_others'), t('rent_subtype_other')]);
      ds.data.forEach((v, i) => {
        if (!chart.getDataVisibility(i)) return;
        total += v;
        // "Others" bucket isn't a leader worth headlining
        if (!others.has(chart.data.labels[i]) && (best < 0 || v > ds.data[best])) best = i;
      });
      if (!total || best < 0) return;
      const c = chart.ctx, r = arc.innerRadius;
      if (r < 22) return;
      let label = String(chart.data.labels[best]);
      c.save();
      c.textAlign = 'center';
      c.fillStyle = '#0f172a';
      c.font = `700 ${Math.min(20, r * 0.5)}px ` + _chartFont();
      c.fillText(Math.round(ds.data[best] / total * 100) + '%', arc.x, arc.y + 2);
      c.font = '500 10px ' + _chartFont();
      c.fillStyle = '#64748b';
      while (label.length > 4 && c.measureText(label).width > r * 1.6) label = label.slice(0, -2);
      if (label !== String(chart.data.labels[best])) label += '…';
      c.fillText(label, arc.x, arc.y + 16);
      c.restore();
    },
  };
  // Indigo scale 800→200, spread across all slices so neighbours differ clearly; biggest slice darkest
  const _INDIGO = ['#3730a3', '#4f46e5', '#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'];
  function _tints(n) {
    if (n <= 1) return [_INDIGO[1]];
    const rgb = h => h.slice(1).match(/../g).map(x => parseInt(x, 16));
    return Array.from({ length: n }, (_, i) => {
      const t = i / (n - 1) * (_INDIGO.length - 1), k = Math.min(Math.floor(t), _INDIGO.length - 2), f = t - k;
      const [a, b] = [rgb(_INDIGO[k]), rgb(_INDIGO[k + 1])];
      return '#' + a.map((v, j) => Math.round(v + (b[j] - v) * f).toString(16).padStart(2, '0')).join('');
    });
  }

  function projName(p) { return _h(p || t('not_specified')); }
  // per-language value map without the RU fallback t() applies
  function tVal(mapKey, k) {
    const L = (typeof I18N !== 'undefined' && typeof currentLang !== 'undefined') ? I18N[currentLang] : null;
    return (L && L[mapKey] && L[mapKey][k]) || k;
  }
  function roomLabel(k){
    if (k==='all')        return t('room_chip_all');
    if (k==='apartments') return t('room_all'); // reuses the "All apartments" string — accurate here, unlike for 'all'
    if (k==='villa')  return t('ru_villa');
    if (k==='other')  return t('ru_other');
    if (k==='homes')  return t('room_chip_homes');
    if (SEGMENTS.includes(k)) return t('seg_' + k);
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
          if (!e) { e = { d: p.d, n: 0, vol: 0, medSum: 0, ppsqmSum: 0, op: 0, mort: 0 }; byDate.set(p.d, e); }
          e.n   += p.n || 0;
          e.vol += p.vol || 0;
          e.op  += p.op || 0;
          e.mort += p.mort || 0;
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
          ...(e.op ? { op: e.op } : {}), ...(e.mort ? { mort: e.mort } : {}),
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
    S.donutCharts = [];
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
  function destroyChartsIn(el, also) {
    S.activeCharts = S.activeCharts.filter(c => {
      if (!(also && also.includes(c)) && !(el && c.canvas && el.contains(c.canvas))) return true;
      if (c === S.roomBreakdownChart) S.roomBreakdownChart = null;
      c.destroy();
      return false;
    });
  }
  // Every chart in the rent pane: renderRentCharts redraws rooms, vintage and donuts too, not just timelines
  function destroyRentCharts() {
    destroyChartsIn(S.container && S.container.querySelector('#dp-pane-rent'), S.rentTimelineCharts);
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
  // The record through the active room chip: donut + vintage fields come from its mix entry (nothing
  // borrowed from other rooms); the record's default chip keeps the top-level fields
  const MIX_FIELDS = ['offplan', 'payment', 'new', 'renewed', 'by_tenant', 'by_subtype', 'by_usage'];
  const VIN_FIELDS = ['vintage', 'vintage_paths', 'vintage_paths_m'];
  function roomView(a) {
    const k = S.roomFilter;
    if (!a || !a.mix) return a;
    const m = a.mix[k] || {}, v = Object.assign({}, a);
    // Top-level rent subtype / usage count every contract, even on the homes chip
    if (k === (a.scope === 'home' ? 'homes' : 'all')) {
      for (const f of ['by_subtype', 'by_usage']) if (m[f]) v[f] = m[f];
      return v;
    }
    for (const f of MIX_FIELDS) v[f] = m[f];
    // Vintage rows are apartments only, so all / homes / apartments chips see the same set
    if (!['all', 'homes', 'apartments'].includes(k)) for (const f of VIN_FIELDS) v[f] = m[f];
    return v;
  }
  function roomTimelineFor(a) {
    const tbr = a.timeline_by_rooms || {};
    if (S.roomFilter === 'homes' || (S.roomFilter === 'all' && !tbr.all)) return a.timeline || [];
    return tbr[S.roomFilter] || [];
  }
  // Chips a record offers: 'homes' only when its headline is homes, 'all' only when it adds deals
  function _roomAvailable(a, k) {
    const tbr = a.timeline_by_rooms || {}, bu = a.by_rooms_unit || {};
    if (k === 'homes') return a.scope === 'home';
    if (k === 'all') return a.scope !== 'home' || (bu.all && bu.all.n > a.n);
    return !!(tbr[k] && tbr[k].length);
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

  // Precomputed [n, vol, med, ppsqm] for the period × chip, same windows as page titles and masks
  function _pstat(a) {
    const ps = a.pstats && a.pstats[S.period];
    if (!ps) return null;
    const tbr = a.timeline_by_rooms || {};
    const k = (S.roomFilter === 'homes' || (S.roomFilter === 'all' && !tbr.all)) ? 'homes' : S.roomFilter;
    return ps[k] || [0, 0, 0, 0];
  }
  function computeStatsSale(a) {
    const ps = _pstat(a);
    if (ps) return { n: ps[0], total: ps[1], med: ps[2], med_ppsqm: ps[3] };
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
    const ps = _pstat(r);
    if (ps) return { n: ps[0], med_annual: ps[2], med_ppsqm: ps[3] };
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
    const bu  = a.by_rooms_unit || {};
    return ROOM_ORDER.map(k => {
      if (!_roomAvailable(a, k)) return '';
      const n = k === 'homes' ? a.n : k === 'all' ? (bu.all ? bu.all.n : a.n) : (bu[k] ? bu[k].n : 0);
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
      return `<button class="rb-chip" type="button" data-dp-toggle-room="${_h(k)}" style="--c:${color}" aria-pressed="${hidden ? 'false' : 'true'}">${roomLabel(k)}<span class="rb-chip-n">${fmtInt(total)}</span></button>`;
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

  const _chartFont = () => getComputedStyle(document.body).fontFamily;

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

  function _disposeLwc() {
    if (S.lwcInstance) { S.lwcInstance.remove(); S.lwcInstance = null; }
  }

  window._dp = {
    PERIODS, ROOM_BREAKDOWN, ROOM_COLORS, ROOM_ORDER, S, _addApartmentsBucket, _areaFill, _chartFont,
    _chartTheme, _closeChartModal, _disposeLwc, _donutCenter, _estNote, _h, _lastValueTag, _maWindow,
    _modalDOM, _projectedPoint, _robustMax, _roomsRec, _stackTotals, _stripKnownBadFromRecord,
    _tints, _trimLeadOutliers, _useCanvasPane, _workdays, _xAxis, _yAxis, alignedMA, avgPrice,
    crossState, destroyCharts, destroyChartsIn, destroyRentCharts, destroyTimelineCharts, fmtAedDP, fmtAxisAed,
    fmtInt, linearTrend, medPrice, periodSlice, projName, renderPeriodChips, renderPeriodChipsRent,
    renderRoomBreakdown, renderRoomChips, renderStatsRent, renderStatsSale, rgba, roomLabel,
    roomTimelineFor, roomView, t, tVal, yoyPercent
  };
})();
