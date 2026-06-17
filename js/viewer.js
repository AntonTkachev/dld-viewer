// Wire buttons (deferred until DOM exists)
setTimeout(() => {
  // Lang buttons
  document.querySelectorAll('#mp-lang-list .lang-btn').forEach(b => {
    b.addEventListener('click', () => applyLang(b.dataset.lang));
  });
  // Middle-panel item toggles
  document.querySelectorAll('#mp-panel .mp-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const item = btn.parentElement;
      const wasOpen = item.classList.contains('open');
      document.querySelectorAll('#mp-panel .mp-item').forEach(it => it.classList.remove('open'));
      if (!wasOpen) {
        item.classList.add('open');
        if (item.id === 'mp-search') {
          const inp = document.getElementById('search-input');
          if (inp) { inp.value = ''; setTimeout(()=>inp.focus(), 0); _renderSearchResults(''); }
        }
        if (item.id === 'mp-mask') {
          if (typeof renderMaskList === 'function') renderMaskList();
        }
      }
    });
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('#mp-panel')) {
      document.querySelectorAll('#mp-panel .mp-item').forEach(it => it.classList.remove('open'));
    }
  });
  // Levels
  document.querySelectorAll('#mp-level-list .ls-btn').forEach(b => {
    b.addEventListener('click', () => {
      const lvl = parseInt(b.dataset.minLevel, 10);
      if (lvl !== minLevel) {
        minLevel = lvl;
        document.querySelectorAll('#mp-level-list .ls-btn').forEach(x => {
          x.classList.toggle('active', parseInt(x.dataset.minLevel,10) === minLevel);
        });
        const cur = document.getElementById('mp-level-current');
        if (cur) cur.textContent = b.textContent;
        if (typeof renderChoro === 'function') renderChoro();
      }
      document.getElementById('mp-level').classList.remove('open');
    });
  });
  // Search input
  const searchInp = document.getElementById('search-input');
  if (searchInp) {
    searchInp.placeholder = t('search_placeholder');
    searchInp.addEventListener('input', e => _renderSearchResults(e.target.value));
    searchInp.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        document.getElementById('mp-search').classList.remove('open');
        return;
      }
      if (e.key === 'Enter') {
        const first = document.querySelector('#search-results .sr-item');
        if (first) first.click();
      }
    });
  }
  // Apply current lang to populate all panel labels on first paint
  applyLang(currentLang);
}, 0);


// ===================== DRILL-DOWN PANEL =====================
var activeCharts = [];
var timelineCharts = [];
var currentRoomFilter = 'all';
var currentPeriod = 'all';   // '1y' | '3y' | '5y' | '10y' | 'all'
var modalChart = null;
const PERIODS = [
  { k: '1y',  months: 12  },
  { k: '3y',  months: 36  },
  { k: '5y',  months: 60  },
  { k: '10y', months: 120 },
  { k: 'all', months: null },
];
const ROOM_ORDER = ['all','studio','1br','2br','3br','4br+','villa','other'];
const ROOM_COLORS = { all:'#1d4ed8', studio:'#9ca3af', '1br':'#60a5fa', '2br':'#3b82f6', '3br':'#1d4ed8', '4br+':'#1e3a8a', villa:'#d97706', other:'#a78bfa' };
function roomLabel(k){
  if (k==='all')    return t('room_chip_all');
  if (k==='villa')  return t('ru_villa');
  if (k==='other')  return t('ru_other');
  return {studio:'Studio','1br':'1BR','2br':'2BR','3br':'3BR','4br+':'4BR+'}[k];
}
function destroyCharts() { for (const c of activeCharts) c.destroy(); activeCharts = []; timelineCharts = []; }
function destroyTimelineCharts() {
  for (const c of timelineCharts) {
    c.destroy();
    const i = activeCharts.indexOf(c);
    if (i>=0) activeCharts.splice(i,1);
  }
  timelineCharts = [];
}

function fmtAedDP(v) {
  if (!v) return '—';
  if (v >= 1e9) return (v/1e9).toFixed(2) + ' ' + t('abbr_b');
  if (v >= 1e6) return (v/1e6).toFixed(2) + ' ' + t('abbr_m');
  if (v >= 1e3) return (v/1e3).toFixed(0) + t('abbr_k');
  return v.toLocaleString();
}
function fmtInt(v) { return (v||0).toLocaleString('ru-RU'); }

function closePanel() {
  const panel = document.getElementById('detail-panel');
  panel.classList.remove('open');
  panel.classList.remove('fullscreen');
  document.getElementById('dp-fs-toggle').textContent = '◀';
  document.getElementById('map').classList.remove('with-panel-open');
  document.getElementById('map').classList.add('with-panel-closed');
  setTimeout(() => map.invalidateSize(), 260);
  destroyCharts();
}
document.getElementById('dp-close').addEventListener('click', closePanel);

document.getElementById('dp-fs-toggle').addEventListener('click', () => {
  const panel = document.getElementById('detail-panel');
  if (!panel.classList.contains('open')) {
    // Panel closed — open Dubai-wide overview
    openDubai();
    return;
  }
  const mapEl = document.getElementById('map');
  const goingFs = !panel.classList.contains('fullscreen');
  panel.classList.toggle('fullscreen', goingFs);
  document.getElementById('dp-fs-toggle').textContent = goingFs ? '▶' : '◀';
  if (goingFs) {
    mapEl.classList.remove('with-panel-open');
  } else {
    mapEl.classList.add('with-panel-open');
  }
  setTimeout(() => map.invalidateSize(), 260);
});

// Tab switch (sale / rent) — delegated on #dp-body
document.getElementById('dp-body').addEventListener('click', e => {
  const btn = e.target.closest('.dp-tab');
  if (!btn) return;
  const which = btn.dataset.dpTab;
  document.querySelectorAll('#dp-body .dp-tab').forEach(b => b.classList.toggle('active', b === btn));
  document.querySelectorAll('#dp-body .dp-tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === 'dp-pane-' + which);
  });
  if (which === 'rent') {
    const titleEl = document.getElementById('dp-title');
    const key = titleEl && titleEl.dataset.key;
    if (key) {
      const r = RENT_AGGREGATES[key];
      if (r) {
        destroyRentCharts();
        renderRentCharts(r);
      }
    }
  }
});

window.openDistrictByKey = function(key, fullscreen) {
  const feat = GEOJSON.features.find(f => f.properties.real_area_key === key);
  if (feat) openDistrict(feat.properties, {fullscreen: !!fullscreen});
  else alert('No feature for key: ' + key);
};

window.openDubai = function(opts) {
  const fullscreen = !!(opts && opts.fullscreen);
  const a = AGGREGATES['__dubai__'];
  if (!a) { alert(t('alert_not_found')); return; }
  destroyCharts();
  const panel = document.getElementById('detail-panel');
  const mapEl = document.getElementById('map');
  const titleEl = document.getElementById('dp-title');
  titleEl.textContent = t('dp_dubai_title');
  titleEl.dataset.key = '__dubai__';
  document.getElementById('dp-body').innerHTML = renderBody(a, {__dubai__: true});
  panel.classList.add('open');
  panel.classList.toggle('fullscreen', fullscreen);
  document.getElementById('dp-fs-toggle').textContent = fullscreen ? '▶' : '◀';
  mapEl.classList.remove('with-panel-closed');
  if (fullscreen) mapEl.classList.remove('with-panel-open');
  else mapEl.classList.add('with-panel-open');
  setTimeout(() => map.invalidateSize(), 260);
  setTimeout(() => renderCharts(a), 50);
};

function openDistrict(props, opts) {
  const fullscreen = !!(opts && opts.fullscreen);
  const key = props.real_area_key;
  if (!key) {
    // No data for this district — silently ignore the click instead of alerting
    return;
  }
  const a = AGGREGATES[key];
  if (!a) { alert(t('alert_not_found')); return; }

  destroyCharts();
  const panel = document.getElementById('detail-panel');
  const mapEl = document.getElementById('map');
  const titleEl = document.getElementById('dp-title'); titleEl.textContent = a.name; titleEl.dataset.key = key;
  document.getElementById('dp-body').innerHTML = renderBody(a, props);
  panel.classList.add('open');
  panel.classList.toggle('fullscreen', fullscreen);
  document.getElementById('dp-fs-toggle').textContent = fullscreen ? '▶' : '◀';
  mapEl.classList.remove('with-panel-closed');
  if (fullscreen) {
    mapEl.classList.remove('with-panel-open');
  } else {
    mapEl.classList.add('with-panel-open');
  }
  setTimeout(() => map.invalidateSize(), 260);

  // Render charts after DOM injection
  setTimeout(() => renderCharts(a), 50);
}

function renderBody(a, props) {
  const rentKey = props.__dubai__ ? '__dubai__' : props.real_area_key;
  const rentA = rentKey ? RENT_AGGREGATES[rentKey] : null;
  const rentCount = rentA ? rentA.n : 0;
  return `
    <div class="dp-tabs">
      <button class="dp-tab active" data-dp-tab="sale" type="button">${t('tab_sale')}<span class="tab-n">${fmtInt(a.n)}</span></button>
      <button class="dp-tab" data-dp-tab="rent" type="button">${t('tab_rent')}<span class="tab-n">${fmtInt(rentCount)}</span></button>
    </div>
    <div class="dp-tab-pane active" id="dp-pane-sale">${renderBodySale(a, props)}</div>
    <div class="dp-tab-pane" id="dp-pane-rent">${renderBodyRent(rentA, props)}</div>
  `;
}

function projName(p) { return p || t('not_specified'); }

// Row in the room-median breakdown.
// 'all' is excluded — it duplicates the headline 4-card stats.
const ROOM_BREAKDOWN = ['studio','1br','2br','3br','4br+','villa','other'];
function roomBreakdownIcon(k) {
  return (k === 'villa') ? '🏡' : (k === 'other') ? '·' : '🏢';
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

function renderBodySale(a, props) {
  const isDubai = !!props.__dubai__;
  const proj_rows = a.top_projects.map(p => {
    const areaCell = isDubai ? `<td>${p.area || '—'}</td>` : '';
    return `<tr><td>${projName(p.proj)}</td>${areaCell}<td class="num">${fmtInt(p.n)}</td><td class="num">${fmtAedDP(p.med)}</td><td class="num">${fmtAedDP(p.total)}</td></tr>`;
  }).join('');
  const deal_rows = a.top_deals.map(d => `<tr><td>${d.d}</td><td>${projName(d.proj)}</td><td>${d.room}</td><td class="num">${d.area ? fmtInt(d.area) : '—'}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-op dp-tag-op-${d.op}">${d.op}</span></td></tr>`).join('');
  const recent_rows = a.recent.map(d => `<tr><td>${d.d}</td><td>${projName(d.proj)}</td><td>${d.room}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-g dp-tag-g-${d.g}">${d.g}</span></td></tr>`).join('');

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
          <div class="dp-chart" style="height:180px"><button class="chart-expand-btn" title="${t('chart_expand')}" onclick="expandChart('ch-timeline-count', '${t('sp_subsection_count')}')">⛶</button><canvas id="ch-timeline-count"></canvas></div>
        </div>
        <div>
          <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_volume")}</div>
          <div class="dp-chart" style="height:180px"><button class="chart-expand-btn" title="${t('chart_expand')}" onclick="expandChart('ch-timeline-volume', '${t('sp_subsection_volume')}')">⛶</button><canvas id="ch-timeline-volume"></canvas></div>
        </div>
        <div>
          <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_avg")}</div>
          <div class="dp-chart" style="height:180px"><button class="chart-expand-btn" title="${t('chart_expand')}" onclick="expandChart('ch-timeline-avg', '${t('sp_subsection_avg')}')">⛶</button><canvas id="ch-timeline-avg"></canvas></div>
        </div>
      </div>
    </div>

    ${renderRoomBreakdown(a)}

    <div class="dp-section">
      <h3>${t("sp_section_offplan")}</h3>
      <div class="dp-chart" style="height:160px"><button class="chart-expand-btn" title="${t('chart_expand')}" onclick="expandChart('ch-offplan', '${t('sp_section_offplan')}')">⛶</button><canvas id="ch-offplan"></canvas></div>
    </div>

    <details class="dp-collapsible">
      <summary>${t("sp_section_top_projects")}</summary>
      <table class="dp-table"><thead><tr><th>${t("th_project")}</th>${proj_th_area}<th class="num">${t("th_n")}</th><th class="num">${t("th_median")}</th><th class="num">${t("th_volume")}</th></tr></thead><tbody>${proj_rows}</tbody></table>
    </details>

    <details class="dp-collapsible">
      <summary>${t("sp_section_top_deals")}</summary>
      <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("th_br")}</th><th class="num">${t("th_sqm")}</th><th class="num">${t("th_aed")}</th><th></th></tr></thead><tbody>${deal_rows}</tbody></table>
    </details>

    <details class="dp-collapsible">
      <summary>${t("sp_section_recent")}</summary>
      <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("th_br")}</th><th class="num">${t("th_aed")}</th><th>${t("th_type")}</th></tr></thead><tbody>${recent_rows}</tbody></table>
    </details>
  `;
}

function renderBodyRent(r, props) {
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
    return `<tr><td>${d.d}</td><td>${projName(d.proj)}</td><td>${d.sub}</td><td class="num">${d.sqm ? fmtInt(d.sqm) : '—'}</td><td class="num">${fmtAedDP(d.val)}</td><td><span class="dp-tag-g dp-tag-g-${d.v==='N'?'O':'R'}">${vTag}</span></td></tr>`;
  }).join('');

  return `
    <div class="period-chips" id="dp-period-chips-rent">${renderPeriodChipsRent()}</div>
    <div class="dp-stats" id="dp-stats-rent">${renderStatsRent(r)}</div>

    <div class="dp-section">
      <h3>${t("rent_section_timeline")}</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div>
          <div style="font-size:11px;color:#666;margin-bottom:2px">${t("sp_subsection_count")}</div>
          <div class="dp-chart" style="height:180px"><button class="chart-expand-btn" title="${t('chart_expand')}" onclick="expandChart('ch-rent-count', '${t('sp_subsection_count')}')">⛶</button><canvas id="ch-rent-count"></canvas></div>
        </div>
        <div>
          <div style="font-size:11px;color:#666;margin-bottom:2px">${t("rent_th_med")}</div>
          <div class="dp-chart" style="height:180px"><button class="chart-expand-btn" title="${t('chart_expand')}" onclick="expandChart('ch-rent-med', '${t('rent_th_med')}')">⛶</button><canvas id="ch-rent-med"></canvas></div>
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

    ${proj_rows ? `<details class="dp-collapsible">
      <summary>${t("rent_section_top_projects")}</summary>
      <table class="dp-table"><thead><tr><th>${t("th_project")}</th><th class="num">${t("th_n")}</th><th class="num">${t("rent_th_med")}</th></tr></thead><tbody>${proj_rows}</tbody></table>
    </details>` : ''}

    ${recent_rows ? `<details class="dp-collapsible">
      <summary>${t("rent_section_recent")}</summary>
      <table class="dp-table"><thead><tr><th>${t("th_date")}</th><th>${t("th_project")}</th><th>${t("rent_th_subtype")}</th><th class="num">${t("th_sqm")}</th><th class="num">${t("th_aed")}</th><th>${t("rent_th_version")}</th></tr></thead><tbody>${recent_rows}</tbody></table>
    </details>` : ''}
  `;
}

function fmtAxisAed(v) {
  if (v >= 1e9) return (v/1e9).toFixed(1) + 'B';
  if (v >= 1e6) return (v/1e6).toFixed(1) + 'M';
  if (v >= 1e3) return (v/1e3).toFixed(0) + 'K';
  return v;
}

// ─── Period helpers ─────────────────────────────────────────────
function renderPeriodChips() {
  return `<span class="pc-lbl">${t('sp_period_label')}:</span>` + PERIODS.map(p => {
    const cls = p.k === currentPeriod ? ' active' : '';
    return `<button class="period-chip${cls}" type="button" onclick="setPeriod('${p.k}')">${t('period_'+p.k)}</button>`;
  }).join('');
}

// Slice a monthly timeline ({d:"YYYY-MM", ...}) to the active period.
// Finite periods anchor at *today* and ignore forward-dated months.
function periodSlice(series) {
  if (!series.length) return series;
  if (currentPeriod === 'all') return series;
  const today = new Date();
  const todayMonth = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`;
  const upto = series.filter(p => p.d <= todayMonth);
  if (!upto.length) return [];
  const months = PERIODS.find(p => p.k === currentPeriod).months;
  return upto.slice(-months);
}

