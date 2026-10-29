// District detail panel: fullscreen chart modal and vintage-paths modal.
(function () {
  const {
    S, _chartFont, _disposeLwc, _ensureECharts, _ensureLwc, _h, _maWindow, _modalDOM, _pct,
    _renderModalECharts, _renderModalLwc, _robustMax, _useCanvasPane, _vintageCohorts, alignedMA,
    crossState, fmtInt, linearTrend, renderPeriodChips, renderRoomChips, roomView, t, yoyPercent
  } = window._dp;

  function openVintagePathsModal(source) {
    source = source || 'sale';
    const rec = roomView(source === 'rent' ? S.rent : S.sale);
    const vc = _vintageCohorts(rec);
    if (!vc) return;
    const { monthly, cohorts } = vc;
    const unit = source === 'rent' ? ' AED/м²/' + t('unit_year_short') : ' AED/м²';
    const pick = cohorts.some(x => x.c === S.vinPick) ? S.vinPick : cohorts[0].c;

    const el = _modalDOM();
    el.dataset.metric = 'vintage_paths';
    el.dataset.source = source;
    el.querySelector('#dp-cm-title').textContent = t(source === 'rent' ? 'vin_paths_rent' : 'vin_paths');
    const controls = el.querySelector('#dp-cm-controls');
    if (controls) controls.style.display = '';
    el.querySelector('#dp-cm-periods').innerHTML = '';
    const chip = v => `<button class="period-chip${v === pick ? ' active' : ''}" type="button" data-dp-vin-pick="${v}">${v}</button>`;
    el.querySelector('#dp-cm-rooms').innerHTML = `<span class="pc-lbl">${t(source === 'rent' ? 'vin_pick_rent' : 'vin_pick')}:</span>`
      + cohorts.map(x => chip(x.c)).join('');

    const maNan = (arr, w) => arr.map((_, i) => {
      let s = 0, c = 0;
      for (let j = Math.max(0, i - w + 1); j <= i; j++) {
        if (Number.isFinite(arr[j])) { s += arr[j]; c++; }
      }
      return c >= Math.max(2, Math.ceil(w / 2)) ? s / c : NaN;
    });
    // x = years since purchase, y = % vs purchase price: every line starts at the same origin
    const datasets = cohorts.map(x => {
      const w = monthly ? _maWindow(x.pts.length) : 1;
      const raw = x.pts.map(p => p.med);
      const smooth = w > 1 ? maNan(raw, w) : raw;
      const data = [{ x: 0, y: 0, v: x.buy }];
      x.pts.forEach((p, i) => {
        const px = x.x(p.d);
        if (px > 0 && Number.isFinite(smooth[i])) data.push({ x: px, y: (smooth[i] / x.buy - 1) * 100, v: raw[i] });
      });
      const on = pick === x.c;
      return {
        label: x.c, data, _ret: x.ret, _on: on, _labelCol: x.ret >= 0 ? '#15803d' : '#b91c1c',
        borderColor: on ? '#16a34a' : 'rgba(203,213,225,0.7)',
        // Red while the picked cohort sits below its purchase price
        segment: on ? { borderColor: c => c.p1.parsed.y < 0 ? '#dc2626' : undefined } : undefined,
        borderWidth: on ? 3 : 1.6,
        pointRadius: 0, pointHoverRadius: on ? 4 : 0, tension: 0.25, order: on ? 0 : 1,
      };
    });

    const ranked = cohorts.slice().sort((a, b) => b.ret - a.ret);
    const bst = ranked[0], wst = ranked[ranked.length - 1];
    const badges = [
      `<span class="cm-badge pos">${t('vin_best')}: ${bst.c} ${_pct(bst.ret)}</span>`,
      `<span class="cm-badge ${wst.ret >= 0 ? 'muted' : 'neg'}">${t('vin_worst')}: ${wst.c} ${_pct(wst.ret)}</span>`,
    ];
    if (monthly) badges.push(`<span class="cm-badge muted">${t('vin_smoothing')}</span>`);
    el.querySelector('#dp-cm-badges').innerHTML = badges.join('');

    const canvas = _useCanvasPane(el);
    el.classList.add('open');

    // Picked cohort's result at its line end
    const endLabels = {
      id: 'vinEndLabels',
      afterDatasetsDraw(chart) {
        const i = chart.data.datasets.findIndex(ds => ds._on);
        const pt = i >= 0 && chart.getDatasetMeta(i).data.at(-1);
        if (!pt) return;
        const ds = chart.data.datasets[i], c = chart.ctx;
        c.save();
        c.font = '600 12px ' + _chartFont();
        c.fillStyle = ds._labelCol;
        c.fillText(ds.label + ' ' + _pct(ds._ret), pt.x + 6, pt.y + 4);
        c.restore();
      },
    };
    const yearsLbl = t(source === 'rent' ? 'vin_years_held_rent' : 'vin_years_held');
    S.modalChart = new Chart(canvas, {
      type: 'line',
      data: { datasets },
      plugins: [endLabels],
      options: {
        responsive: true, maintainAspectRatio: false, parsing: false,
        layout: { padding: { right: 72 } },
        interaction: { intersect: false, mode: 'nearest' },
        plugins: {
          legend: { display: false },
          tooltip: {
            filter: it => it.dataset._on,
            callbacks: {
              title: items => items.length ? items[0].parsed.x.toFixed(1) + ' ' + yearsLbl : '',
              label: c => ' ' + c.dataset.label + ': ' + _pct(c.parsed.y) + ' · ' + fmtInt(Math.round(c.raw.v)) + unit,
            },
          },
        },
        scales: {
          x: {
            type: 'linear', min: 0,
            title: { display: true, text: yearsLbl, font: { size: 11 }, color: '#64748b' },
            ticks: { font: { size: 11 }, stepSize: 1 },
            grid: { color: '#f1f5f9' },
          },
          y: {
            ticks: { font: { size: 11 }, callback: v => _pct(v) },
            grid: { color: c => c.tick.value === 0 ? '#475569' : '#f1f5f9', lineWidth: c => c.tick.value === 0 ? 1.5 : 1 },
          },
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
      const yCap = metric === 'avg' && source === 'sale' ? _robustMax(data, secondary && secondary.values) : undefined;
      if (useEc) _renderModalECharts({ el: echartsEl, labels, data, ma, ma50, ma200, median, color, m, secondary, est: cd.est, yCap });
      else _renderModalLwc({ el: lwcEl, dates: cd.fullLabels, data, ma50, ma200, median, color, m, secondary, cross, est: cd.est, yCap });
    }).catch(err => {
      target.innerHTML = `<div style="padding:20px;color:#dc2626;font-size:12px">${useEc ? 'ECharts' : 'Lightweight Charts'} failed to load.</div>`;
      console.error('Chart library load failed:', err);
    });
  }

  Object.assign(window._dp, {
    openChartModal, openVintagePathsModal
  });
})();
