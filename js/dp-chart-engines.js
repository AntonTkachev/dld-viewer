// District detail panel: lazy-loaded fullscreen chart engines (Lightweight Charts, ECharts) and the measure tool.
(function () {
  const {
    S, _h, fmtInt, rgba, t
  } = window._dp;

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

  function _renderModalLwc({ el, dates, data, ma50, ma200, median, color, m, secondary, cross, est, yCap }) {
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
    const fmtAxis = v => { if (v < 0) return ''; const r = m.fmtY(Math.round(v)); return typeof r === 'number' ? fmtInt(r) : r; };
    const pf = { type: 'custom', minMove: 1, formatter: fmtAxis };
    const autoscaleInfoProvider = orig => {
      const r = orig();
      if (r && r.priceRange && yCap) r.priceRange.maxValue = Math.min(r.priceRange.maxValue, yCap);
      return r;
    };
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
    const maOpts = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, priceFormat: pf, autoscaleInfoProvider };
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
      priceFormat: pf, priceLineVisible: false, autoscaleInfoProvider,
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

  function _renderModalECharts({ el, labels, data, ma, ma50, ma200, median, color, m, secondary, est, yCap }) {
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
        type: 'value', min: 0, max: yCap,
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

  Object.assign(window._dp, {
    _ensureECharts, _ensureLwc, _renderModalECharts, _renderModalLwc
  });
})();
