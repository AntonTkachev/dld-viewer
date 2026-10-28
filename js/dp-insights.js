// District detail panel: insight donuts and sale/rent chart sets.
(function () {
  const {
    ROOM_COLORS, ROOM_ORDER, S, _areaFill, _donutCenter, _h, _lastValueTag, _modalDOM, _tints,
    _useCanvasPane, _xAxis, _yAxis, fmtAedDP, fmtAxisAed, fmtInt, medPrice, periodSlice,
    renderRoomBreakdownChart, renderTimelineCharts, renderVintageChart, renderVintagePaths,
    roomLabel, roomTimelineFor, t, tVal
  } = window._dp;

  const OP_COLORS = { 'Off-Plan': '#f59e0b', 'Ready': '#4f46e5' };

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
  // Values sorted desc: spread the scale over slices ≥2% only, crumbs go neutral grey
  function _donutPalette(values) {
    const tot = values.reduce((s, v) => s + v, 0) || 1;
    const m = Math.max(1, values.filter(v => v / tot >= 0.02).length);
    const steps = _tints(m);
    return values.map((_, i) => i < m ? steps[i] : '#cbd5e1');
  }

  // Period totals from the monthly timeline; 'all' keeps the all-time fields
  function _periodCounts(a) {
    if (S.period === 'all') return null;
    let n = 0, op = 0, mort = 0;
    for (const p of periodSlice(a.timeline || [])) { n += p.n || 0; op += p.op || 0; mort += p.mort || 0; }
    return { n, op, mort };
  }
  function _offplanData(a) {
    const pc = _periodCounts(a);
    const op = pc ? { 'Ready': pc.n - pc.op, 'Off-Plan': pc.op } : (a.offplan || {});
    const labels = Object.keys(op).filter(k => op[k] > 0);
    if (!labels.length) return null;
    return {
      labels,
      values: labels.map(k => op[k]),
      colors: labels.map(k => OP_COLORS[k] || '#64748b'),
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
      colors: _tints(sorted.length).reverse(),
      fmt: fmtAedDP,
    };
  }

  // Same buckets as the room chips: DLD files many villas as unnamed Land plots with no bedroom count
  function _recentByRoomData(a) {
    const list = (a.recent || []).filter(d => d.seg);
    if (!list.length) return null;
    const counts = new Map();
    for (const d of list) counts.set(d.seg, (counts.get(d.seg) || 0) + 1);
    const keys = [...ROOM_ORDER.filter(k => counts.has(k)), ...[...counts.keys()].filter(k => !ROOM_ORDER.includes(k))];
    return {
      labels: keys.map(k => roomLabel(k) || k),
      values: keys.map(k => counts.get(k)),
      colors: keys.map(k => ROOM_COLORS[k] || '#64748b'),
      fmt: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(),
    };
  }

  function _paymentData(a) {
    const pc = _periodCounts(a);
    const p = pc ? { financed: Math.min(pc.mort, pc.n), cash: pc.n - Math.min(pc.mort, pc.n) } : (a.payment || {});
    const cash = p.cash || 0;
    const fin  = p.financed || 0;
    if (!(cash + fin)) return null;
    return {
      labels: [t('donut_payment_cash'), t('donut_payment_financed')],
      values: [cash, fin],
      colors: ['#4f46e5', '#f59e0b'],
      fmt: v => fmtInt(v) + ' ' + t('ch_count').toLowerCase(),
    };
  }
  function _renderDonut(canvasId, d, opts) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;
    if (!d) { _donutEmpty(canvasId, t('donut_empty')); return null; }
    const ch = new Chart(ctx, {
      type: 'doughnut',
      data: { labels: d.labels, datasets: [{ data: d.values, backgroundColor: d.colors, borderWidth: 2, borderColor: '#fff', borderRadius: 3, _center: true }] },
      plugins: [_donutCenter],
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '70%',
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 10.5 }, padding: 6,
            // "Ready 42%" — share in the legend, long project names clipped
            generateLabels: chart => {
              const items = Chart.overrides.doughnut.plugins.legend.labels.generateLabels(chart);
              const vals = chart.data.datasets[0].data, tot = vals.reduce((s, v) => s + v, 0);
              return items.filter(it => !tot || vals[it.index] / tot >= 0.01).map(it => {
                const name = String(it.text);
                return Object.assign(it, { text: (name.length > 16 ? name.slice(0, 15) + '…' : name) + (tot ? ' ' + Math.round(vals[it.index] / tot * 100) + '%' : '') });
              });
            },
          } },
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
    for (const c of S.donutCharts || []) {
      c.destroy();
      const i = S.activeCharts.indexOf(c);
      if (i >= 0) S.activeCharts.splice(i, 1);
    }
    S.donutData = {
      offplan:  _offplanData(a),
      deals:    _dealsByYearData(a),
      recent:   _recentByRoomData(a),
      payment:  _paymentData(a),
    };
    S.donutCharts = [
      _renderDonut('ch-offplan',           S.donutData.offplan),
      _renderDonut('ch-donut-deals',       S.donutData.deals),
      _renderDonut('ch-donut-recent',      S.donutData.recent),
      _renderDonut('ch-donut-payment',     S.donutData.payment),
    ].filter(Boolean);
  }

  function openDonutModal(kind) {
    if (!S.donutData || !S.donutData[kind]) return;
    const d = S.donutData[kind];
    const titleKey = {
      offplan:  'sp_section_offplan',
      deals:    'donut_deals_title_full',
      recent:   'donut_recent_title_full',
      payment:  'donut_payment_title_full',
    }[kind];
    const el = _modalDOM();
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = 'none';
    el.querySelector('#dp-cm-title').textContent = t(titleKey);
    const total = d.values.reduce((s,v)=>s+v,0);
    const others = new Set([t('donut_others'), t('rent_subtype_other')]);
    const named = d.values.reduce((b, v, i) => others.has(d.labels[i]) || (b >= 0 && d.values[b] >= v) ? b : i, -1);
    const leadIdx = named >= 0 ? named : d.values.indexOf(Math.max(...d.values));
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
    const items = top.map(([k, n]) => ({ name: tVal('rent_ptype_map', k), n }));
    if (tailN > 0) items.push({ name: t('rent_subtype_other'), n: tailN });
    return {
      labels: items.map(i => i.name),
      values: items.map(i => i.n),
      colors: _donutPalette(items.map(i => i.n)).map((c, i) => tailN > 0 && i === items.length - 1 ? '#cbd5e1' : c),
      fmt: v => fmtInt(v) + ' ' + t('rent_sc_contracts').toLowerCase(),
    };
  }
  function _rentUsageDonutData(r) {
    const usage = r.by_usage || {};
    const entries = Object.entries(usage).filter(([, n]) => n > 0);
    if (!entries.length) return null;
    entries.sort((a,b) => b[1] - a[1]);
    return {
      labels: entries.map(([k]) => tVal('rent_usage_map', k)),
      values: entries.map(([, n]) => n),
      colors: _donutPalette(entries.map(([, n]) => n)),
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
      colors: ['#4f46e5', '#a5b4fc'],
      fmt: v => fmtInt(v) + ' ' + t('rent_sc_contracts').toLowerCase(),
    };
  }

  function _rentTenantDonutData(r) {
    const tn = r.by_tenant || {};
    const label = { 'Person': t('rent_tenant_person'), 'Authority': t('rent_tenant_authority'), 'Unknown': t('rent_tenant_unknown') };
    const color = { 'Person': '#4f46e5', 'Authority': '#f59e0b', 'Unknown': '#cbd5e1' };
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

    const tlSource = roomTimelineFor(r);
    const series = periodSlice(tlSource);
    const labels = series.map(p => p.d.length === 10 ? p.d.slice(5) : p.d);
    const fullLabels = series.map(p => p.d);
    const color = '#0ea5e9';
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
        data:{ labels, datasets:[{ data, borderColor:color, backgroundColor:_areaFill(color), borderWidth: 2, tension:.25, fill:true,
          pointRadius: 0, pointHoverRadius: 4, pointHoverBorderColor: '#fff', pointHoverBorderWidth: 2, pointHoverBackgroundColor: color,
          _tag: { fmt: v => fmtAxisAed(Math.round(v)), color } }]},
        plugins: [_lastValueTag],
        options:{
          responsive:true, maintainAspectRatio:false,
          interaction:{intersect:false, mode:'index'},
          plugins:{legend:{display:false}, tooltip:{callbacks:{label: c => ' ' + tooltipFmt(c.parsed.y)}}},
          scales:{ y: _yAxis(fmtY, { beginAtZero: true, grace: '12%' }), x: _xAxis() },
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
      const tenant = _rentTenantDonutData(r);
      // 64 districts (and the Dubai total) ship no tenant split — hide the card instead of an empty ring
      const tenantCard = document.getElementById('dp-rent-tenant-card');
      if (tenantCard) tenantCard.style.display = tenant ? '' : 'none';
      if (tenant) _renderDonut('ch-rent-donut-tenant', tenant);
      _renderDonut('ch-rent-donut-newrenew', _rentNewRenewDonutData(r));
    } catch(e) { console.error('rent donuts:', e); }
  }

  Object.assign(window._dp, {
    openDonutModal, renderInsightDonuts, renderRentCharts, renderSaleCharts
  });
})();