// Pick base timeline by room filter (returns full series — period applied separately).
function roomTimelineFor(a) {
  if (currentRoomFilter === 'all') return a.timeline || [];
  return (a.timeline_by_rooms && a.timeline_by_rooms[currentRoomFilter]) || [];
}

// Median of a list of numbers (ignores zero / falsy).
function medOf(arr) {
  const v = arr.filter(x => x).sort((a,b) => a-b);
  if (!v.length) return 0;
  return v[Math.floor(v.length/2)];
}

// Roll up stats from monthly timeline rows in [from, to] window.
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

window.setPeriod = function(p) {
  if (currentPeriod === p) return;
  currentPeriod = p;
  const titleEl = document.getElementById('dp-title');
  const key = titleEl && titleEl.dataset.key;
  if (!key) return;
  // Sale tab refresh
  const a = AGGREGATES[key];
  if (a) {
    const pcEl = document.getElementById('dp-period-chips');
    if (pcEl) pcEl.innerHTML = renderPeriodChips();
    const statsEl = document.getElementById('dp-stats-sale');
    if (statsEl) statsEl.innerHTML = renderStatsSale(a);
    destroyTimelineCharts();
    renderTimelineCharts(a);
  }
  // Rent tab refresh (mirrors period)
  const r = RENT_AGGREGATES[key];
  if (r) {
    const pcRentEl = document.getElementById('dp-period-chips-rent');
    if (pcRentEl) pcRentEl.innerHTML = renderPeriodChipsRent();
    const statsRentEl = document.getElementById('dp-stats-rent');
    if (statsRentEl) statsRentEl.innerHTML = renderStatsRent(r);
    // Re-render rent charts only if the rent tab is currently visible (canvases exist + in DOM)
    if (document.getElementById('ch-rent-count')) {
      destroyRentCharts();
      renderRentCharts(r);
    }
  }
};

// ─── Chart expand modal ────────────────────────────────────────
window.expandChart = function(canvasId, title) {
  const src = activeCharts.find(c => c.canvas && c.canvas.id === canvasId);
  if (!src) return;
  const modal = document.getElementById('chart-modal');
  document.getElementById('chart-modal-title').textContent = title || '';
  const canvas = document.getElementById('chart-modal-canvas');
  if (modalChart) { modalChart.destroy(); modalChart = null; }
  modal.classList.add('open');
  // Clone config (deep) so updates don't fight the source chart
  const cfg = JSON.parse(JSON.stringify({
    type: src.config.type,
    data: src.config.data,
    options: src.config.options || {},
  }));
  // Restore callbacks lost via JSON serialization
  cfg.options.responsive = true;
  cfg.options.maintainAspectRatio = false;
  cfg.options.plugins = cfg.options.plugins || {};
  cfg.options.plugins.legend = { display: false };
  if (cfg.options.scales && cfg.options.scales.y && cfg.options.scales.y.ticks) {
    cfg.options.scales.y.ticks.callback = fmtAxisAed;
  }
  modalChart = new Chart(canvas, cfg);
};

window.closeChartModal = function() {
  const modal = document.getElementById('chart-modal');
  modal.classList.remove('open');
  if (modalChart) { modalChart.destroy(); modalChart = null; }
};

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeChartModal();
});

// ─── Rent panel helpers ────────────────────────────────────────
var rentTimelineCharts = [];

function destroyRentCharts() {
  for (const c of rentTimelineCharts) {
    c.destroy();
    const i = activeCharts.indexOf(c);
    if (i >= 0) activeCharts.splice(i, 1);
  }
  rentTimelineCharts = [];
}

function renderPeriodChipsRent() {
  return `<span class="pc-lbl">${t('sp_period_label')}:</span>` + PERIODS.map(p => {
    const cls = p.k === currentPeriod ? ' active' : '';
    return `<button class="period-chip${cls}" type="button" onclick="setPeriod('${p.k}')">${t('period_'+p.k)}</button>`;
  }).join('');
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
  const newRatio = r.n ? Math.round(r.new / r.n * 100) : 0;
  const renRatio = 100 - newRatio;
  return `
      <div class="dp-stat"><div class="k">${t("rent_sc_contracts")}</div><div class="v">${fmtInt(s.n)}</div></div>
      <div class="dp-stat"><div class="k">${t("rent_sc_med_annual")}</div><div class="v">${s.med_annual ? fmtAedDP(s.med_annual) : '—'}</div></div>
      <div class="dp-stat"><div class="k">${t("rent_sc_ppsqm")}</div><div class="v">${s.med_ppsqm ? fmtInt(s.med_ppsqm)+' AED' : '—'}</div></div>
      <div class="dp-stat"><div class="k">New / Renew</div><div class="v" style="font-size:13px">${newRatio}% / ${renRatio}%</div></div>
  `;
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
    activeCharts.push(ch);
    rentTimelineCharts.push(ch);
  };

  mkChart('ch-rent-count', series.map(p => p.n), v => v,   v => v + ' ' + t('ch_count').toLowerCase());
  mkChart('ch-rent-med',   series.map(p => p.med || 0), fmtAxisAed, fmtAedDP);
}

function renderRoomChips(a) {
  const tbr = a.timeline_by_rooms || {};
  const bu  = a.by_rooms_unit || {};
  return ROOM_ORDER.map(k => {
    const n = k === 'all' ? a.n : (bu[k] ? bu[k].n : 0);
    const disabled = k !== 'all' && (!tbr[k] || !tbr[k].length);
    if (disabled) return '';
    const active = (k === currentRoomFilter) ? ' active' : '';
    const color  = ROOM_COLORS[k];
    const style  = (k === currentRoomFilter) ? ` style="background:${color};border-color:${color};color:#fff"` : '';
    return `<button class="room-chip${active}" data-room="${k}" onclick="setRoomFilter('${k}')"${style}>${roomLabel(k)}<span class="chip-n">${fmtInt(n)}</span></button>`;
  }).join('');
}

window.setRoomFilter = function(room) {
  if (currentRoomFilter === room) return;
  currentRoomFilter = room;
  const titleEl = document.getElementById('dp-title');
  const key = titleEl && titleEl.dataset.key;
  if (!key) return;
  const a = AGGREGATES[key];
  if (!a) return;
  document.getElementById('dp-room-chips').innerHTML = renderRoomChips(a);
  const statsEl = document.getElementById('dp-stats-sale');
  if (statsEl) statsEl.innerHTML = renderStatsSale(a);
  destroyTimelineCharts();
  renderTimelineCharts(a);
};

function pickTimelineSeries(a) {
  return periodSlice(roomTimelineFor(a));
}

function renderTimelineCharts(a) {
  const series = pickTimelineSeries(a);
  // Daily ("YYYY-MM-DD" → "MM-DD") or monthly ("YYYY-MM" → as-is)
  const labels = series.map(p => p.d.length === 10 ? p.d.slice(5) : p.d);
  const color  = ROOM_COLORS[currentRoomFilter] || '#1d4ed8';
  // hex → rgba(_,_,_,.14)
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
    activeCharts.push(ch);
    timelineCharts.push(ch);
  };

  mkChart('ch-timeline-count',  series.map(p => p.n),                   v => v, v => v + ' ' + t('ch_count').toLowerCase());
  mkChart('ch-timeline-volume', series.map(p => p.vol||0),              fmtAxisAed, fmtAedDP);
  mkChart('ch-timeline-avg',    series.map(p => p.n ? Math.round(p.vol/p.n) : 0), fmtAxisAed, fmtAedDP);
}

function renderCharts(a) {
  currentRoomFilter = 'all';
  currentPeriod = 'all';
  const chipsEl = document.getElementById('dp-room-chips');
  if (chipsEl) chipsEl.innerHTML = renderRoomChips(a);
  const periodEl = document.getElementById('dp-period-chips');
  if (periodEl) periodEl.innerHTML = renderPeriodChips();
  const statsEl = document.getElementById('dp-stats-sale');
  if (statsEl) statsEl.innerHTML = renderStatsSale(a);
  renderTimelineCharts(a);
  // Rooms breakdown — count + volume
  try {
    const bu = a.by_rooms_unit || {};
    const order = ['studio','1br','2br','3br','4br+','villa','other'];
    const labelFor = k => ({
      studio:'Studio', '1br':'1BR', '2br':'2BR', '3br':'3BR',
      '4br+':'4BR+', villa:t('ru_villa'), other:t('ru_other')
    })[k];
    const colorFor = k => ({
      studio:'#9ca3af', '1br':'#60a5fa', '2br':'#3b82f6', '3br':'#1d4ed8',
      '4br+':'#1e3a8a', villa:'#d97706', other:'#a78bfa'
    })[k];
    const keys = order.filter(k => bu[k] && (bu[k].n > 0));
    const labels = keys.map(labelFor);
    const colors = keys.map(colorFor);

    const ctxRC = document.getElementById('ch-rooms-count');
    if (ctxRC && keys.length) {
      activeCharts.push(new Chart(ctxRC, {
        type:'bar',
        data:{ labels, datasets:[{ data: keys.map(k => bu[k].n), backgroundColor: colors }]},
        options:{
          indexAxis:'y', responsive:true, maintainAspectRatio:false,
          plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>` ${c.parsed.x} ${t('ch_count').toLowerCase()}`}}},
          scales:{
            x:{ticks:{font:{size:10}}, beginAtZero:true},
            y:{ticks:{font:{size:11}}}
          }
        }
      }));
    }
    const ctxRV = document.getElementById('ch-rooms-volume');
    if (ctxRV && keys.length) {
      activeCharts.push(new Chart(ctxRV, {
        type:'bar',
        data:{ labels, datasets:[{ data: keys.map(k => bu[k].vol), backgroundColor: colors }]},
        options:{
          indexAxis:'y', responsive:true, maintainAspectRatio:false,
          plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>` ${fmtAedDP(c.parsed.x)}`}}},
          scales:{
            x:{ticks:{font:{size:10}, callback:fmtAxisAed}, beginAtZero:true},
            y:{ticks:{font:{size:11}}}
          }
        }
      }));
    }
  } catch(e) { console.error('rooms charts:', e); }

  // Off-plan donut
  try {
    const ctxO = document.getElementById('ch-offplan');
    if (ctxO && a.offplan) {
      const labels = Object.keys(a.offplan);
      const data = labels.map(k => a.offplan[k]);
      const colors = labels.map(k => k==='Off-Plan' ? '#f0a020' : '#21918c');
      if (labels.length) {
        activeCharts.push(new Chart(ctxO, {
          type:'doughnut',
          data:{ labels, datasets:[{ data, backgroundColor:colors }]},
          options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{position:'bottom', labels:{boxWidth:10, font:{size:11}}}} }
        }));
      }
    }
  } catch(e) { console.error('offplan chart:', e); }
}


