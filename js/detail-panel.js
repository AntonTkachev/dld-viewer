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
        <div class="dp-stat"><div class="k">${t("sc_trans")}</div><div class="v">${fmtInt(s.n)}</div></div>
        <div class="dp-stat"><div class="k">${t("sc_volume")}</div><div class="v">${fmtAedDP(s.total)}</div></div>
        <div class="dp-stat"><div class="k">${t("sc_median_price")}</div><div class="v">${s.med ? fmtAedDP(s.med) : '—'}</div></div>
        <div class="dp-stat"><div class="k">${t("sc_price_psqm")}</div><div class="v">${s.med_ppsqm ? fmtInt(s.med_ppsqm)+' AED' : '—'}</div></div>
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
    const bu = a.by_rooms_unit || {};
    const rows = ROOM_BREAKDOWN
      .filter(k => bu[k] && bu[k].n > 0)
      .map(k => {
        const r = bu[k];
        return `<tr>
          <td>${roomBreakdownIcon(k)} ${roomLabel(k)}</td>
          <td class="num">${fmtInt(r.n)}</td>
          <td class="num">${r.med ? fmtAedDP(r.med) : '—'}</td>
          <td class="num">${r.ppsqm ? fmtInt(r.ppsqm) : '—'}</td>
        </tr>`;
      }).join('');
    if (!rows) return '';
    return `
      <div class="dp-section">
        <h3>${t('rooms_breakdown_title')}</h3>
        <table class="dp-table">
          <thead><tr>
            <th>${t('th_rooms_type')}</th>
            <th class="num">${t('th_count')}</th>
            <th class="num">${t('th_med_aed')}</th>
            <th class="num">${t('th_aed_psqm')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  // ─── Tab content ───────────────────────────────────────────────
  function renderBodySale(a) {
    const isDubai = S.isDubai;
    const proj_rows = (a.top_projects || []).map(p => {
      const areaCell = isDubai ? `<td>${_h(p.area || '—')}</td>` : '';
      return `<tr><td>${projName(p.proj)}</td>${areaCell}<td class="num">${fmtInt(p.n)}</td><td class="num">${fmtAedDP(p.med)}</td><td class="num">${fmtAedDP(p.total)}</td></tr>`;
    }).join('');
    const deal_rows = (a.top_deals || []).map(d => `<tr><td>${_h(d.d)}</td><td>${projName(d.proj)}</td><td>${_h(d.room)}</td><td class="num">${d.area ? fmtInt(d.area) : '—'}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-op dp-tag-op-${_h(d.op)}">${_h(d.op)}</span></td></tr>`).join('');
    const recent_rows = (a.recent || []).map(d => `<tr><td>${_h(d.d)}</td><td>${projName(d.proj)}</td><td>${_h(d.room)}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-g dp-tag-g-${_h(d.g)}">${_h(d.g)}</span></td></tr>`).join('');
    const proj_th_area = isDubai ? `<th>${t('th_district')}</th>` : '';

    return `
      <div class="period-chips" id="dp-period-chips">${renderPeriodChips()}</div>
      <div class="dp-stats" id="dp-stats-sale">${renderStatsSale(a)}</div>

      <div class="dp-section">
        <h3>${t("sp_section_timeline")}</h3>
        <div class="room-chips" id="dp-room-chips">${renderRoomChips(a)}</div>
        <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px">
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_count")}</div>
            <div class="dp-chart" style="height:180px"><canvas id="ch-timeline-count"></canvas></div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_volume")}</div>
            <div class="dp-chart" style="height:180px"><canvas id="ch-timeline-volume"></canvas></div>
          </div>
          <div>
            <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_avg")}</div>
            <div class="dp-chart" style="height:180px"><canvas id="ch-timeline-avg"></canvas></div>
          </div>
        </div>
      </div>

      ${renderRoomBreakdown(a)}

      <div class="dp-section">
        <h3>${t("sp_section_offplan")}</h3>
        <div class="dp-chart" style="height:160px"><canvas id="ch-offplan"></canvas></div>
      </div>

      <details class="dp-collapsible" data-tier="premium" open>
        <summary>${t("sp_section_top_projects")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_project")}</th>${proj_th_area}<th class="num">${t("th_n")}</th><th class="num">${t("th_median")}</th><th class="num">${t("th_volume")}</th></tr></thead><tbody>${proj_rows}</tbody></table>
        ${listLinkFooter('top_projects', 'Открыть полный список топ-проектов')}
      </details>

      <details class="dp-collapsible" data-tier="premium" open>
        <summary>${t("sp_section_top_deals")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("th_br")}</th><th class="num">${t("th_sqm")}</th><th class="num">${t("th_aed")}</th><th></th></tr></thead><tbody>${deal_rows}</tbody></table>
        ${listLinkFooter('top_deals', 'Открыть полный список крупных сделок')}
      </details>

      <details class="dp-collapsible" data-tier="premium" open>
        <summary>${t("sp_section_recent")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("th_br")}</th><th class="num">${t("th_aed")}</th><th>${t("th_type")}</th></tr></thead><tbody>${recent_rows}</tbody></table>
        ${listLinkFooter('recent', 'Открыть последние сделки')}
      </details>
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

      ${proj_rows ? `<details class="dp-collapsible" data-tier="premium" open>
        <summary>${t("rent_section_top_projects")}</summary>
        <table class="dp-table"><thead><tr><th>${t("th_project")}</th><th class="num">${t("th_n")}</th><th class="num">${t("rent_th_med")}</th></tr></thead><tbody>${proj_rows}</tbody></table>
        ${listLinkFooter('top_projects', 'Открыть полный список топ-проектов по аренде')}
      </details>` : ''}

      ${recent_rows ? `<details class="dp-collapsible" data-tier="premium" open>
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
  function renderTimelineCharts(a) {
    const series = periodSlice(roomTimelineFor(a));
    const labels = series.map(p => p.d.length === 10 ? p.d.slice(5) : p.d);
    const color  = ROOM_COLORS[S.roomFilter] || '#1d4ed8';
    const rgba = (hex, alpha) => {
      const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
      if (!m) return 'rgba(29,78,216,.12)';
      return `rgba(${parseInt(m[1],16)},${parseInt(m[2],16)},${parseInt(m[3],16)},${alpha})`;
    };
    const bg = rgba(color, .14);
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
    mkChart('ch-timeline-count',  series.map(p => p.n),                          v => v, v => v + ' ' + t('ch_count').toLowerCase());
    mkChart('ch-timeline-volume', series.map(p => p.vol||0),                     fmtAxisAed, fmtAedDP);
    mkChart('ch-timeline-avg',    series.map(p => p.n ? Math.round(p.vol/p.n) : 0), fmtAxisAed, fmtAedDP);
  }
  function renderOffplanChart(a) {
    const ctxO = document.getElementById('ch-offplan');
    if (!ctxO || !a.offplan) return;
    const labels = Object.keys(a.offplan);
    if (!labels.length) return;
    const data = labels.map(k => a.offplan[k]);
    const colors = labels.map(k => k==='Off-Plan' ? '#f0a020' : '#21918c');
    S.activeCharts.push(new Chart(ctxO, {
      type:'doughnut',
      data:{ labels, datasets:[{ data, backgroundColor:colors }]},
      options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom', labels:{boxWidth:10, font:{size:11}}}} }
    }));
  }
  function renderSaleCharts(a) {
    renderTimelineCharts(a);
    try { renderOffplanChart(a); } catch(e) { console.error('offplan chart:', e); }
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
