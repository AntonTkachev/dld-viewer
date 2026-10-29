// District detail panel: room breakdown chart/modal and building-age (vintage) charts.
(function () {
  const {
    PERIODS, ROOM_BREAKDOWN, ROOM_COLORS, S, _chartFont, _estNote, _modalDOM, _roomsRec,
    _stackTotals, _useCanvasPane, _workdays, _xAxis, _yAxis, fmtAxisAed, fmtInt, linearTrend,
    periodSlice, renderRoomBreakdown, rgba, roomLabel, t
  } = window._dp;

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
    if (!sparseLabels.length) return null;

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
    // Round only the top visible segment of each stack
    const topKey = [...ser.used].reverse().find(k => !hidden.has(k));
    datasets.forEach(ds => { ds.borderRadius = ds._roomKey === topKey ? { topLeft: 3, topRight: 3 } : 0; ds.borderSkipped = false; });
    const fc = _roomForecast(ser, hidden);
    if (fc) datasets.push(fc.dataset);
    const ch = new Chart(ctx, {
      type: 'bar',
      data: { labels: ser.labels, datasets },
      plugins: [_forecastOutline, _stackTotals],
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: false },  
          tooltip: { callbacks: _roomForecastTooltip(fc) },
        },
        layout: { padding: { top: 14 } },
        scales: {
          x: _xAxis({ stacked: true, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } }),
          y: _yAxis(v => fmtAxisAed(v), { stacked: true, beginAtZero: true }),
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
  function _vintageBuckets(rec) {
    const v = rec && rec.vintage;
    if (!v) return null;
    const present = VINTAGE_ORDER.filter(b => v[b] && v[b].ppsqm);
    return present.length >= 2 ? present : null;
  }
  // Per purchase-year cohort: baseline = seed-year average, return measured to the latest point
  function _vintageCohorts(rec) {
    const vp = rec && (rec.vintage_paths_m || rec.vintage_paths);
    if (!vp) return null;
    const monthly = !!rec.vintage_paths_m;
    const mid = d => d.length === 4 ? +d * 12 + 5.5 : _monthIdx(d);
    const cohorts = Object.keys(vp).sort().filter(y => vp[y].length >= (monthly ? 12 : 3)).map(c => {
      const pts = vp[c];
      const seed = pts.filter(p => p.d.slice(0, 4) === c).map(p => p.med);
      const buy = seed.length ? seed.reduce((a, b) => a + b, 0) / seed.length : pts[0].med;
      const last = pts[pts.length - 1];
      const yrs = Math.max(1, (mid(last.d) - (+c * 12 + 5.5)) / 12);
      return {
        c, pts, buy, last: last.med, yrs,
        ret: (last.med / buy - 1) * 100,
        cagr: (Math.pow(last.med / buy, 1 / yrs) - 1) * 100,
        x: d => (mid(d) - (+c * 12 + 5.5)) / 12,
      };
    }).filter(x => x.buy > 0);
    return cohorts.length >= 2 ? { monthly, cohorts } : null;
  }
  const _pct = v => (v > 0 ? '+' : '') + Math.round(v) + '%';
  const _hatchCache = {};
  function _hatch(color) {
    if (_hatchCache[color]) return _hatchCache[color];
    const cv = document.createElement('canvas');
    cv.width = cv.height = 6;
    const g = cv.getContext('2d');
    g.fillStyle = rgba(color, 0.08);
    g.fillRect(0, 0, 6, 6);
    g.strokeStyle = rgba(color, 0.5);
    g.beginPath();
    g.moveTo(0, 6); g.lineTo(6, 0);
    g.moveTo(-1, 1); g.lineTo(1, -1);
    g.moveTo(5, 7); g.lineTo(7, 5);
    g.stroke();
    return (_hatchCache[color] = g.createPattern(cv, 'repeat'));
  }

  // Dashed line at the newest-building level + hatched gap showing each older bucket's discount
  const _vintageGap = {
    id: 'vintageGap',
    afterDatasetsDraw(chart) {
      const ds = chart.data.datasets[0];
      if (!ds || !ds._base) return;
      const c = chart.ctx, area = chart.chartArea, font = _chartFont();
      const baseY = chart.scales.y.getPixelForValue(ds._base);
      c.save();
      c.setLineDash([4, 3]);
      c.strokeStyle = '#94a3b8';
      c.beginPath(); c.moveTo(area.left, baseY); c.lineTo(area.right, baseY); c.stroke();
      c.setLineDash([]);
      c.textAlign = 'center';
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        const { x, y, width, base } = bar.getProps(['x', 'y', 'width', 'base'], true);
        c.font = `600 ${width < 80 ? 9.5 : 11}px ` + font;
        c.fillStyle = ds._ink[i];
        if (base - y > 20) c.fillText(fmtInt(ds.data[i]), x, base - 7);
        if (i === 0) return;
        const rel = (ds.data[i] / ds._base - 1) * 100;
        if (Math.abs(rel) < 0.5) return;
        const col = rel > 0 ? '#16a34a' : '#dc2626';
        const y1 = Math.min(y, baseY), y2 = Math.max(y, baseY);
        c.fillStyle = _hatch(col);
        c.fillRect(x - width / 2, y1, width, y2 - y1);
        c.font = '700 13px ' + font;
        c.fillStyle = col;
        c.fillText(_pct(rel), x, y2 - y1 >= 20 ? (y1 + y2) / 2 + 5 : y1 - 6);
      });
      c.restore();
    },
  };
  // "+128%" above positive bars, below negative ones
  const _signedBarLabels = {
    id: 'signedBarLabels',
    afterDatasetsDraw(chart) {
      const ds = chart.data.datasets[0], c = chart.ctx;
      c.save();
      c.textAlign = 'center';
      chart.getDatasetMeta(0).data.forEach((bar, i) => {
        const { x, y, width } = bar.getProps(['x', 'y', 'width'], true);
        if (width < 14) return;
        const v = ds.data[i];
        c.font = `700 ${width < 24 ? 9 : 11}px ` + _chartFont();
        c.fillStyle = v >= 0 ? '#15803d' : '#b91c1c';
        c.fillText(_pct(v), x, v >= 0 ? y - 5 : y + 13);
      });
      c.restore();
    },
  };
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
    const vc = _vintageCohorts(rec);
    if (!ctx || !vc) return;
    const cs = vc.cohorts;
    const unit = kind === 'rent' ? ' AED/м²/' + t('unit_year_short') : ' AED/м²';
    const vals = cs.map(x => Math.round(x.ret));
    const ch = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: cs.map(x => x.c),
        datasets: [{
          data: vals,
          backgroundColor: vals.map(v => v >= 0 ? 'rgba(22,163,74,0.75)' : 'rgba(220,38,38,0.75)'),
          borderRadius: 3, barPercentage: 0.75, categoryPercentage: 0.85,
        }],
      },
      plugins: [_signedBarLabels],
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 16 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: {
            title: items => t(kind === 'rent' ? 'vin_pick_rent' : 'vin_pick') + ' ' + items[0].label,
            label: c => {
              const x = cs[c.dataIndex];
              return [' ' + fmtInt(Math.round(x.buy)) + ' → ' + fmtInt(x.last) + unit,
                      ' ' + _pct(x.ret) + ' · ' + (x.cagr >= 0 ? '+' : '') + x.cagr.toFixed(1) + '%' + t('vin_per_year')];
            },
          } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true } },
          y: {
            grace: '10%',
            ticks: { font: { size: 10 }, callback: v => _pct(v) },
            grid: { color: c => c.tick.value === 0 ? '#475569' : '#f1f5f9', lineWidth: c => c.tick.value === 0 ? 1.5 : 1 },
          },
        },
      },
    });
    S.activeCharts.push(ch);
  }
  function renderVintageChart(rec, kind) {
    const ctx = document.getElementById('ch-vintage-' + kind);
    const present = _vintageBuckets(rec);
    if (!ctx || !present) return;
    const labels = { v0_1: t('vin_0_1'), v2_4: t('vin_2_4'), v5_10: t('vin_5_10'), v11p: t('vin_11p') };
    const vals = present.map(b => rec.vintage[b].ppsqm);
    const ns   = present.map(b => rec.vintage[b].n);
    const base = vals[0];
    const unit = kind === 'rent' ? ' AED/м²/' + t('unit_year_short') : ' AED/м²';
    // One hue that fades with age: newest = solid, oldest = washed out
    const hue = kind === 'rent' ? '#0ea5e9' : '#4f46e5';
    const fade = { v0_1: 1, v2_4: 0.7, v5_10: 0.48, v11p: 0.3 };
    const ch = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: present.map(b => labels[b]),
        datasets: [{
          data: vals,
          backgroundColor: present.map(b => rgba(hue, fade[b])),
          borderWidth: 0, borderRadius: 3,
          barPercentage: 0.6,
          _base: base,
          _ink: present.map(b => fade[b] >= 0.6 ? '#ffffff' : '#334155'),
        }],
      },
      plugins: [_vintageGap],
      options: {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: 18 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => {
            const i = c.dataIndex;
            const relTxt = i === 0 ? '' : ' · ' + _pct((vals[i] / base - 1) * 100) + ' vs ' + labels[present[0]];
            return ' ' + fmtInt(vals[i]) + unit + ' · n=' + fmtInt(ns[i]) + relTxt;
          } } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: { display: false, beginAtZero: true, grace: '8%' },
        },
      },
    });
    S.activeCharts.push(ch);
  }

  Object.assign(window._dp, {
    _pct, _vintageCohorts, openRoomChartModal, refreshRoomBreakdown, renderRoomBreakdownChart,
    renderVintageChart, renderVintagePaths, renderVintageSection
  });
})();