// ===================== MAP =====================
// SVG pattern defs for "no DLD data" hatched fill. Injected into the document
// (not Leaflet's overlay <svg>) so url(#nodata-hatch) resolves the moment any
// path is rendered, regardless of pane creation order.
document.body.insertAdjacentHTML('beforeend',
  '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
  + '<defs><pattern id="nodata-hatch" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">'
  + '<line x1="0" y1="0" x2="0" y2="8" stroke="#94a3b8" stroke-width="1.4"/>'
  + '</pattern></defs></svg>');

const map = L.map('map').setView([25.12, 55.25], 10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
  maxZoom: 19,
}).addTo(map);

// ===================== CHOROPLETH =====================
const RAMP = ['#440154','#3b528b','#21918c','#5ec962','#fde725'];
const METRIC_FMT = {
  count: v => v.toLocaleString('ru-RU'),
  total_aed: v => v >= 1e9 ? (v/1e9).toFixed(2)+' '+t('abbr_b') : v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString(),
  median_price_aed: v => v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString(),
  avg_sqm: v => v.toLocaleString('ru-RU',{maximumFractionDigits:1}),
};
function qBreaks(vs,n){const s=vs.slice().sort((a,b)=>a-b),b=[];for(let i=1;i<n;i++)b.push(s[Math.floor(s.length*i/n)]);return b}
function lBreaks(vs,n){const lo=Math.min(...vs),hi=Math.max(...vs),b=[];for(let i=1;i<n;i++)b.push(lo+(hi-lo)*i/n);return b}
function logBreaks(vs,n){const p=vs.filter(v=>v>0);if(!p.length)return Array(n-1).fill(0);const lo=Math.log(Math.min(...p)),hi=Math.log(Math.max(...p)),b=[];for(let i=1;i<n;i++)b.push(Math.exp(lo+(hi-lo)*i/n));return b}
function classify(v,b){for(let i=0;i<b.length;i++)if(v<=b[i])return i;return b.length}

// Manual parent-fallback for polygons that have a DLD area_id but no CSV row.
// DLD records deals from these sub-communities under their parent community.
const PARENT_OVERRIDES = {
  // exact name equivalence (different transliteration / modern DLD name)
  'The Gardens':                          { parent_key: 'discovery gardens',  parent_name: 'Discovery Gardens' },
  'Jebel Ali Village':                    { parent_key: 'jabal ali first',    parent_name: 'Jabal Ali First' },
  'Al Jaddaf':                            { parent_key: 'sama al jadaf',      parent_name: 'Sama Al Jadaf' },
  'Nakhlat Jabal Ali':                    { parent_key: 'palm jabal ali',     parent_name: 'Palm Jabal Ali' },
  'Port Rashid':                          { parent_key: 'mina rashid',        parent_name: 'Mina Rashid' },
  'Al Ruwayyah 1':                        { parent_key: 'al rowaiyah first',  parent_name: 'Al Rowaiyah First' },
  'Al Ruwayyah 2':                        { parent_key: 'al rowaiyah first',  parent_name: 'Al Rowaiyah First' },
  'Al Ruwayyah 3':                        { parent_key: 'al rowaiyah first',  parent_name: 'Al Rowaiyah First' },
  // shared DLD code / geographic containment
  // Al Barsha South 5 polygon sits over the JVT geographic area (west of Al Khail);
  // the big "Jumeirah Village Circle" polygon already covers actual JVC on the east.
  'Al Barsha South 5':                    { parent_key: 'jumeirah village triangle', parent_name: 'Jumeirah Village Triangle' },
  'Wadi Al Safa 6':                       { parent_key: 'arabian ranches i',  parent_name: 'Arabian Ranches I' },
  'Dubai International Financial Centre': { parent_key: 'zaabeel second',     parent_name: 'Zaabeel Second' },
  'Emaar Beachfront':                     { parent_key: 'dubai harbour',      parent_name: 'Dubai Harbour' },
  // DLD-name equivalents (OSM marketing name → DLD official community)
  'Downtown Dubai':                       { parent_key: 'burj khalifa',       parent_name: 'Burj Khalifa' },
  'Expo City Dubai':                      { parent_key: 'madinat al mataar',  parent_name: 'Madinat Al Mataar' },
  // Polygon spans two DLD sub-communities; using the larger half (more deals)
  'Zabeel':                               { parent_key: 'zaabeel second',     parent_name: 'Zaabeel Second' },
  'Trade Centre':                         { parent_key: 'trade center second', parent_name: 'Trade Center Second' },
};
// Emirates Living master community: DLD doesn't split it per sub-community,
// all deals roll into "emirate living". Map all sub-polygons to that parent.
for (const n of [
  'Springs 2','Springs 3','Springs 4','Springs 5','Springs 6','Springs 7','Springs 8',
  'Springs 9','Springs 10','Springs 11','Springs 12','Springs 14','Springs 15',
  'Meadows 1','Meadows 2','Meadows 3','Meadows 4','Meadows 5','Meadows 6','Meadows 9',
  'Hattan 2','Emirates Hills',
]) {
  PARENT_OVERRIDES[n] = { parent_key: 'emirate living', parent_name: 'Emirates Living' };
}
for (const f of GEOJSON.features) {
  const ov = PARENT_OVERRIDES[f.properties.name];
  if (!ov || f.properties.real_count) continue;
  const a = AGGREGATES[ov.parent_key];
  if (!a) continue;
  Object.assign(f.properties, {
    real_area_key:    ov.parent_key,
    real_count:       a.n,
    real_total_aed:   a.total,
    real_med_price:   a.med,
    real_med_ppsqm:   a.med_ppsqm,
    real_match_kind:  'parent',
    real_parent_name: ov.parent_name,
  });
}

