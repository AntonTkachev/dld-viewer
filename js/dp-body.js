// District detail panel: sale/rent body markup and the timeline charts.
(function () {
  const {
    ROOM_COLORS, S, _areaFill, _estNote, _h, _lastValueTag, _projectedPoint, _robustMax,
    _trimLeadOutliers, _xAxis, _yAxis, avgPrice, fmtAedDP, fmtAxisAed, fmtInt, periodSlice, projName,
    renderPeriodChips, renderPeriodChipsRent, renderRoomBreakdown, renderRoomChips, renderStatsRent,
    renderStatsSale, renderVintageSection, roomTimelineFor, t, tVal
  } = window._dp;

  function renderBodySale(a) {
    return `
      <div class="dp-toolbar">
        <div class="period-chips" id="dp-period-chips">${renderPeriodChips()}</div>
        <div class="room-chips" id="dp-room-chips">${renderRoomChips(a)}</div>
      </div>
      <div class="dp-stats" id="dp-stats-sale">${renderStatsSale(a)}</div>

      <div class="dp-section">
        <h3>${t("sp_section_timeline")}</h3>
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
        ${listLinkFooter('top_projects', t('open_full_top_projects'))}
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
      <tr><td>${_h(tVal('rent_ptype_map', k))}</td><td class="num">${fmtInt(v.n)}</td><td class="num">${fmtAedDP(v.med)}</td><td class="num">${fmtInt(v.med_ppsqm)}</td></tr>`).join('');
    const proj_rows = (r.top_projects||[]).map(p => `<tr><td>${projName(p.proj)}</td><td class="num">${fmtInt(p.n)}</td><td class="num">${fmtAedDP(p.med)}</td></tr>`).join('');
    const recent_rows = (r.recent||[]).map(d => {
      const vTag = d.v === 'N' ? t('rent_v_new') : t('rent_v_renew');
      return `<tr><td>${_h(d.d)}</td><td>${projName(d.proj)}</td><td>${_h(tVal('rent_ptype_map', d.sub))}</td><td class="num">${d.sqm ? fmtInt(d.sqm) : '—'}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-g dp-tag-g-${d.v==='N'?'O':'R'}">${_h(vTag)}</span></td></tr>`;
    }).join('');

    const hasRooms = !!(r.by_rooms_unit && Object.keys(r.by_rooms_unit).length);

    return `
      <div class="dp-toolbar">
        <div class="period-chips" id="dp-period-chips-rent">${renderPeriodChipsRent()}</div>
        ${hasRooms ? `<div class="room-chips" id="dp-room-chips-rent">${renderRoomChips(r)}</div>` : ''}
      </div>
      <div class="dp-stats" id="dp-stats-rent">${renderStatsRent(r)}</div>

      <div class="dp-section">
        <h3>${t("rent_section_timeline")}</h3>
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
          <div class="dp-donut-card" id="dp-rent-tenant-card">
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

  function renderTimelineCharts(a) {
    const raw = _trimLeadOutliers(roomTimelineFor(a));
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
      const estIdx = est ? est.idx : -1;
      const datasets = [];
      if (secondary) {
        // Deal-count bars on a hidden axis stretched so they sit in the bottom ~40%
        const secMax = Math.max(...secondary.values.filter(Number.isFinite), 1) * 2.4;
        datasets.push({
          type:'bar', label: secondary.label, data: secondary.values, _secMax: secMax,
          backgroundColor: c => c.dataIndex === estIdx ? 'rgba(148,163,184,0.15)' : 'rgba(148,163,184,0.38)', borderWidth: 0,
          borderRadius: 1.5, yAxisID: 'y1', barPercentage: .8, categoryPercentage: .9, order: 2,
        });
      }
      datasets.push({ label, data, borderColor:color, backgroundColor:_areaFill(color), borderWidth: 2, tension:.25, fill:true, order: 1,
        _tag: { fmt: v => fmtAxisAed(Math.round(v)), color },
        pointRadius: c => c.dataIndex === estIdx ? 3 : 0,
        pointHoverRadius: 4, pointHoverBorderColor: '#fff', pointHoverBorderWidth: 2, pointHoverBackgroundColor: color,
        pointBackgroundColor: '#fff', pointBorderColor: color,
        spanGaps: true,
        segment: { borderDash: c => c.p1DataIndex === estIdx ? [4, 3] : undefined } });
      const scales = {
        y: _yAxis(fmtY, { beginAtZero: true, grace: '12%', max: secondary ? _robustMax(data, secondary.values) : undefined }),
        x: _xAxis(),
      };
      if (secondary) scales.y1 = { display: false, min: 0, max: datasets[0]._secMax };
      const ch = new Chart(ctx, {
        type:'line',
        data:{ labels, datasets },
        plugins: [_lastValueTag],
        options:{
          responsive:true, maintainAspectRatio:false,
          interaction:{intersect:false, mode:'index'},
          plugins:{
            legend:{ display: false },
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

  Object.assign(window._dp, {
    renderBody, renderTimelineCharts
  });
})();
