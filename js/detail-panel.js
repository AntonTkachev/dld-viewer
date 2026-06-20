/**
 * Detail panel — standalone renderer for one district's sales + rent data.
 *
 * Entry point:
 *   DetailPanel.mount({
 *     container,        // DOM node to render into
 *     sale,             // AGGREGATES[key]-shaped record (or null)
 *     rent,             // RENT_AGGREGATES[key]-shaped record (or null)
 *     title,            // optional display title for the title element (#dp-title)
 *     isDubai: false,   // when rendering Dubai-wide aggregate
 *   });
 *
 * Used by:
 *   - index.html viewer (slide-out panel)
 *   - sales/<district>/index.html (full-page standalone)
 *
 * Depends on:
 *   - Chart.js (window.Chart) — for timeline / room / off-plan charts
 *   - js/i18n.js (window.t)   — for localized labels
 *   - css/viewer.css          — for .dp-* / .room-chip / .period-chip styling
 */
(function () {
  // Module state — replaces the global lookups (AGGREGATES[key]) used by the
  // slide-out panel. mount() seeds these; setPeriod / setRoomFilter mutate.
  const S = {
    container: null,
    sale: null,
    rent: null,
    isDubai: false,
    period: 'all',
    roomFilter: 'all',
    activeCharts: [],
    timelineCharts: [],
    rentTimelineCharts: [],
    modalChart: null,
  };

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

  // ─── i18n shim ─────────────────────────────────────────────────
  // Use the real t() if i18n.js is loaded, otherwise fall back to the key.
  function t(k) { return (typeof window.t === 'function') ? window.t(k) : k; }

  // ─── XSS guard ────────────────────────────────────────────────
  // All string-typed values from AGGREGATES / RENT_AGGREGATES (project names,
  // area names, room labels, tx types) are interpolated raw into innerHTML.
  // Sources are DLD/RERA — lower-risk than OSM but still untrusted. Escape.
  function _h(s) {
    return String(s == null ? '' : s).replace(/[&<>"'`]/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','`':'&#96;',
    })[c]);
  }

  // ─── Formatters ────────────────────────────────────────────────
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

  // ─── Chart cleanup ─────────────────────────────────────────────
  function destroyCharts() {
    for (const c of S.activeCharts) c.destroy();
    S.activeCharts = [];
    S.timelineCharts = [];
    S.rentTimelineCharts = [];
    S.roomBreakdownChart = null;
    // Modal chart lives outside activeCharts; clean up too so a stale handle
    // doesn't survive a re-mount.
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

  // ─── Period / room helpers ─────────────────────────────────────
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

  // ─── Period chips ──────────────────────────────────────────────
  // When periodHref is provided, chips are real <a> tags (crawlable). Click
  // is intercepted by JS for in-page switch + pushState, so navigation is
  // fast but Google still sees every period URL in the HTML source.
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

  // ─── Stats blocks ──────────────────────────────────────────────
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
    const slice = periodSlice(r.timeline || []);
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
    const newRatio = r.n ? Math.round((r.new||0) / r.n * 100) : 0;
    const renRatio = 100 - newRatio;
    return `
        <div class="dp-stat"><div class="k">${t("rent_sc_contracts")}</div><div class="v">${fmtInt(s.n)}</div></div>
        <div class="dp-stat"><div class="k">${t("rent_sc_med_annual")}</div><div class="v">${s.med_annual ? fmtAedDP(s.med_annual) : '—'}</div></div>
        <div class="dp-stat"><div class="k">${t("rent_sc_ppsqm")}</div><div class="v">${s.med_ppsqm ? fmtInt(s.med_ppsqm)+' AED' : '—'}</div></div>
        <div class="dp-stat"><div class="k">New / Renew</div><div class="v" style="font-size:13px">${newRatio}% / ${renRatio}%</div></div>
    `;
  }

  // ─── Room breakdown / chips ────────────────────────────────────
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
    // Has any room-typed data at all? If not, skip the section entirely.
    const bu = a.by_rooms_unit || {};
    const tbr = a.timeline_by_rooms || {};
    const anyData = ROOM_BREAKDOWN.some(k => (bu[k] && bu[k].n > 0) || (tbr[k] && tbr[k].length));
    if (!anyData) return '';
    // Legend chip per room — click to toggle that room category in the bar
    // chart. Active state is read from S.roomBreakdownHidden (a Set of keys
    // the user has hidden).
    const chips = ROOM_BREAKDOWN.map(k => {
      const total = (bu[k] && bu[k].n) || 0;
      if (total === 0) return '';  // Don't list categories that never appear
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
    // Build per-room time-bucketed counts using the existing period slice.
    // Group monthly points into 12-bucket bins so the bars stay readable
    // even on long timelines (2002 → today = ~280 months).
    const tbr = a.timeline_by_rooms || {};
    const used = ROOM_BREAKDOWN.filter(k => tbr[k] && tbr[k].length);
    if (!used.length) return null;
    // Build the UNION of period-sliced "d" labels across every used room.
    // Earlier we keyed the chart's x-axis off the first non-empty category
    // (`tbr[used[0]]`) — that clipped categories with deeper history (e.g.
    // Palm Jabal Ali's `other` plot sales going back to 2007) down to
    // whichever recent slice the unit categories happened to cover.
    const labelSet = new Set();
    const slicesByRoom = {};
    for (const k of used) {
      const slice = periodSlice(tbr[k]);
      slicesByRoom[k] = slice;
      for (const row of slice) labelSet.add(row.d);
    }
    const sparseLabels = Array.from(labelSet).sort();
    // Densify into the full calendar-month range. Without this, sparse
    // history (e.g. Palm Jabal Ali: 2007-10, 2008-09, 2009-04, 2012-04…)
    // would land in the same fixed-size bucket and bars would lie about
    // span — a 6-entry bucket can cover 10 calendar years.
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
    // Bucket adaptive: aim for ~24 bars max. 1y→monthly, 3y→quarterly,
    // 5y→quarterly, 10y/all→half-year, anything beyond → yearly.
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
        ? slab[0].slice(2)  // "YY-MM"
        : bucketSize === 12
          ? slab[0].slice(0, 4)  // single year
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
    // S.chartData augmentation so the expand modal can rebuild from same data.
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
          legend: { display: false },  // Custom chip legend above the chart.
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
    if (!S.sale) return;
    const legend = S.container && S.container.querySelector('#dp-rb-legend');
    if (legend) {
      // Re-render legend chips (active/hidden state).
      const tmp = document.createElement('div');
      tmp.innerHTML = renderRoomBreakdown(S.sale);
      const fresh = tmp.querySelector('#dp-rb-legend');
      if (fresh) legend.innerHTML = fresh.innerHTML;
    }
    // Re-render the chart in place: destroy old, create new with updated
    // dataset.hidden flags pulled from S.roomBreakdownHidden.
    if (S.roomBreakdownChart) {
      const idx = S.activeCharts.indexOf(S.roomBreakdownChart);
      if (idx >= 0) S.activeCharts.splice(idx, 1);
      S.roomBreakdownChart.destroy();
      S.roomBreakdownChart = null;
    }
    renderRoomBreakdownChart(S.sale);
  }
  function openRoomChartModal() {
    // Reuse the modal shell — render a stacked bar version of the same data
    // but with all room categories + a totals overlay line for context.
    if (!S.roomChartData) return;
    const ser = S.roomChartData;
    const hidden = S.roomBreakdownHidden || new Set();
    const el = _modalDOM();
    el.querySelector('#dp-cm-title').textContent = t('rooms_breakdown_title');
    // Compute a simple total per bucket for the overlay sparkline trendline.
    const totals = ser.buckets.map(b => Object.values(b.totals).reduce((s,v)=>s+v,0));
    const trend = linearTrend(totals);
    const trendLine = trend ? totals.map((_, i) => Math.max(0, trend.intercept + trend.slope * i)) : null;
    const grand = totals.reduce((s,v)=>s+v,0);
    const badges = [];
    badges.push(`<span class="cm-badge muted">Σ ${fmtInt(grand)}</span>`);
    if (trend) badges.push(`<span class="cm-badge ${trend.slope>=0?'pos':'neg'}">${t('ch_trend')}: ${trend.slope>=0?'↑':'↓'} ${Math.abs(trend.slope).toFixed(1)}/bin</span>`);
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');
    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
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
    el.classList.add('open');
  }

  // ─── Tab content ───────────────────────────────────────────────
  function renderBodySale(a) {
    return `
      <div class="period-chips" id="dp-period-chips">${renderPeriodChips()}</div>
      <div class="dp-stats" id="dp-stats-sale">${renderStatsSale(a)}</div>

      <div class="dp-section">
        <h3>${t("sp_section_timeline")}</h3>
        <div class="room-chips" id="dp-room-chips">${renderRoomChips(a)}</div>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px">
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
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_avg")}</div>
            <div class="dp-chart" style="height:180px">
              <button class="chart-expand-btn" type="button" data-dp-expand="avg" title="${t('chart_expand')}" aria-label="${t('chart_expand')}">⛶</button>
              <canvas id="ch-timeline-avg"></canvas>
            </div>
          </div>
        </div>
      </div>

      ${renderRoomBreakdown(a)}

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
    const subOrder = ['Flat','Villa','Studio','Office','Shop','Warehouse','Hotel','Showroom','Complex Villas','Labor Camps','Other'];
    const sub = r.by_subtype || {};
    const subKeys = subOrder.filter(k => sub[k]);
    const sub_rows = subKeys.map(k => {
      const v = sub[k];
      return `<tr><td>${k}</td><td class="num">${fmtInt(v.n)}</td><td class="num">${fmtAedDP(v.med)}</td><td class="num">${fmtInt(v.med_ppsqm)}</td></tr>`;
    }).join('');
    const usage = r.by_usage || {};
    const usageTotal = Object.values(usage).reduce((s,v)=>s+v,0) || 1;
    const usage_rows = Object.entries(usage).sort((a,b)=>b[1]-a[1]).map(([k,v]) => {
      const pct = (v/usageTotal*100).toFixed(1);
      return `<tr><td>${k}</td><td class="num">${fmtInt(v)}</td><td class="num">${pct}%</td></tr>`;
    }).join('');
    const proj_rows = (r.top_projects||[]).map(p => `<tr><td>${projName(p.proj)}</td><td class="num">${fmtInt(p.n)}</td><td class="num">${fmtAedDP(p.med)}</td></tr>`).join('');
    const recent_rows = (r.recent||[]).map(d => {
      const vTag = d.v === 'N' ? t('rent_v_new') : t('rent_v_renew');
      return `<tr><td>${_h(d.d)}</td><td>${projName(d.proj)}</td><td>${_h(d.sub)}</td><td class="num">${d.sqm ? fmtInt(d.sqm) : '—'}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-g dp-tag-g-${d.v==='N'?'O':'R'}">${_h(vTag)}</span></td></tr>`;
    }).join('');

    return `
      <div class="period-chips" id="dp-period-chips-rent">${renderPeriodChipsRent()}</div>
      <div class="dp-stats" id="dp-stats-rent">${renderStatsRent(r)}</div>

      <div class="dp-section">
        <h3>${t("rent_section_timeline")}</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_count")}</div>
            <div class="dp-chart" style="height:180px"><canvas id="ch-rent-count"></canvas></div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("rent_th_med")}</div>
            <div class="dp-chart" style="height:180px"><canvas id="ch-rent-med"></canvas></div>
          </div>
        </div>
      </div>

      ${sub_rows ? `<div class="dp-section">
        <h3>${t("rent_section_subtype")}</h3>
        <table class="dp-table"><thead><tr><th>${t("rent_th_subtype")}</th><th class="num">${t("th_n")}</th><th class="num">${t("rent_th_med")}</th><th class="num">${t("rent_th_ppsqm")}</th></tr></thead><tbody>${sub_rows}</tbody></table>
      </div>` : ''}

      ${usage_rows ? `<div class="dp-section">
        <h3>${t("rent_section_usage")}</h3>
        <table class="dp-table"><thead><tr><th>${t("rent_section_usage")}</th><th class="num">${t("th_n")}</th><th class="num">%</th></tr></thead><tbody>${usage_rows}</tbody></table>
      </div>` : ''}

      ${proj_rows ? `<details class="dp-collapsible" data-tier="premium">
        <summary>${t("rent_section_top_projects")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_project")}</th><th class="num">${t("th_n")}</th><th class="num">${t("rent_th_med")}</th></tr></thead><tbody>${proj_rows}</tbody></table>
        ${listLinkFooter('top_projects', 'Открыть полный список топ-проектов по аренде')}
      </details>` : ''}

      ${recent_rows ? `<details class="dp-collapsible" data-tier="premium">
        <summary>${t("rent_section_recent")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("rent_th_subtype")}</th><th class="num">${t("th_sqm")}</th><th class="num">${t("th_aed")}</th><th>${t("rent_th_version")}</th></tr></thead><tbody>${recent_rows}</tbody></table>
        ${listLinkFooter('recent', 'Открыть последние договоры аренды')}
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
    // 'both' — slide-out panel keeps tabs.
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

  // ─── Chart rendering ───────────────────────────────────────────
  function rgba(hex, alpha) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return `rgba(29,78,216,${alpha})`;
    return `rgba(${parseInt(m[1],16)},${parseInt(m[2],16)},${parseInt(m[3],16)},${alpha})`;
  }
  // Trailing simple moving average. Returns NaN for indices < window-1 so the
  // line just doesn't render there (Chart.js skips NaN/null cleanly).
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
  // OLS slope+intercept of (i, arr[i]) — for the trendline. Skips NaN/0-len.
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
  // Year-over-year % change of last vs same month a year ago. Labels are
  // "YYYY-MM"-shaped → compare by index 12 back.
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
    const color  = ROOM_COLORS[S.roomFilter] || '#1d4ed8';
    const bg = rgba(color, .14);
    // Stash each metric's series + labels so the expand-modal can rebuild
    // an enriched chart from the same data without re-fetching.
    S.chartData = {
      labels: labels.slice(),
      fullLabels: series.map(p => p.d),
      count:  { values: series.map(p => p.n),                                    fmtY: v => v,        fmtTip: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(), label: t('sp_subsection_count') },
      volume: { values: series.map(p => p.vol || 0),                             fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                                label: t('sp_subsection_volume') },
      avg:    { values: series.map(p => p.n ? Math.round(p.vol / p.n) : 0),      fmtY: fmtAxisAed,    fmtTip: fmtAedDP,                                                label: t('sp_subsection_avg') },
      color,
    };
    const mkChart = (id, data, fmtY, tooltipFmt) => {
      const ctx = document.getElementById(id);
      if (!ctx) return;
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
    mkChart('ch-timeline-count',  S.chartData.count.values,  S.chartData.count.fmtY,  S.chartData.count.fmtTip);
    mkChart('ch-timeline-volume', S.chartData.volume.values, S.chartData.volume.fmtY, S.chartData.volume.fmtTip);
    mkChart('ch-timeline-avg',    S.chartData.avg.values,    S.chartData.avg.fmtY,    S.chartData.avg.fmtTip);
  }

  // ─── Chart expand modal — "Bloomberg-lite" overlay ──────────────
  // Indicators packed onto the enlarged chart:
  //   1. Channel band  : SMA(window) ± 1.5σ — shaded gray. Visual at-a-glance
  //      "normal range"; periods poking out are the outliers.
  //   2. Moving average: dashed gray line through the band's centre.
  //   3. Segment fill  : actual line fills to the MA — green when above,
  //      red when below. Reads like a heat-map for momentum.
  //   4. Trendline     : OLS linear regression over the visible period. Tells
  //      the user whether the market in this district is structurally
  //      heading up or down once short-term noise is smoothed out.
  //   5. Median rule   : horizontal line at the period's median. Useful as
  //      a "fair value" reference vs. recent moves.
  //   6. Header badges : YoY %, vs-MA spread, volatility (σ/μ).
  function _maWindow(n) {
    // Pick a smoothing window proportional to the series length, capped to
    // keep the band readable. 6 months is a sane minimum for monthly DLD data.
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
          <button class="chart-modal-close" id="dp-cm-close" type="button" aria-label="Close">✕</button>
        </div>
        <div class="chart-modal-body"><canvas id="dp-cm-canvas"></canvas></div>
      </div>`;
    document.body.appendChild(el);
    return el;
  }
  function _closeChartModal() {
    const el = document.getElementById('dp-chart-modal');
    if (!el) return;
    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    el.classList.remove('open');
  }
  function openChartModal(metric) {
    const cd = S.chartData;
    if (!cd || !cd[metric]) return;
    const m = cd[metric];
    const labels = cd.labels.slice();
    const data = m.values.slice();
    if (data.length < 2) return;  // not enough to plot anything meaningful

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

    const color = cd.color || '#1d4ed8';
    const grnLine = 'rgba(34,197,94,1)';
    const redLine = 'rgba(239,68,68,1)';
    const grnFill = 'rgba(34,197,94,0.16)';
    const redFill = 'rgba(239,68,68,0.18)';

    const el = _modalDOM();
    el.querySelector('#dp-cm-title').textContent = m.label;
    const badges = [];
    if (yoy != null)        badges.push(`<span class="cm-badge ${yoy>=0?'pos':'neg'}">YoY: ${(yoy>=0?'+':'')}${yoy.toFixed(1)}%</span>`);
    if (lastSpread != null) badges.push(`<span class="cm-badge ${lastSpread>=0?'pos':'neg'}">vs MA${w}: ${(lastSpread>=0?'+':'')}${lastSpread.toFixed(1)}%</span>`);
    if (vol != null)        badges.push(`<span class="cm-badge muted">σ/μ: ${vol.toFixed(0)}%</span>`);
    if (trend)              badges.push(`<span class="cm-badge ${trend.slope>=0?'pos':'neg'}">${t('ch_trend')}: ${trend.slope>=0?'↑':'↓'}</span>`);
    badges.push(`<span class="cm-badge muted">n=${data.length}</span>`);
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');

    if (S.modalChart) { S.modalChart.destroy(); S.modalChart = null; }
    const ctx = el.querySelector('#dp-cm-canvas');
    S.modalChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          // 0 — lower band anchor (invisible line; gives the fill an anchor).
          { label: 'lower', data: lower, borderWidth: 0, pointRadius: 0, fill: false, order: 6 },
          // 1 — upper band, fills back to dataset 0 → the shaded channel.
          { label: t('ch_channel'), data: upper, borderColor: 'rgba(148,163,184,0.55)', borderWidth: 1, borderDash:[3,3], pointRadius: 0, fill: '-1', backgroundColor: 'rgba(148,163,184,0.10)', order: 5 },
          // 2 — moving average centerline.
          { label: t('ch_ma') + ` (${w})`, data: ma, borderColor: '#64748b', borderWidth: 1.5, borderDash: [6,4], pointRadius: 0, fill: false, order: 4 },
          // 3 — trendline (OLS).
          ...(trendLine ? [{ label: t('ch_trend'), data: trendLine, borderColor: '#0f172a', borderWidth: 1.2, borderDash:[2,3], pointRadius: 0, fill: false, order: 3 }] : []),
          // 4 — median horizontal.
          ...(median != null ? [{ label: t('ch_median'), data: data.map(()=>median), borderColor: 'rgba(29,78,216,0.55)', borderWidth: 1, borderDash:[1,2], pointRadius: 0, fill: false, order: 2 }] : []),
          // 5 — actual line + green/red fill-to-MA momentum heatmap.
          {
            label: m.label,
            data,
            borderColor: color,
            borderWidth: 2.5,
            pointRadius: 2.2,
            pointHoverRadius: 4,
            // Fill to MA dataset (always at absolute index 2) with conditional
            // above/below coloring — green when actual > MA, red when below.
            fill: { target: 2, above: grnFill, below: redFill },
            // segment.borderColor: greens up-swings, reds down-swings.
            segment: {
              borderColor: ctx => {
                const i = ctx.p0DataIndex;
                if (i >= ma.length - 1) return color;
                const v0 = data[i], v1 = data[i+1];
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
    el.classList.add('open');
  }
  // ─── Insight donuts ─────────────────────────────────────────────
  // 4-up grid that turns the legacy expandable tables (top projects / top
  // deals / recent 20) into at-a-glance slices alongside the off-plan vs
  // ready donut. The deeper view (full table) is still one click away via
  // the "Открыть полный список →" footer link under each card.
  const DONUT_FALLBACK_COLORS = ['#1d4ed8','#0ea5e9','#22c55e','#eab308','#f97316','#ef4444','#a855f7','#ec4899','#14b8a6','#64748b'];
  const OP_COLORS = { 'Off-Plan': '#f0a020', 'Ready': '#21918c' };
  const ROOM_DONUT_COLORS = {
    'Studio': '#9ca3af',
    '1BR': '#60a5fa', '2BR': '#3b82f6', '3BR': '#1d4ed8', '4BR+': '#1e3a8a',
    'Villa': '#d97706',
    'Other': '#a78bfa',
  };
  // Empty-state placeholder. Chart.js can't draw a donut with no data — show
  // a centred "—" so the card still occupies its grid slot.
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
  // Build the off-plan dataset: {Off-Plan: n, Ready: n} (sometimes missing
  // a key entirely — handle gracefully).
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
  // Top projects by deal count — keep the leaders, fold the long tail into
  // a single "Others" slice so the donut doesn't fragment into 30 toothpicks.
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
  // "When did the big money land?" — group the top-10 largest deals by
  // calendar year, value = sum of AED. Highlights "this district had a 2014
  // spike of 5B AED + a smaller 2020 echo" at a glance.
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
  // Distribution of the most recent N transactions by room type. A snapshot
  // of "what's actually changing hands right now" — complements the rooms
  // breakdown chart (which is historical).
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
    // Cache datasets so the expand-modal can rebuild from the same data.
    S.donutData = {
      offplan:  _offplanData(a),
      projects: _projectsDonutData(a),
      deals:    _dealsByYearData(a),
      recent:   _recentByRoomData(a),
    };
    _renderDonut('ch-offplan',           S.donutData.offplan);
    _renderDonut('ch-donut-projects',    S.donutData.projects);
    _renderDonut('ch-donut-deals',       S.donutData.deals);
    _renderDonut('ch-donut-recent',      S.donutData.recent);
  }
  // Big-mode donut: legend on the side + a summary "leader" badge in the
  // header, so the modal reads like a quick analytic exhibit.
  function openDonutModal(kind) {
    if (!S.donutData || !S.donutData[kind]) return;
    const d = S.donutData[kind];
    const titleKey = {
      offplan:  'sp_section_offplan',
      projects: 'donut_proj_title_full',
      deals:    'donut_deals_title_full',
      recent:   'donut_recent_title_full',
    }[kind];
    const el = _modalDOM();
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
    el.classList.add('open');
  }
  function renderSaleCharts(a) {
    renderTimelineCharts(a);
    try { renderRoomBreakdownChart(a); } catch(e) { console.error('rooms chart:', e); }
    try { renderInsightDonuts(a);    } catch(e) { console.error('donuts:', e); }
  }
  function renderRentCharts(r) {
    const series = periodSlice(r.timeline || []);
    const labels = series.map(p => p.d);
    const color = '#0ea5e9';
    const bg = 'rgba(14,165,233,.14)';
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
    mkChart('ch-rent-med',   series.map(p => p.med || 0), fmtAxisAed, fmtAedDP);
  }

  // ─── Event handlers (delegated) ────────────────────────────────
  function bindDelegates() {
    if (S._bound) return;
    S._bound = true;
    // Use document so it survives container re-renders.
    document.addEventListener('click', (e) => {
      // Tab switch
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
      // Period change
      const periodBtn = e.target.closest('[data-dp-set-period]');
      if (periodBtn && S.container && S.container.contains(periodBtn)) {
        // Cmd/Ctrl/middle-click → let browser open the period URL in a new tab.
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
      // Room filter change
      const roomBtn = e.target.closest('[data-dp-set-room]');
      if (roomBtn && S.container && S.container.contains(roomBtn)) {
        const k = roomBtn.dataset.dpSetRoom;
        if (S.roomFilter !== k) {
          S.roomFilter = k;
          refreshSale();
        }
        return;
      }
      // Chart expand button → open enriched modal chart.
      const expandBtn = e.target.closest('[data-dp-expand]');
      if (expandBtn && S.container && S.container.contains(expandBtn)) {
        e.preventDefault();
        openChartModal(expandBtn.dataset.dpExpand);
        return;
      }
      // Room-breakdown expand button → stacked bar in modal.
      const expandRoomBtn = e.target.closest('[data-dp-expand-rooms]');
      if (expandRoomBtn && S.container && S.container.contains(expandRoomBtn)) {
        e.preventDefault();
        openRoomChartModal();
        return;
      }
      // Insight-donut expand button → enlarged donut in modal.
      const expandDonutBtn = e.target.closest('[data-dp-expand-donut]');
      if (expandDonutBtn && S.container && S.container.contains(expandDonutBtn)) {
        e.preventDefault();
        openDonutModal(expandDonutBtn.dataset.dpExpandDonut);
        return;
      }
      // Room-breakdown legend chip → toggle category in/out of the chart.
      const rbToggle = e.target.closest('[data-dp-toggle-room]');
      if (rbToggle && S.container && S.container.contains(rbToggle)) {
        const k = rbToggle.dataset.dpToggleRoom;
        if (!S.roomBreakdownHidden) S.roomBreakdownHidden = new Set();
        if (S.roomBreakdownHidden.has(k)) S.roomBreakdownHidden.delete(k);
        else S.roomBreakdownHidden.add(k);
        refreshRoomBreakdown();
        return;
      }
      // Close modal: explicit ✕ button OR click on the dim backdrop.
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
  }
  function refreshRent() {
    if (!S.rent) return;
    const pc = S.container.querySelector('#dp-period-chips-rent');
    if (pc) pc.innerHTML = renderPeriodChipsRent();
    const stEl = S.container.querySelector('#dp-stats-rent');
    if (stEl) stEl.innerHTML = renderStatsRent(S.rent);
    // Re-render rent charts only if its tab pane is currently visible
    if (S.container.querySelector('#ch-rent-count')) {
      destroyRentCharts();
      renderRentCharts(S.rent);
    }
  }

  // ─── Entry point ───────────────────────────────────────────────
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