// ===================== MASKS =====================
// A "mask" picks what each polygon's `real_*` fields hold + which labels
// the legend/popup use. Default = sales × all → identical to original.
//
// Optional per-mask config:
//   metricKey  — which property drives choropleth color (default real_count)
//   scaleMode  — 'log' (default), 'quantile', 'linear'
//   allowZero  — if true, value 0 is colored (default false: 0 → no-data hatch)
//   overlay(r) — string label to render on top of polygon centroids (no overlay if absent)
//   popupRows(p, t, fmt) — custom popup body (default = sales/rents rows)
//   legendFmt  — format function for legend ranges (default = METRIC_FMT.count)
// Resolve inlined per-period datasets. They're injected as `const X = {...}`
// which lands in the script's declarative scope (NOT on `window`), so we need
// direct typeof checks to read them safely without a ReferenceError.
const _TX_P      = (typeof TX_PERIODS      !== 'undefined') ? TX_PERIODS      : {};
const _RENTS_P   = (typeof RENTS_PERIODS   !== 'undefined') ? RENTS_PERIODS   : {};
const _GROWTH_P  = (typeof GROWTH_PERIODS  !== 'undefined') ? GROWTH_PERIODS  : {};
const _PAYBACK_P = (typeof PAYBACK_PERIODS !== 'undefined') ? PAYBACK_PERIODS : {};
const MASKS = {
  sales: {
    labelKey: 'mask_sales', descKey: 'mask_sales_desc',
    periods: ['1y','3y','5y','10y','all'], defaultPeriod: 'all',
    data: {
      all:   AGGREGATES,
      '1y':  _TX_P['1y']  || {},
      '3y':  _TX_P['3y']  || {},
      '5y':  _TX_P['5y']  || {},
      '10y': _TX_P['10y'] || {},
    },
    pluck: r => ({ real_count: r.n || 0, real_total_aed: r.total || 0, real_med_price: r.med || 0, real_med_ppsqm: r.med_ppsqm || 0, real_metric: r.n || 0 }),
    legendKey: 'legend_sales', popupCountKey: 'pp_trans_ytd', showVolume: true,
    tableColumns: [
      { key: 'name',      labelKey: 'tv_col_district', type: 'str',    width: '32%', defaultSort: false },
      { key: 'n',         labelKey: 'tv_col_n_sales',  type: 'int',    width: '13%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'total',     labelKey: 'tv_col_volume',   type: 'aed_big',width: '20%' },
      { key: 'med',       labelKey: 'tv_col_median',   type: 'aed_big',width: '18%' },
      { key: 'med_ppsqm', labelKey: 'tv_col_ppsqm',    type: 'int',    width: '17%' },
    ],
  },
  rents: {
    labelKey: 'mask_rents', descKey: 'mask_rents_desc',
    periods: ['1y','3y','5y','10y','all'], defaultPeriod: 'all',
    data: {
      all:   (typeof RENT_AGGREGATES !== 'undefined') ? RENT_AGGREGATES : {},
      '1y':  _RENTS_P['1y']  || {},
      '3y':  _RENTS_P['3y']  || {},
      '5y':  _RENTS_P['5y']  || {},
      '10y': _RENTS_P['10y'] || {},
    },
    pluck: r => ({ real_count: r.n || 0, real_total_aed: 0, real_med_price: r.med_annual || r.med || 0, real_med_ppsqm: r.med_ppsqm || 0, real_metric: r.n || 0 }),
    legendKey: 'legend_rents', popupCountKey: 'rent_sc_contracts', showVolume: false,
    tableColumns: [
      { key: 'name',                       labelKey: 'tv_col_district',      type: 'str',     width: '38%' },
      { key: 'n',                          labelKey: 'tv_col_n_rents',       type: 'int',     width: '17%', defaultSort: true, defaultSortDir: 'desc' },
      { key: r => r.med_annual || r.med,   labelKey: 'tv_col_median_annual', type: 'aed_big', width: '25%' },
      { key: 'med_ppsqm',                  labelKey: 'tv_col_ppsqm_year',    type: 'int',     width: '20%' },
    ],
  },
  growth: {
    labelKey: 'mask_growth', descKey: 'mask_growth_desc',
    periods: ['1y','3y','5y','10y'], defaultPeriod: '5y',
    data: {
      '1y':  _GROWTH_P['1y']  || {},
      '3y':  _GROWTH_P['3y']  || {},
      '5y':  _GROWTH_P['5y']  || {},
      '10y': _GROWTH_P['10y'] || {},
    },
    pluck: r => ({
      real_count: r.n || 0, real_total_aed: 0,
      real_med_price: 0, real_med_ppsqm: r.med_now || 0,
      real_metric: (typeof r.growth_pct === 'number') ? r.growth_pct : null,
      real_med_then_ppsqm: r.med_then || 0,
      real_fallback_yrs: (typeof r.fallback_yrs === 'number') ? r.fallback_yrs : null,
    }),
    legendKey: 'legend_growth', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    overlay: r => (typeof r.growth_pct !== 'number') ? null
                  : ((r.growth_pct >= 0 ? '+' : '') + Math.round(r.growth_pct) + '%'),
    legendFmt: v => (v >= 0 ? '+' : '') + Math.round(v) + '%',
    popupRows: (p, t) => {
      if (p.real_metric === null || p.real_metric === undefined) return '';
      const fb = (typeof p.real_fallback_yrs === 'number')
        ? `<div class="stat"><span class="k">${t('pp_fallback_yrs')}</span><span class="v">${p.real_fallback_yrs.toFixed(1)} ${t('unit_years')}</span></div>`
        : '';
      return `
      <div class="stat"><span class="k">${t('pp_growth_pct')} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">DLD</span></span><span class="v" style="font-weight:700">${p.real_metric >= 0 ? '+' : ''}${p.real_metric.toFixed(1)}%</span></div>
      <div class="stat"><span class="k">${t('pp_med_now_psqm')}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')}</span></div>
      <div class="stat"><span class="k">${t('pp_med_then_psqm')}</span><span class="v">${(p.real_med_then_ppsqm||0).toLocaleString('ru-RU')}</span></div>
      ${fb}
      <div class="stat"><span class="k">${t('pp_trans_ytd_growth')}</span><span class="v">${p.real_count.toLocaleString('ru-RU')}</span></div>
    `;
    },
    tableColumns: [
      { key: 'name',         labelKey: 'tv_col_district',    type: 'str',     width: '28%' },
      { key: 'growth_pct',   labelKey: 'tv_col_growth_pct',  type: 'pct',     width: '12%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'med_now',      labelKey: 'tv_col_med_now',     type: 'int',     width: '15%' },
      { key: 'med_then',     labelKey: 'tv_col_med_then',    type: 'int',     width: '15%' },
      { key: 'fallback_yrs', labelKey: 'tv_col_history',     type: 'yrs_opt', width: '14%' },
      { key: 'n',            labelKey: 'tv_col_n_last_year', type: 'int',     width: '16%' },
    ],
  },
  payback: {
    labelKey: 'mask_payback', descKey: 'mask_payback_desc',
    periods: ['studio','1br','2br','3br','4br_plus'], defaultPeriod: '1br',
    data: {
      'studio':   _PAYBACK_P['studio']   || {},
      '1br':      _PAYBACK_P['1br']      || {},
      '2br':      _PAYBACK_P['2br']      || {},
      '3br':      _PAYBACK_P['3br']      || {},
      '4br_plus': _PAYBACK_P['4br_plus'] || {},
    },
    pluck: r => ({
      real_count: (r.n_sale || 0) + (r.n_rent || 0),
      real_total_aed: 0,
      real_med_price: r.sale_ppsqm || 0,
      real_med_ppsqm: r.rent_ppsqm || 0,
      real_metric: (typeof r.years === 'number') ? r.years : null,
      real_n_sale: r.n_sale || 0,
      real_n_rent: r.n_rent || 0,
    }),
    legendKey: 'legend_payback', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    invertRamp: true,  // fewer years to break even = better → yellow end of RAMP
    overlay: r => (typeof r.years !== 'number') ? null : r.years.toFixed(1),
    legendFmt: v => v.toFixed(1),
    periodLabelKey: 'mask_room_label',
    popupRows: (p, t) => p.real_metric === null || p.real_metric === undefined ? '' : `
      <div class="stat"><span class="k">${t('pp_payback_years')} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">DLD</span></span><span class="v" style="font-weight:700">${p.real_metric.toFixed(1)} ${t('unit_years')}</span></div>
      <div class="stat"><span class="k">${t('pp_sale_ppsqm')}</span><span class="v">${(p.real_med_price||0).toLocaleString('ru-RU')} AED/м²</span></div>
      <div class="stat"><span class="k">${t('pp_rent_ppsqm')}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')} AED/м²/${t('unit_year_short')}</span></div>
      <div class="stat"><span class="k">${t('pp_n_sale')}</span><span class="v">${(p.real_n_sale||0).toLocaleString('ru-RU')}</span></div>
      <div class="stat"><span class="k">${t('pp_n_rent')}</span><span class="v">${(p.real_n_rent||0).toLocaleString('ru-RU')}</span></div>
    `,
    tableColumns: [
      { key: 'name',       labelKey: 'tv_col_district',    type: 'str', width: '28%' },
      { key: 'years',      labelKey: 'tv_col_payback_yrs', type: 'yrs', width: '14%', defaultSort: true, defaultSortDir: 'asc' },
      { key: 'sale_ppsqm', labelKey: 'tv_col_sale_ppsqm',  type: 'int', width: '15%' },
      { key: 'rent_ppsqm', labelKey: 'tv_col_rent_ppsqm',  type: 'int', width: '15%' },
      { key: 'n_sale',     labelKey: 'tv_col_n_sale_2y',   type: 'int', width: '14%' },
      { key: 'n_rent',     labelKey: 'tv_col_n_rent_2y',   type: 'int', width: '14%' },
    ],
  },
};
// Per-page bootstrap: SEO landing pages (/sales/, /rents/) inject these
// before viewer.js to preselect the mask + period without changing UI state.
let currentMask = (typeof window !== 'undefined' && window.__INITIAL_MASK__ && MASKS[window.__INITIAL_MASK__]) ? window.__INITIAL_MASK__ : 'sales';
let currentMaskPeriod = (typeof window !== 'undefined' && window.__INITIAL_PERIOD__ && MASKS[currentMask] && MASKS[currentMask].periods.includes(window.__INITIAL_PERIOD__)) ? window.__INITIAL_PERIOD__ : 'all';
let currentView = (typeof window !== 'undefined' && window.__INITIAL_VIEW__ === 'table') ? 'table' : 'map';
// Per-mask runtime UI state for the table view (sort + search). Persisted
// across mask switches inside the same session so a user toggling between
// /sales/table/ and /rents/table/ keeps a per-table sort intent.
const _tableState = {};  // { [maskId]: { sortKey, sortDir, search } }

// Snapshot baseline real_* (post-PARENT_OVERRIDES) so applyMask can restore cleanly.
const BASE_REAL = new Map();
for (const f of GEOJSON.features) {
  const p = f.properties;
  BASE_REAL.set(f, {
    real_count:       p.real_count       || 0,
    real_total_aed:   p.real_total_aed   || 0,
    real_med_price:   p.real_med_price   || 0,
    real_med_ppsqm:   p.real_med_ppsqm   || 0,
    real_area_key:    p.real_area_key    || null,
    real_match_kind:  p.real_match_kind  || null,
    real_parent_name: p.real_parent_name || null,
  });
}

// Fields any mask might write — reset to neutral defaults before pluck() runs.
const _MASK_FIELDS = [
  'real_count','real_total_aed','real_med_price','real_med_ppsqm',
  'real_metric','real_med_then_ppsqm','real_n_sale','real_n_rent','real_fallback_yrs',
];
function _resetMaskFields(p) {
  for (const f of _MASK_FIELDS) p[f] = (f === 'real_metric' || f === 'real_fallback_yrs') ? null : 0;
}

function applyMask(maskId, period, opts) {
  opts = opts || {};
  const mask = MASKS[maskId];
  if (!mask) return;
  if (!mask.periods.includes(period)) period = mask.defaultPeriod;
  currentMask = maskId;
  currentMaskPeriod = period;
  const data = mask.data[period] || {};
  for (const f of GEOJSON.features) {
    const base = BASE_REAL.get(f) || {};
    f.properties.real_area_key    = base.real_area_key;
    f.properties.real_match_kind  = base.real_match_kind;
    f.properties.real_parent_name = base.real_parent_name;
    _resetMaskFields(f.properties);
    const rec = base.real_area_key && data[base.real_area_key];
    if (rec) Object.assign(f.properties, mask.pluck(rec));
  }
  if (typeof renderChoro === 'function') renderChoro();
  if (typeof updateMaskCurrentLabel === 'function') updateMaskCurrentLabel();
  if (currentView === 'table' && typeof renderTable === 'function') renderTable();
  if (opts.pushUrl !== false) _pushPageUrl(maskId, currentView);
}

function setView(view, opts) {
  opts = opts || {};
  if (view !== 'map' && view !== 'table') return;
  if (view === currentView && !opts.force) {
    if (opts.pushUrl !== false) _pushPageUrl(currentMask, view);
    return;
  }
  currentView = view;
  document.body.classList.toggle('view-table', view === 'table');
  if (view === 'table') {
    renderTable();
  } else if (typeof map !== 'undefined' && map.invalidateSize) {
    // Map was display:none — needs a resize tick after un-hiding
    setTimeout(() => map.invalidateSize(), 50);
  }
  if (typeof renderMaskList === 'function') renderMaskList();
  if (typeof updateMaskCurrentLabel === 'function') updateMaskCurrentLabel();
  if (opts.pushUrl !== false) _pushPageUrl(currentMask, view);
}

// ===================== URL routing for SEO masks =====================
// Each SEO mask owns two SEO landings: map (/<mask>/) and table
// (/<mask>/table/). Switching mask or view via dropdown / footer pills
// updates the URL so deep links + Back/Forward both work.
const _SEO_MASKS = ['sales', 'rents', 'growth', 'payback'];

function _isSeoMask(m) { return _SEO_MASKS.indexOf(m) !== -1; }

function _currentPageState() {
  const p = (typeof window !== 'undefined' ? window.location.pathname : '') || '';
  for (const m of _SEO_MASKS) {
    if (new RegExp('/' + m + '/table/(index\\.html)?$').test(p)) return { mask: m, view: 'table' };
    if (new RegExp('/' + m + '/(index\\.html)?$').test(p))       return { mask: m, view: 'map' };
  }
  return { mask: null, view: 'map' };
}
function _currentPageMask() { return _currentPageState().mask; }

function _hrefForPage(targetMask, targetView) {
  targetView = targetView || 'map';
  const cur = _currentPageState();
  if (cur.mask === targetMask && cur.view === targetView) return null;
  // upSteps = '../' count needed to reach project root from current page
  const upSteps = (cur.mask ? 1 : 0) + (cur.view === 'table' ? 1 : 0);
  let rel = upSteps ? '../'.repeat(upSteps) : './';
  rel += targetMask + '/';
  if (targetView === 'table') rel += 'table/';
  // file:// browsers don't auto-resolve '/' to index.html — they show a
  // directory listing. Append it explicitly so the link works either way.
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') rel += 'index.html';
  try { return new URL(rel, window.location.href).href; } catch (e) { return null; }
}

function _pushPageUrl(maskId, view) {
  view = view || 'map';
  if (!_isSeoMask(maskId)) return;
  const cur = _currentPageState();
  if (cur.mask === maskId && cur.view === view) return;
  const href = _hrefForPage(maskId, view);
  if (!href) return;
  // Chrome/Safari block pushState across file:// origins → real navigation
  if (window.location.protocol === 'file:') { window.location.href = href; return; }
  try { history.pushState({ mask: maskId, view }, '', href); }
  catch (e) { window.location.href = href; }
}

window.addEventListener('popstate', () => {
  const cur = _currentPageState();
  if (cur.mask && cur.mask !== currentMask) {
    const mk = MASKS[cur.mask];
    if (mk) applyMask(cur.mask, mk.defaultPeriod, { pushUrl: false });
  }
  if (cur.view !== currentView) setView(cur.view, { pushUrl: false });
  if (typeof renderMaskList === 'function') renderMaskList();
});

// ===================== TABLE VIEW =====================
function _tableValue(col, rec) {
  return typeof col.key === 'function' ? col.key(rec) : rec[col.key];
}
function _tableColIdent(col) {
  return typeof col.key === 'function' ? col.labelKey : col.key;
}
function _tableFmt(col, v) {
  if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return '—';
  switch (col.type) {
    case 'str': return String(v);
    case 'int': return Number(v).toLocaleString('ru-RU');
    case 'aed_big': {
      const n = Number(v) || 0;
      if (n >= 1e9) return (n/1e9).toFixed(2) + ' ' + t('abbr_b');
      if (n >= 1e6) return (n/1e6).toFixed(1) + ' ' + t('abbr_m');
      return n.toLocaleString('ru-RU');
    }
    case 'pct':     return (v >= 0 ? '+' : '') + Number(v).toFixed(1) + '%';
    case 'yrs':
    case 'yrs_opt': return Number(v).toFixed(1) + ' ' + t('unit_years');
    default:        return String(v);
  }
}
function _tableSort(rows, col, dir) {
  const sign = dir === 'asc' ? 1 : -1;
  return rows.slice().sort((a, b) => {
    const va = _tableValue(col, a), vb = _tableValue(col, b);
    const an = (va === null || va === undefined || (typeof va === 'number' && isNaN(va))) ? 1 : 0;
    const bn = (vb === null || vb === undefined || (typeof vb === 'number' && isNaN(vb))) ? 1 : 0;
    if (an !== bn) return an - bn;  // null/missing always sorted last
    if (col.type === 'str') return sign * String(va).localeCompare(String(vb), 'ru');
    return sign * (Number(va) - Number(vb));
  });
}

const PAGE_SIZE = 50;

function _renderTvPages() {
  const el = document.getElementById('tv-pages');
  if (!el) return;
  el.innerHTML = '';
  for (const m of _SEO_MASKS) {
    const mk = MASKS[m];
    if (!mk) continue;
    const isCurrent = (m === currentMask);
    const a = document.createElement('a');
    a.className = 'tv-page-pill' + (isCurrent ? ' active' : '');
    a.textContent = t(mk.labelKey);
    if (isCurrent) {
      a.setAttribute('aria-current', 'page');
    } else {
      const href = _hrefForPage(m, 'table');
      if (href) a.href = href;
      a.addEventListener('click', e => {
        e.preventDefault();
        applyMask(m, mk.defaultPeriod);
      });
    }
    el.appendChild(a);
  }
}

function _renderTvPeriods() {
  const el = document.getElementById('tv-periods');
  if (!el) return;
  const mask = MASKS[currentMask];
  el.innerHTML = '';
  if (!mask || mask.periods.length <= 1) return;
  const lbl = document.createElement('span');
  lbl.className = 'tv-periods-k';
  lbl.textContent = t(mask.periodLabelKey || 'mask_period_label');
  el.appendChild(lbl);
  for (const p of mask.periods) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tv-period-chip' + (p === currentMaskPeriod ? ' active' : '');
    btn.textContent = _periodLabel(mask, p);
    btn.addEventListener('click', () => {
      const state = _tableState[currentMask] || (_tableState[currentMask] = {});
      state.page = 1;
      applyMask(currentMask, p);
    });
    el.appendChild(btn);
  }
}

function _renderTvPager(page, totalPages, total) {
  const el = document.getElementById('tv-pager');
  if (!el) return;
  if (totalPages <= 1) { el.innerHTML = ''; return; }

  const btns = [];
  // Prev
  btns.push(`<button class="tv-pager-btn${page<=1?' disabled':''}" data-page="${page-1}">‹</button>`);

  // Numbered: 1, …, p-1, p, p+1, …, M  (sliding window of ±1 around current)
  const windowSize = 1;
  const want = new Set([1, totalPages, page]);
  for (let d = 1; d <= windowSize; d++) {
    if (page - d > 1) want.add(page - d);
    if (page + d < totalPages) want.add(page + d);
  }
  const pages = Array.from(want).sort((a, b) => a - b);
  let last = 0;
  for (const p of pages) {
    if (p - last > 1) btns.push(`<span class="tv-pager-ellipsis">…</span>`);
    btns.push(`<button class="tv-pager-btn${p===page?' active':''}" data-page="${p}">${p}</button>`);
    last = p;
  }

  // Next
  btns.push(`<button class="tv-pager-btn${page>=totalPages?' disabled':''}" data-page="${page+1}">›</button>`);
  btns.push(`<span class="tv-pager-info">${total.toLocaleString('ru-RU')} ${t('tv_count_label')}</span>`);
  el.innerHTML = btns.join('');
  el.querySelectorAll('.tv-pager-btn').forEach(b => {
    b.addEventListener('click', () => {
      if (b.classList.contains('disabled') || b.classList.contains('active')) return;
      const p = parseInt(b.dataset.page, 10);
      if (!Number.isFinite(p)) return;
      const state = _tableState[currentMask] || (_tableState[currentMask] = {});
      state.page = Math.max(1, Math.min(totalPages, p));
      renderTable();
      // Keep the table in view after a page change
      const scroll = document.querySelector('#table-view .tv-scroll');
      if (scroll) scroll.scrollTop = 0;
    });
  });
}

function renderTable() {
  const mask = MASKS[currentMask];
  if (!mask || !mask.tableColumns) return;

  // Per-mask state (sort + search + page) survives mask switches in-session
  const state = _tableState[currentMask] || (_tableState[currentMask] = {});
  if (!state.sortKey) {
    const def = mask.tableColumns.find(c => c.defaultSort) || mask.tableColumns[1] || mask.tableColumns[0];
    state.sortKey = _tableColIdent(def);
    state.sortDir = (def && def.defaultSortDir) || 'desc';
  }
  if (state.search === undefined) state.search = '';
  if (!state.page) state.page = 1;

  _renderTvPages();
  _renderTvPeriods();

  const searchEl = document.getElementById('tv-search');
  if (searchEl && searchEl.value !== state.search) searchEl.value = state.search;
  if (searchEl) searchEl.placeholder = t('tv_search_placeholder');

  const data = mask.data[currentMaskPeriod] || {};
  const dubaiKey = '__dubai__';
  const q = state.search.toLowerCase().trim();
  const matches = (rec) => !q || (rec.name || '').toLowerCase().includes(q);

  let rows = [];
  for (const [k, rec] of Object.entries(data)) {
    if (k === dubaiKey) continue;
    if (matches(rec)) {
      // attach area_key inline so the district cell can render a clickable
      // link without us having to thread (key, rec) tuples through sort
      rec._k = k;
      rows.push(rec);
    }
  }
  const sortCol = mask.tableColumns.find(c => _tableColIdent(c) === state.sortKey) || mask.tableColumns[0];
  rows = _tableSort(rows, sortCol, state.sortDir);

  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (state.page > totalPages) state.page = totalPages;
  const start = (state.page - 1) * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);

  const cols = mask.tableColumns.map(c => `<col${c.width ? ' style="width:' + c.width + '"' : ''}>`).join('');
  const ths = mask.tableColumns.map(c => {
    const ident = _tableColIdent(c);
    const sortedCls = (ident === state.sortKey) ? (' sorted-' + state.sortDir) : '';
    const numCls = (c.type !== 'str') ? 'num' : '';
    const cls = (numCls + sortedCls).trim();
    return `<th data-col="${ident}"${cls ? ' class="' + cls + '"' : ''}>${t(c.labelKey)}</th>`;
  }).join('');

  const renderCell = (c, rec, isDubai) => {
    const v = _tableValue(c, rec);
    const isNum = c.type !== 'str';
    const txt = _tableFmt(c, v);
    let cls = isNum ? 'num' : '';
    if (c.type === 'pct' && typeof v === 'number' && !isDubai) cls += ' ' + (v >= 0 ? 'pos' : 'neg');
    cls = cls.trim();
    // District-name cell — make it a clickable link that opens the polygon
    // (or Dubai-wide panel for the rollup row) in map view.
    if (c.key === 'name') {
      const areaKey = isDubai ? '__dubai__' : (rec && rec._k);
      if (areaKey) {
        const safe = areaKey.replace(/"/g, '&quot;');
        return `<td${cls ? ' class="' + cls + '"' : ''}><a class="tv-district-link" data-key="${safe}">${txt}</a></td>`;
      }
    }
    return `<td${cls ? ' class="' + cls + '"' : ''}>${txt}</td>`;
  };

  // Dubai rollup pinned at the top of page 1 (and ONLY there) so the
  // city-wide reference number is visible without polluting later pages.
  let dubaiHtml = '';
  if (state.page === 1 && data[dubaiKey] && matches(data[dubaiKey])) {
    dubaiHtml = '<tr class="dubai-row">' + mask.tableColumns.map(c => renderCell(c, data[dubaiKey], true)).join('') + '</tr>';
  }
  const bodyHtml = pageRows.length
    ? pageRows.map(rec => '<tr>' + mask.tableColumns.map(c => renderCell(c, rec, false)).join('') + '</tr>').join('')
    : `<tr><td colspan="${mask.tableColumns.length}" class="tv-empty">${t('search_empty')}</td></tr>`;

  const tbl = document.getElementById('tv-table');
  if (!tbl) return;
  tbl.innerHTML = `<colgroup>${cols}</colgroup><thead><tr>${ths}</tr></thead><tbody>${dubaiHtml}${bodyHtml}</tbody>`;

  const cnt = document.getElementById('tv-count');
  if (cnt) cnt.textContent = total.toLocaleString('ru-RU') + ' ' + t('tv_count_label');

  _renderTvPager(state.page, totalPages, total);

  tbl.querySelectorAll('th').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.col;
      if (state.sortKey === k) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = k; state.sortDir = (sortCol.type === 'str') ? 'asc' : 'desc'; }
      state.page = 1;
      renderTable();
    });
  });
  tbl.querySelectorAll('.tv-district-link').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      _openDistrictFromTable(a.dataset.key);
    });
  });
}

// Close the table view, switch to map, and zoom + open the polygon popup
// for the given area_key. Used by district-name links in the table view.
function _openDistrictByKey(areaKey) {
  if (areaKey === '__dubai__') {
    if (typeof window.openDubai === 'function') window.openDubai();
    return;
  }
  const feat = GEOJSON.features.find(f => f.properties.real_area_key === areaKey);
  if (feat && typeof _onSearchSelect === 'function') _onSearchSelect(feat);
}

function _openDistrictFromTable(areaKey) {
  if (!areaKey) return;
  // On file://, setView('map') falls through to a real page navigation
  // because pushState is blocked. Stash the district in the URL hash so the
  // destination page can finish the open after it boots.
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') {
    const href = _hrefForPage(currentMask, 'map');
    if (href) {
      window.location.href = href + '#district=' + encodeURIComponent(areaKey);
      return;
    }
  }
  // http(s): in-place. Flip view, force a layout tick, then fly + popup.
  // Two rAFs — first lets the browser paint after display:none is removed,
  // second runs after Leaflet sees the restored dimensions.
  setView('map');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (typeof map !== 'undefined' && map.invalidateSize) map.invalidateSize();
    _openDistrictByKey(areaKey);
  }));
}

function _periodLabel(mask, p) {
  // payback mask uses room-class periods; everything else is years
  if (mask && mask.periods && mask.periods.includes('studio'))
    return t('room_' + p);
  return t('period_' + p);
}

function updateMaskCurrentLabel() {
  const el = document.getElementById('mp-mask-current');
  if (!el) return;
  const mask = MASKS[currentMask];
  if (!mask) return;
  const lbl = t(mask.labelKey);
  const showPer = mask.periods.length > 1 && currentMaskPeriod !== 'all';
  el.textContent = showPer ? (lbl + ' · ' + _periodLabel(mask, currentMaskPeriod)) : lbl;
}

function renderMaskList() {
  const list = document.getElementById('mp-mask-list');
  if (!list) return;
  list.innerHTML = '';
  for (const [id, mask] of Object.entries(MASKS)) {
    const row = document.createElement('div');
    row.className = 'mask-row' + (id === currentMask ? ' active' : '');
    row.dataset.mask = id;
    const periodHTML = mask.periods.length > 1
      ? `<div class="mask-row-periods">
           <span class="pc-lbl">${t(mask.periodLabelKey || 'mask_period_label')}</span>
           ${mask.periods.map(p =>
              `<button type="button" class="mask-period-chip${(id===currentMask && p===currentMaskPeriod)?' active':''}" data-period="${p}">${_periodLabel(mask, p)}</button>`
           ).join('')}
         </div>`
      : '';
    row.innerHTML = `
      <div class="mask-row-head">
        <div class="mask-row-radio"></div>
        <div class="mask-row-title">${t(mask.labelKey)}</div>
      </div>
      <div class="mask-row-desc">${t(mask.descKey)}</div>
      ${periodHTML}
    `;
    row.addEventListener('click', e => {
      if (e.target.closest('.mask-period-chip')) return;
      applyMask(id, (id === currentMask) ? currentMaskPeriod : mask.defaultPeriod);
      renderMaskList();
    });
    row.querySelectorAll('.mask-period-chip').forEach(chip => {
      chip.addEventListener('click', e => {
        e.stopPropagation();
        applyMask(id, chip.dataset.period);
        renderMaskList();
      });
    });
    list.appendChild(row);
  }
  // ── View toggle (Map / Table) ──────────────────────────────────────────
  const viewRow = document.createElement('div');
  viewRow.className = 'mp-mask-view';
  viewRow.innerHTML = `
    <span class="mp-mask-view-k">${t('view_label')}</span>
    <button type="button" class="mp-mask-view-btn${currentView==='map'?' active':''}" data-view="map">${t('view_map')}</button>
    <button type="button" class="mp-mask-view-btn${currentView==='table'?' active':''}" data-view="table">${t('view_table')}</button>
  `;
  viewRow.querySelectorAll('.mp-mask-view-btn').forEach(b => {
    b.addEventListener('click', () => setView(b.dataset.view));
  });
  list.appendChild(viewRow);

  // ── SEO page pills (preserve current view in hrefs) ───────────────────
  const cur = _currentPageMask();
  const foot = document.createElement('div');
  foot.className = 'mp-mask-page';
  const viewSuffix = currentView === 'table' ? 'table/' : '';
  const parts = [`<span class="mp-mask-page-k">${t('current_page')}</span>`];
  for (const m of _SEO_MASKS) {
    const mk = MASKS[m];
    if (!mk) continue;
    const label = t(mk.labelKey);
    const path  = '/' + m + '/' + viewSuffix;
    if (m === cur) {
      parts.push(`<span class="mp-mask-page-cur" title="${label}">${path}</span>`);
    } else {
      const href = _hrefForPage(m, currentView) || '#';
      parts.push(`<a class="mp-mask-page-go" href="${href}" data-mask="${m}" title="${label}">${path}</a>`);
    }
  }
  foot.innerHTML = parts.join(' ');
  foot.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', e => {
      e.preventDefault();
      const m = a.dataset.mask;
      const mk = MASKS[m];
      if (!mk) return;
      applyMask(m, mk.defaultPeriod);
      renderMaskList();
    });
  });
  list.appendChild(foot);
}

// Wire table-view controls (script is in <body> end, so DOM exists)
(function _wireTableUI() {
  const searchEl = document.getElementById('tv-search');
  if (searchEl) {
    searchEl.addEventListener('input', e => {
      const state = _tableState[currentMask] || (_tableState[currentMask] = {});
      state.search = e.target.value;
      state.page = 1;
      renderTable();
    });
  }
  const backBtn = document.getElementById('tv-back-map');
  if (backBtn) backBtn.addEventListener('click', () => setView('map'));
})();

// ===================== LOCATION LEVELS =====================
// Each feature is tagged with `_level` = depth of its containment chain:
// 0 = nothing contains it; 1 = contained by a level-0; 2 = contained by a level-1; etc.
// Features then sorted by bbox area DESC so smaller polygons render on top —
// click events naturally route to the smallest containing polygon.
let minLevel = 0;
function _bbox(geom){
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  (function walk(o){
    if (typeof o[0] === 'number' && o.length === 2){
      if(o[0]<minX)minX=o[0]; if(o[0]>maxX)maxX=o[0];
      if(o[1]<minY)minY=o[1]; if(o[1]>maxY)maxY=o[1];
      return;
    }
    for (const x of o) walk(x);
  })(geom.coordinates);
  return {area:(maxX-minX)*(maxY-minY), cx:(minX+maxX)/2, cy:(minY+maxY)/2};
}
function _pip(pt, ring){
  const x=pt[0], y=pt[1]; let inside=false;
  for (let i=0,j=ring.length-1; i<ring.length; j=i++){
    const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
    if ((yi>y)!=(yj>y) && x<(xj-xi)*(y-yi)/(yj-yi+1e-15)+xi) inside=!inside;
  }
  return inside;
}
function _featContains(f, pt){
  const g = f.geometry;
  if (g.type==='Polygon') return _pip(pt, g.coordinates[0]);
  if (g.type==='MultiPolygon') return g.coordinates.some(poly => _pip(pt, poly[0]));
  return false;
}
(function computeLocationLevels(){
  const N = GEOJSON.features.length;
  const bbs = GEOJSON.features.map(f => _bbox(f.geometry));
  // containers[i] = indices j s.t. j's polygon contains i's centroid AND j is 1.5x+ bigger
  const containers = Array.from({length:N}, () => []);
  for (let i=0; i<N; i++){
    const bi = bbs[i];
    for (let j=0; j<N; j++){
      if (i===j) continue;
      if (bbs[j].area <= bi.area * 1.5) continue;
      if (_featContains(GEOJSON.features[j], [bi.cx, bi.cy])) containers[i].push(j);
    }
  }
  const level = new Array(N).fill(-1);
  function compute(i, path){
    if (level[i] !== -1) return level[i];
    if (path && path.has(i)) return 0;
    if (containers[i].length === 0) { level[i] = 0; return 0; }
    const next = path ? new Set(path) : new Set();
    next.add(i);
    let mx = 0;
    for (const j of containers[i]) mx = Math.max(mx, compute(j, next));
    level[i] = 1 + mx;
    return level[i];
  }
  const counts = [0,0,0,0,0,0];
  for (let i=0; i<N; i++){
    compute(i);
    GEOJSON.features[i]._level    = level[i];
    GEOJSON.features[i]._bboxArea = bbs[i].area;
    if (level[i] < counts.length) counts[level[i]]++;
  }
  // Sort: biggest first. Renderer adds in array order → smallest on top in SVG.
  GEOJSON.features.sort((a, b) => b._bboxArea - a._bboxArea);
  console.log('location levels:', counts.map((c,i)=>`L${i}=${c}`).join(' '));
})();

// ===================== NEW DEVELOPMENTS PER DISTRICT =====================
// Count construction projects whose centroid falls inside each district polygon.
// Polygons are now sorted DESC by bbox area, so walking the array in reverse
// gives us smallest-first — a project lands in its tightest container.
(function tagProjectsToDistricts() {
  if (typeof PROJECTS === 'undefined') return;
  // PROJECTS is now district-level aggregates — each entry already carries
  // the in-flight count for its polygon, so we just route it to the smallest
  // enclosing district feature for the side-panel badge.
  for (const p of PROJECTS) {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon)) continue;
    const count = p.in_flight || 0;
    if (!count) continue;
    for (let i = GEOJSON.features.length - 1; i >= 0; i--) {
      const f = GEOJSON.features[i];
      if (_featContains(f, [p.lon, p.lat])) {
        f.properties._new_dev_count = (f.properties._new_dev_count || 0) + count;
        break;
      }
    }
  }
})();

// ===================== DISTRICT SEARCH =====================
let _searchIndex = null;
function _buildSearchIndex(){
  return GEOJSON.features
    .filter(f => f.properties.name)
    .map(f => ({
      name:   f.properties.name,
      nameAr: f.properties.name_ar || '',
      rc:     f.properties.real_count || 0,
      level:  f._level || 0,
      feat:   f,
    }))
    .sort((a,b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
}
function _renderSearchResults(query){
  if (!_searchIndex) _searchIndex = _buildSearchIndex();
  const q = (query||'').toLowerCase().trim();
  let items = _searchIndex;
  if (q) {
    items = _searchIndex.filter(x =>
      x.name.toLowerCase().includes(q) || (x.nameAr && x.nameAr.includes(query)));
    // Prefix matches first
    items.sort((a,b) => {
      const ap = a.name.toLowerCase().startsWith(q) ? 0 : 1;
      const bp = b.name.toLowerCase().startsWith(q) ? 0 : 1;
      if (ap !== bp) return ap - bp;
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });
  }
  items = items.slice(0, 10);
  const el = document.getElementById('search-results');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = `<div class="sr-empty">${t('search_empty')}</div>`;
    return;
  }
  el.innerHTML = items.map((x, i) =>
    `<div class="sr-item" data-i="${i}"><span class="sr-name">${x.name}</span><span class="sr-meta">L${x.level}${x.rc?(' · '+x.rc.toLocaleString('ru-RU')):''}</span></div>`
  ).join('');
  el.querySelectorAll('.sr-item').forEach((it, i) => {
    it.addEventListener('click', () => _onSearchSelect(items[i].feat));
  });
}
function _onSearchSelect(feat){
  // If hidden by current level filter, reset to 0
  if (feat._level !== undefined && feat._level < minLevel) {
    minLevel = 0;
    document.querySelectorAll('#mp-level-list .ls-btn').forEach(x => {
      x.classList.toggle('active', parseInt(x.dataset.minLevel,10) === 0);
    });
    const cur = document.getElementById('mp-level-current');
    if (cur) cur.textContent = '0+';
    if (typeof renderChoro === 'function') renderChoro();
  }
  const bb = _bbox(feat.geometry);
  const center = [bb.cy, bb.cx];
  map.flyTo(center, Math.max(map.getZoom(), 14), {duration: 0.5});
  document.getElementById('mp-search').classList.remove('open');
  setTimeout(() => {
    let layer = null;
    if (typeof choro !== 'undefined' && choro && choro.eachLayer) {
      choro.eachLayer(l => { if (l.feature === feat) layer = l; });
    }
    if (layer && layer.openPopup) layer.openPopup(center);
  }, 550);
}

let choro;
let overlayLayer = null;
function _refreshOverlay(mask) {
  if (overlayLayer) { map.removeLayer(overlayLayer); overlayLayer = null; }
  if (!mask || typeof mask.overlay !== 'function') return;
  const data = mask.data[currentMaskPeriod] || {};
  overlayLayer = L.layerGroup();
  for (const f of GEOJSON.features) {
    if (f._level !== undefined && f._level < minLevel) continue;
    const key = f.properties.real_area_key;
    if (!key) continue;
    const rec = data[key];
    if (!rec) continue;
    const label = mask.overlay(rec);
    if (label === null || label === undefined || label === '') continue;
    const bb = _bbox(f.geometry);
    const icon = L.divIcon({
      className: 'choro-overlay',
      html: `<span class="choro-overlay-text">${label}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
    L.marker([bb.cy, bb.cx], { icon, interactive: false, keyboard: false }).addTo(overlayLayer);
  }
  overlayLayer.addTo(map);
}

function renderChoro(){
  const mask = MASKS[currentMask] || MASKS.sales;
  const metricKey = mask.metricKey || 'real_count';
  const scale     = mask.scaleMode || 'log';
  const allowZero = !!mask.allowZero;
  const isMissing = (v) => v === null || v === undefined || isNaN(v) || (!allowZero && v === 0);
  const vs = GEOJSON.features
    .map(f => f.properties[metricKey])
    .filter(v => !isMissing(v));
  const breaks = vs.length
    ? (scale==='quantile' ? qBreaks(vs,RAMP.length)
       : scale==='log'    ? logBreaks(vs,RAMP.length)
       :                    lBreaks(vs,RAMP.length))
    : Array(RAMP.length - 1).fill(0);
  if(choro) map.removeLayer(choro);
  choro = L.geoJSON(GEOJSON,{
    filter: f => (f._level !== undefined ? f._level >= minLevel : true),
    style: f => {
      const v = f.properties[metricKey], z = isMissing(v);
      if (z) return {weight:0.8,color:'#64748b',fillColor:'url(#nodata-hatch)',fillOpacity:1,dashArray:'4,3'};
      let idx = classify(v, breaks);
      if (mask.invertRamp) idx = RAMP.length - 1 - idx;
      return {weight:0.6,color:'#1f2933',fillColor:RAMP[idx],fillOpacity:0.7};
    },
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindPopup(() => {
        const m = MASKS[currentMask] || MASKS.sales;
        const sourceLabel = ({'osm-admin':'OSM admin_level=10','osm-place':'OSM place='+(p.kind||''),'osm-residential':'OSM landuse=residential'})[p.source] || 'OSM';
        const newDev = p._new_dev_count || 0;
        const newDevRow = newDev ? `<div class="stat"><span class="k">${t("new_buildings")} <span class="src-tag src-osm">OSM</span></span><span class="v">${newDev}</span></div>` : '';
        const detailsBtn = p.real_area_key ? `<div style="margin-top:8px"><button onclick='openDistrictByKey(${JSON.stringify(p.real_area_key)})' style="background:#0366d6;color:#fff;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600">${t("pp_open")}</button></div>` : '';
        let bodyRows;
        if (typeof m.popupRows === 'function') {
          const rendered = m.popupRows(p, t);
          bodyRows = rendered
            ? `${rendered}${newDevRow}${detailsBtn}`
            : `${newDevRow}<div class="muted" style="font-size:11px;color:#888;padding:4px 0">${t("no_dld_data")}</div>`;
        } else {
          const volumeRow = m.showVolume ? `<div class="stat"><span class="k">${t("pp_volume")}</span><span class="v">${(p.real_total_aed||0)>=1e9?((p.real_total_aed/1e9).toFixed(2)+' '+t('abbr_b')):((p.real_total_aed/1e6).toFixed(1)+' '+t('abbr_m'))}</span></div>` : '';
          bodyRows = p.real_count ? `
            <div class="stat"><span class="k">${t(m.popupCountKey || "pp_trans_ytd")} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">DLD</span>${p.real_match_kind==='parent'?' <span class="src-tag" style="background:#fff5e6;color:#7a4c00">parent: '+p.real_parent_name+'</span>':''}</span><span class="v">${p.real_count.toLocaleString('ru-RU')}</span></div>
            ${volumeRow}
            <div class="stat"><span class="k">${t("pp_median")}</span><span class="v">${((p.real_med_price||0)/1e6).toFixed(2)} ${t('abbr_m')}</span></div>
            <div class="stat"><span class="k">${t("pp_median_psqm")}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')}</span></div>
            ${newDevRow}
            ${detailsBtn}
          ` : `
            ${newDevRow}
            <div class="muted" style="font-size:11px;color:#888;padding:4px 0">${t("no_dld_data")}</div>
          `;
        }
        return `
          <h3>${p.name||'—'} <span class="src-tag src-osm">${sourceLabel}</span></h3>
          <div class="muted" style="margin-bottom:6px;color:#888">${p.name_ar||''}</div>
          ${bodyRows}
        `;
      });
      layer.on({
        mouseover:e=>e.target.setStyle({weight:2,color:'#000'}),
        mouseout:e=>choro.resetStyle(e.target),
      });
    },
  }).addTo(map);
  choro.bringToBack();

  // Legend
  const fmt = mask.legendFmt || METRIC_FMT.count;
  const title = t(mask.legendKey || 'ch_count');
  const lo = vs.length ? Math.min(...vs) : 0;
  const hi = vs.length ? Math.max(...vs) : 0;
  const all = [lo, ...breaks, hi];
  let html = `<div style="font-weight:600;margin-bottom:4px">${title}</div>`;
  for(let i=0;i<RAMP.length;i++) {
    const cIdx = mask.invertRamp ? (RAMP.length - 1 - i) : i;
    html += `<div class="row"><span class="sw" style="background:${RAMP[cIdx]}"></span>${fmt(all[i])} – ${fmt(all[i+1])}</div>`;
  }
  html += `<div class="row"><span class="sw" style="background:repeating-linear-gradient(45deg,transparent,transparent 3px,#94a3b8 3px,#94a3b8 4px)"></span>${t('legend_no_data')}</div>`;
  document.getElementById('legend').innerHTML = html;

  _refreshOverlay(mask);
}
// metric/scale selectors are hidden — listeners disabled
// document.getElementById('metric').addEventListener('change', renderChoro);
// document.getElementById('scale').addEventListener('change', renderChoro);

// ===================== METRO LINES + STATIONS =====================
// All metro lines and stations in a single toggle layer
const metroLayer = L.layerGroup();
// Merge Tram into the metro features so the single toggle controls both.
if (typeof TRAM_LINE !== 'undefined') METRO_LINES.features.push(TRAM_LINE);
for (const f of METRO_LINES.features) {
  L.geoJSON(f, {style: {color: f.properties.color, weight: 4, opacity: 0.9, dashArray: f.properties.status==='construction' ? '8,6' : null}}).addTo(metroLayer);
}
function getGroupLabel(g) { return ({red:t('metro_line_red'), green:t('metro_line_green'), blue:t('metro_line_blue'), tram:t('metro_line_tram'), gold:t('metro_line_gold')})[g] || g; }
const GROUP_PIN = {red:'metro-red', green:'metro-green', blue:'metro-blue', tram:'metro-tram', gold:'metro-gold'};
if (typeof TRAM_STATIONS !== 'undefined') {
  for (const s of TRAM_STATIONS) METRO_STATIONS.push(s);
}
for (const s of METRO_STATIONS) {
  const groups = s.groups || [s.group];
  const labelLines = groups.map(g => getGroupLabel(g)).join(' / ');
  const isInterchange = groups.length > 1;
  // Render once per station, with the first group's colour (or red if multiple to highlight interchanges)
  const primary = groups[0];
  const pinLetter = (primary === 'tram') ? 'T' : 'M';
  const icon = L.divIcon({className:'', html:`<div class="pin ${GROUP_PIN[primary]}">${pinLetter}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => `
    <h3>🚇 ${s.name || t('station_default')} <span class="src-tag src-osm">OSM</span></h3>
    <div class="muted" style="color:#888;margin-bottom:4px">${labelLines}${isInterchange?(' · '+t('metro_interchange')):''}</div>
    ${s.line ? `<div class="stat"><span class="k">${t("metro_line")}</span><span class="v">${s.line}</span></div>` : ''}
  `);
  m.addTo(metroLayer);
}

// ===================== SCHOOLS (KHDA-enriched) =====================
const schoolLayer = L.layerGroup();
const _rcls = v => (v || '').replace(/\s+/g, '');
for (const s of SCHOOLS) {
  const icon = L.divIcon({className:'', html:`<div class="pin school">🏫</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => {
    const hasName = s.name && s.name !== '(unnamed school)';
    // Arabic name renders RTL; we set dir on the title so it doesn't get
    // visually broken when mixed with Latin browser fonts.
    const nameIsArabic = hasName && /[؀-ۿ]/.test(s.name);
    const titleAttr = nameIsArabic ? ' dir="rtl" style="text-align:right"' : '';
    const displayName = hasName
      ? `<span${titleAttr}>${s.name}</span>`
      : ('<span style="color:#888">' + t('no_name') + '</span>');
    const arSubtitle = (s.name_ar && s.name_ar !== s.name)
      ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${s.name_ar}</div>`
      : '';
    if (!s.in_khda) {
      const osmRows = [];
      if (s.operator)       osmRows.push(`<div class="stat"><span class="k">${t('h_op')}</span><span class="v">${s.operator}</span></div>`);
      if (s.school_type)    osmRows.push(`<div class="stat"><span class="k">${t('sch_curr')}</span><span class="v">${s.school_type}</span></div>`);
      if (s.school_gender)  osmRows.push(`<div class="stat"><span class="k">${t('sch_gender')}</span><span class="v">${s.school_gender}</span></div>`);
      if (s.addr_suburb)    osmRows.push(`<div class="stat"><span class="k">${t('sch_area')}</span><span class="v">${s.addr_suburb}</span></div>`);
      if (s.website)        osmRows.push(`<div class="stat"><span class="k">${t('h_web')}</span><span class="v"><a href="${s.website}" target="_blank">${s.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32)}</a></span></div>`);
      if (s.wikidata)       osmRows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${s.wikidata}" target="_blank">${s.wikidata}</a></span></div>`);
      return `
        <h3>🏫 ${displayName} <span class="src-tag src-osm">OSM</span></h3>
        ${arSubtitle}
        ${osmRows.join('')}
        <div class="muted" style="font-size:11px;color:#888;margin-top:6px">${t('sch_not_in_khda')}</div>
      `;
    }
    const srcTag = '<span class="src-tag" style="background:#e6f7e6;color:#0a7f00">KHDA</span>';
    const rows = [];
    if (s.curriculum)  rows.push(`<div class="stat"><span class="k">${t('sch_curr')}</span><span class="v">${s.curriculum}</span></div>`);
    if (s.grade_range) rows.push(`<div class="stat"><span class="k">${t('sch_grade_range')}</span><span class="v">${s.grade_range}</span></div>`);
    if (s.area)        rows.push(`<div class="stat"><span class="k">${t('sch_area')}</span><span class="v">${s.area}</span></div>`);
    if (s.phone)       rows.push(`<div class="stat"><span class="k">${t('sch_phone')}</span><span class="v"><a href="tel:${s.phone}">${s.phone}</a></span></div>`);
    if (s.rating)      rows.push(`<div class="stat"><span class="k">${t('sch_rating')}</span><span class="v"><span class="rating ${_rcls(s.rating)}">${s.rating}</span></span></div>`);
    if (s.wellbeing)   rows.push(`<div class="stat"><span class="k">${t('sch_wellbeing')}</span><span class="v"><span class="rating ${_rcls(s.wellbeing)}">${s.wellbeing}</span></span></div>`);
    if (s.inclusion)   rows.push(`<div class="stat"><span class="k">${t('sch_inclusion')}</span><span class="v"><span class="rating ${_rcls(s.inclusion)}">${s.inclusion}</span></span></div>`);
    const detailsUrl = `https://web.khda.gov.ae/en/Education-Directory/Schools/School-Details?Id=${s.khda_id}&CenterID=${s.center_id}`;
    return `
      <h3>🏫 ${displayName} ${srcTag}</h3>
      ${arSubtitle}
      ${rows.join('')}
      <div style="margin-top:6px"><a href="${detailsUrl}" target="_blank" style="font-size:11px">KHDA School Details ↗</a></div>
    `;
  });
  m.addTo(schoolLayer);
}

// ===================== OTHER POI LAYERS (emoji icons) =====================
const POI_DEFS = {
};
const POI_LAYERS = {};
for (const [key, def] of Object.entries(POI_DEFS)) {
  const grp = L.layerGroup();
  for (const p of (POIS[key] || [])) {
    const icon = L.divIcon({className:'', html:`<div class="pin ${key}">${def.emoji}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
    const m = L.marker([p.lat, p.lon], {icon});
    const lines = [`<h3>${def.emoji} ${p.name || ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>`];
    lines.push(`<div class="muted" style="color:#888;margin-bottom:4px">${def.label}</div>`);
    if (p.op) lines.push(`<div class="stat"><span class="k">${t('uni_op')}</span><span class="v">${p.op}</span></div>`);
    if (p.kind) lines.push(`<div class="stat"><span class="k">${t('uni_op_type')}</span><span class="v">${p.kind}</span></div>`);
    if (p.start_date) lines.push(`<div class="stat"><span class="k">${t("pj_start")}</span><span class="v">${p.start_date}</span></div>`);
    m.bindPopup(lines.join(''));
    m.addTo(grp);
  }
  POI_LAYERS[key] = grp;
}

// ===================== UNIVERSITIES (enriched) =====================
const uniLayer = L.layerGroup();
const fmtAedU = v => v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString();
for (const u of UNIVERSITIES) {
  const icon = L.divIcon({className:'', html:`<div class="pin university">🎓</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([u.lat, u.lon], {icon});
  m.bindPopup(() => {
    const hasName = u.name && u.name !== '(unnamed)';
    const isAr = hasName && /[؀-ۿ]/.test(u.name);
    const titleAttr = isAr ? ' dir="rtl" style="text-align:right"' : '';
    const displayName = hasName ? `<span${titleAttr}>${u.name}</span>` : `<span style="color:#888">${t('no_name')}</span>`;
    const arSub = (u.name_ar && u.name_ar !== u.name)
      ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${u.name_ar}</div>`
      : '';
    const srcTag = u.in_khda
      ? '<span class="src-tag" style="background:#e6f7e6;color:#0a7f00">KHDA</span>'
      : '<span class="src-tag src-osm">OSM</span>';
    const rows = [];
    if (u.in_khda) {
      if (u.khda_area)        rows.push(`<div class="stat"><span class="k">${t('uni_city')}</span><span class="v">${u.khda_area}</span></div>`);
      if (u.khda_established) rows.push(`<div class="stat"><span class="k">${t('uni_established')}</span><span class="v">${u.khda_established}</span></div>`);
      if (u.khda_stars)       rows.push(`<div class="stat"><span class="k">${t('uni_khda_stars')}</span><span class="v"><span class="rating Verygood">${'★'.repeat(parseInt(u.khda_stars,10)||0)}${'☆'.repeat(5-(parseInt(u.khda_stars,10)||0))}</span> ${u.khda_rating_year ? `<span style="color:#888;font-size:11px">${u.khda_rating_year}</span>` : ''}</span></div>`);
    }
    if (u.operator)      rows.push(`<div class="stat"><span class="k">${t('uni_op')}</span><span class="v">${u.operator}</span></div>`);
    if (u.website)       rows.push(`<div class="stat"><span class="k">${t('uni_web')}</span><span class="v"><a href="${u.website}" target="_blank">${u.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32)}</a></span></div>`);
    if (u.wikipedia) {
      const wpUrl = 'https://' + u.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${wpUrl}" target="_blank">${u.wikipedia}</a></span></div>`);
    }
    if (u.wikidata && !u.wikipedia) rows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${u.wikidata}" target="_blank">${u.wikidata}</a></span></div>`);
    const detailsLink = u.khda_uni_id
      ? `<div style="margin-top:6px"><a href="https://web.khda.gov.ae/en/Education-Directory/Higher-Education/Higher-Education-Details?CenterID=${u.khda_uni_id}" target="_blank" style="font-size:11px">KHDA Details ↗</a></div>`
      : '';
    const notInKhdaNote = (!u.in_khda)
      ? `<div class="muted" style="font-size:11px;color:#888;margin-top:6px">${t('uni_not_in_khda')}</div>`
      : '';
    const khdaOnlyNote = (u.source === 'khda')
      ? `<div class="muted" style="font-size:11px;color:#888;margin-top:4px">${t('uni_khda_only_geocoded')}</div>`
      : '';
    return `
      <h3>🎓 ${displayName} ${srcTag}</h3>
      ${arSub}
      ${rows.join('')}
      ${khdaOnlyNote}
      ${notInKhdaNote}
      ${detailsLink}
    `;
  });
  m.addTo(uniLayer);
}

// ===================== MEDICAL (OSM hospitals + clinics + doctors) =====================
// One layer for all healthcare facilities. `kind` ∈ {hospital, clinic, doctors}
// is the only distinction — DLD has no medical data, DHA's facility list is
// behind a portal, so OSM tags are the source of truth.
const medicalLayer = L.layerGroup();
const MEDICAL_META = {
  hospital: {emoji: '🏥', pin: 'hospital', size: 24},
  clinic:   {emoji: '🩺', pin: 'clinic',   size: 20},
  doctors:  {emoji: '👨‍⚕️', pin: 'clinic',  size: 20},
};
for (const m of MEDICAL) {
  const meta = MEDICAL_META[m.kind] || MEDICAL_META.clinic;
  const icon = L.divIcon({
    className: '',
    html: `<div class="pin ${meta.pin}">${meta.emoji}</div>`,
    iconSize: [meta.size, meta.size],
    iconAnchor: [meta.size / 2, meta.size / 2],
  });
  const mk = L.marker([m.lat, m.lon], {icon});
  mk.bindPopup(() => {
    const rows = [];
    rows.push(`<div class="stat"><span class="k">${t('med_kind')}</span><span class="v">${t('med_kind_' + m.kind)}</span></div>`);
    if (m.emergency) {
      const yes = m.emergency === 'yes';
      rows.push(`<div class="stat"><span class="k">${t('h_emerg')}</span><span class="v" style="color:${yes ? '#0a7f00' : '#666'}">${yes ? t('yes_t') : t('no_t')}</span></div>`);
    }
    if (m.healthcare_speciality) {
      const specs = String(m.healthcare_speciality).split(';').map(s => s.trim()).filter(Boolean);
      rows.push(`<div class="stat"><span class="k">${t('h_specs_real')}</span><span class="v" style="text-align:right;max-width:200px;white-space:normal;font-size:11px">${specs.map(s => `<span class="lang-chip">${s}</span>`).join('')}</span></div>`);
    }
    if (m.operator) rows.push(`<div class="stat"><span class="k">${t('h_op')}</span><span class="v">${m.operator}</span></div>`);
    if (m.phone)    rows.push(`<div class="stat"><span class="k">${t('h_phone')}</span><span class="v"><a href="tel:${m.phone}">${m.phone}</a></span></div>`);
    if (m.website)  rows.push(`<div class="stat"><span class="k">${t('h_web')}</span><span class="v"><a href="${m.website}" target="_blank">${m.website.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 32)}</a></span></div>`);
    if (m.wikipedia) {
      const wpUrl = 'https://' + m.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g, '_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${wpUrl}" target="_blank">${m.wikipedia}</a></span></div>`);
    }
    if (m.opening_hours) rows.push(`<div class="stat"><span class="k">${t('ml_hours')}</span><span class="v" style="font-size:11.5px">${m.opening_hours}</span></div>`);
    if (m.addr_city)     rows.push(`<div class="stat"><span class="k">${t('h_city')}</span><span class="v">${m.addr_city}</span></div>`);
    return `
      <h3>${meta.emoji} ${m.name || ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>
      ${m.name_ar ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${m.name_ar}</div>` : ''}
      ${rows.join('')}
    `;
  });
  mk.addTo(medicalLayer);
}

// ===================== MOSQUES (enriched) =====================
const mosqueLayer = L.layerGroup();
for (const mo of MOSQUES) {
  const icon = L.divIcon({className:'', html:`<div class="pin mosque">🕌</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([mo.lat, mo.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  // Hide low-signal "denomination: sunni" (default for 99% of UAE mosques)
  if (mo.denomination && String(mo.denomination).toLowerCase() !== 'sunni') {
    realRows.push(`<div class="stat"><span class="k">${t("mo_denom")}</span><span class="v">${mo.denomination}</span></div>`);
  }
  if (mo.addr_street) realRows.push(`<div class="stat"><span class="k">${t("mo_street")}</span><span class="v">${mo.addr_street}</span></div>`);
  if (mo.addr_city) realRows.push(`<div class="stat"><span class="k">${t("mo_city")}</span><span class="v">${mo.addr_city}</span></div>`);
  if (mo.wheelchair) realRows.push(`<div class="stat"><span class="k">${t("mo_wheel")}</span><span class="v">${mo.wheelchair==='yes'?'✓ да':mo.wheelchair}</span></div>`);
  if (mo.image) realRows.push(`<div class="stat"><span class="k">${t("mo_image")}</span><span class="v"><a href="${mo.image}" target="_blank">${t("view_t")}</a></span></div>`);

  // Drop the synthetic "size" row — it duplicates capacity and "Mahalla" is untranslated.
  const synth = `
    <div class="stat"><span class="k">${t("mo_cap")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.capacity.toLocaleString('ru-RU')}</span></div>
    <div class="stat"><span class="k">${t("mo_khutbah")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.khutbah_langs.map(l=>`<span class="lang-chip">${l}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("mo_women")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.women_section?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_park")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.parking?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_classes")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.classes?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_iftar")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.iftar?t('yes_t'):t('no_t')}</span></div>
  `;
  return `
    <h3>🕌 ${mo.name || ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>
    ${mo.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${mo.name_ar}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    ${synth}
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("mo_warn")}</div>
  `;
});
  m.addTo(mosqueLayer);
}

// ===================== PROJECTS (RERA, aggregated per district) =====================
// One marker per master_project_en / area_name_en polygon — NOT per project.
// The badge shows the in-flight count; the popup breaks down by status,
// lists top developers, sums composition, and links to a per-district detail
// page (still a placeholder — page is being built separately).
//
// Source: Dubai Pulse dataset 467654 (RERA Real Estate Projects), refreshed
// via scripts/dld_projects_pull.py + dld_projects_merge_into_viewer.py.
const projectLayer = L.layerGroup();
const STATUS_META = {
  ACTIVE:                 {color: '#3aaf2f', key: 'pj_status_active'},
  NOT_STARTED:            {color: '#94a3b8', key: 'pj_status_not_started'},
  PENDING:                {color: '#f0a020', key: 'pj_status_pending'},
  CONDITIONAL_ACTIVATING: {color: '#7a4c00', key: 'pj_status_cond_activating'},
  FINISHED:               {color: '#1d4ed8', key: 'pj_status_finished'},
  CANCELLED:              {color: '#cc4040', key: 'pj_status_cancelled'},
  FRIEZED:                {color: '#7a4c00', key: 'pj_status_frozen'},
};
for (const d of PROJECTS) {
  // Badge size scales weakly with in-flight count so big districts look fuller.
  const n = d.in_flight;
  const size = n >= 100 ? 44 : n >= 30 ? 38 : 32;
  const icon = L.divIcon({
    className: '',
    html: `<div class="pin construction-cluster" style="width:${size}px;height:${size}px"><span class="pin-count">${n}</span><span class="pin-emoji">🏗️</span></div>`,
    iconSize: [size, size], iconAnchor: [size/2, size/2],
  });
  const m = L.marker([d.lat, d.lon], {icon});
  m.bindPopup(() => {
    const rows = [];

    // Status breakdown — show every non-zero count, coloured. In-flight
    // states first, then FINISHED/CANCELLED so the eye lands on what's
    // currently happening.
    const order = ['ACTIVE','NOT_STARTED','PENDING','CONDITIONAL_ACTIVATING','FINISHED','CANCELLED','FRIEZED'];
    const chips = [];
    for (const s of order) {
      const v = d.by_status[s] || 0;
      if (!v) continue;
      const meta = STATUS_META[s] || {color:'#888', key:'pj_status'};
      chips.push(`<span class="pj-status-chip" style="background:${meta.color}1a;color:${meta.color}">${t(meta.key)} · ${v}</span>`);
    }
    rows.push(`<div class="stat"><span class="k">${t('pj_count_by_status')}</span><span class="v" style="text-align:right;max-width:220px;display:flex;flex-wrap:wrap;gap:3px;justify-content:flex-end">${chips.join('')}</span></div>`);

    if (Number.isFinite(d.avg_percent)) {
      rows.push(`<div class="stat"><span class="k">${t('pj_avg_percent')}</span><span class="v" style="color:#3aaf2f">${d.avg_percent}%</span></div>`);
    }

    // Composition totals
    const comp = [];
    if (d.total_units > 0)     comp.push(`${d.total_units.toLocaleString('ru-RU')} ${t('pj_units_n')}`);
    if (d.total_villas > 0)    comp.push(`${d.total_villas.toLocaleString('ru-RU')} ${t('pj_villas_n')}`);
    if (d.total_buildings > 0) comp.push(`${d.total_buildings.toLocaleString('ru-RU')} ${t('pj_buildings_n')}`);
    if (d.total_lands > 0)     comp.push(`${d.total_lands.toLocaleString('ru-RU')} ${t('pj_lands_n')}`);
    if (comp.length) {
      rows.push(`<div class="stat"><span class="k">${t('pj_composition_total')}</span><span class="v" style="text-align:right;max-width:200px;font-size:11.5px">${comp.join(', ')}</span></div>`);
    }

    // Top developers — name is Arabic, render RTL.
    if (d.top_developers && d.top_developers.length) {
      const devLines = d.top_developers.slice(0, 5).map(([name, count]) =>
        `<div style="display:flex;justify-content:space-between;gap:8px;font-size:11.5px"><span dir="rtl" style="flex:1;text-align:right">${name}</span><span style="color:#888">${count}</span></div>`
      ).join('');
      rows.push(`<div class="stat"><span class="k">${t('pj_top_devs')}</span><span class="v" style="text-align:right;max-width:220px">${devLines}</span></div>`);
    }

    const geoNote = d.geocode_kind === 'area'
      ? `<div class="muted" style="margin-top:6px;font-size:11px;color:#888">${t('pj_geocode_area')}</div>`
      : '';
    const openAll = `<div style="margin-top:8px"><button class="pj-open-all" disabled title="${t('pj_open_all_soon')}">${t('pj_open_all')} (${d.total}) →</button></div>`;

    return `
      <h3>🏗️ ${d.name} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">RERA</span></h3>
      <div class="muted" style="color:#888;margin-bottom:4px;font-size:11.5px">${d.in_flight} ${t('pj_in_flight_label')} / ${d.total} ${t('pj_total_label')}</div>
      ${rows.join('')}
      ${geoNote}
      ${openAll}
    `;
  });
  m.addTo(projectLayer);
}

// ===================== MALLS (enriched) =====================
const mallLayer = L.layerGroup();
for (const ml of MALLS) {
  const icon = L.divIcon({className:'', html:`<div class="pin mall">🛍️</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([ml.lat, ml.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  if (ml.opening_hours) realRows.push(`<div class="stat"><span class="k">${t("ml_hours")}</span><span class="v" style="font-size:11.5px">${ml.opening_hours}</span></div>`);
  if (ml.operator) realRows.push(`<div class="stat"><span class="k">${t("ml_op")}</span><span class="v">${ml.operator}</span></div>`);
  if (ml.phone) realRows.push(`<div class="stat"><span class="k">${t("ml_phone")}</span><span class="v"><a href="tel:${ml.phone}">${ml.phone}</a></span></div>`);
  if (ml.website) realRows.push(`<div class="stat"><span class="k">${t("ml_web")}</span><span class="v"><a href="${ml.website}" target="_blank">${ml.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32)}</a></span></div>`);
  if (ml.wikipedia) {
    const wpUrl = 'https://' + ml.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
    realRows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${wpUrl}" target="_blank">${ml.wikipedia}</a></span></div>`);
  }
  if (ml.building_levels) realRows.push(`<div class="stat"><span class="k">${t("ml_levels")}</span><span class="v">${ml.building_levels}</span></div>`);
  if (ml.addr_city) realRows.push(`<div class="stat"><span class="k">${t("ml_city")}</span><span class="v">${ml.addr_city}</span></div>`);
  if (ml.wheelchair === 'yes') realRows.push(`<div class="stat"><span class="k">${t("ml_access")}</span><span class="v" style="color:#0a7f00">✓ wheelchair</span></div>`);

  const tierColor = ml.tier === 'A++' ? '#7a0fd4' : ml.tier === 'A' ? '#0a7f00' : ml.tier === 'B' ? '#b8590a' : '#666';
  // flags built lazily inside popup arrow
  const buildFlags = () => {
    const f = [];
    if (ml.hypermarket) f.push(t('flag_hyper'));
    if (ml.food_court) f.push(t('flag_food'));
    if (ml.cinema) f.push(t('flag_cinema'));
    if (ml.ice_rink) f.push(t('flag_ice'));
    if (ml.ski) f.push(t('flag_ski'));
    if (ml.parking_free) f.push(t('flag_parking_free'));
    return f;
  };
  return `
    <h3>🛍️ ${ml.name} <span class="src-tag src-osm">OSM</span></h3>
    ${ml.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${ml.name_ar}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    <div class="stat"><span class="k">${t("ml_size")} <span class="src-tag src-fake">~</span></span><span class="v"><span style="color:${tierColor};font-weight:600">${ml.size}</span> (${ml.tier})</span></div>
    <div class="stat"><span class="k">${t("ml_stores")} <span class="src-tag src-fake">~</span></span><span class="v">≈ ${ml.stores}</span></div>
    <div class="stat"><span class="k">${t("ml_anchors")} <span class="src-tag src-fake">~</span></span><span class="v" style="text-align:right;max-width:200px;font-size:11px">${ml.anchors.map(a=>`<span class="lang-chip">${a}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("ml_brands")} <span class="src-tag src-fake">~</span></span><span class="v" style="text-align:right;max-width:200px;font-size:11px">${ml.brands.map(b=>`<span class="lang-chip">${b}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("ml_staff_langs")} <span class="src-tag src-fake">~</span></span><span class="v">${ml.languages.map(l=>`<span class="lang-chip">${l}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("ml_footfall")} <span class="src-tag src-fake">~</span></span><span class="v">≈ ${ml.footfall_k}</span></div>
    <div style="margin-top:6px;font-size:11px;line-height:1.6">${buildFlags().map(f=>`<span class="lang-chip" style="background:#fffbe6;color:#7a4c00">${f}</span>`).join(' ')}</div>
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("ml_warn")}</div>
  `;
});
  m.addTo(mallLayer);
}


// ===================== POI TOGGLES (in middle panel) =====================
// Apply default mask (sales × all) — semantically identical to original
// baked-in values, also normalises real_med_price for legacy keys.
applyMask(currentMask, currentMaskPeriod, { pushUrl: false });
if (currentView === 'table') setView('table', { pushUrl: false, force: true });
// Built-in named layers
function poiBuiltinDefs() {
  return [
    {key:'metro',   label:t('metro_all'),     count:METRO_STATIONS.length, layer:metroLayer},
    {key:'schools', label:t('schools'),       count:SCHOOLS.length,        layer:schoolLayer},
    {key:'unis',    label:t('universities'),  count:UNIVERSITIES.length,   layer:uniLayer},
    {key:'medical', label:t('medical'),       count:MEDICAL.length,        layer:medicalLayer},
    {key:'mosques', label:t('mosques'),       count:MOSQUES.length,        layer:mosqueLayer},
    {key:'proj',    label:t('construction'),  count:PROJECTS.length,       layer:projectLayer},
    {key:'malls',   label:t('malls'),         count:MALLS.length,          layer:mallLayer},
  ];
}
function renderPoiList() {
  const el = document.getElementById('mp-poi-list');
  if (!el) return;
  const defs = poiBuiltinDefs();
  for (const [key, def] of Object.entries(POI_DEFS)) {
    defs.push({key:'poi-'+key, label:`${def.emoji} ${def.label}`, count:(POIS[key]||[]).length, layer:POI_LAYERS[key]});
  }
  el.innerHTML = defs.map((d,i) => {
    const checked = map.hasLayer(d.layer) ? 'checked' : '';
    return `<label data-i="${i}"><input type="checkbox" ${checked}><span class="poi-label">${d.label}</span><span class="poi-count">${d.count}</span></label>`;
  }).join('');
  el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    inp.addEventListener('change', () => {
      if (inp.checked) defs[i].layer.addTo(map);
      else map.removeLayer(defs[i].layer);
    });
  });
}
renderPoiList();

// First render
map.fitBounds(L.geoJSON(GEOJSON).getBounds(), {padding:[20,20]});


