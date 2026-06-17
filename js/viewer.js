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
function renderChoro(){
  const metric = 'real_count';
  const scale = 'log';
  const metricKey = currentPType==='villa' ? 'real_count_villa' : currentPType==='flat' ? 'real_count_flat' : 'real_count';
  const vs = GEOJSON.features.map(f => f.properties[metricKey] || (currentPType==='all' ? (f.properties.count || 0) : 0));
  const breaks = scale==='quantile'?qBreaks(vs,RAMP.length):scale==='log'?logBreaks(vs,RAMP.length):lBreaks(vs,RAMP.length);
  if(choro) map.removeLayer(choro);
  choro = L.geoJSON(GEOJSON,{
    filter: f => (f._level !== undefined ? f._level >= minLevel : true),
    style: f => {
      const v = (f.properties[metricKey] || (currentPType==='all' ? f.properties.count : 0) || 0), z = v===0;
      return {weight:0.6,color:'#1f2933',fillColor:z?'#dde3ea':RAMP[classify(v,breaks)],fillOpacity:z?0.25:0.7};
    },
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindPopup(() => {
        const sourceLabel = ({'osm-admin':'OSM admin_level=10','osm-place':'OSM place='+(p.kind||''),'osm-residential':'OSM landuse=residential'})[p.source] || 'OSM';
        const dldRow = '';
        const realRows = p.real_count ? `
          <div class="stat"><span class="k">${t("pp_trans_ytd")} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">DLD</span>${p.real_match_kind==='parent'?' <span class="src-tag" style="background:#fff5e6;color:#7a4c00">parent: '+p.real_parent_name+'</span>':''}</span><span class="v">${p.real_count.toLocaleString('ru-RU')}</span></div>
          <div class="stat"><span class="k">${t("pp_volume")}</span><span class="v">${(p.real_total_aed||0)>=1e9?((p.real_total_aed/1e9).toFixed(2)+' '+t('abbr_b')):((p.real_total_aed/1e6).toFixed(1)+' '+t('abbr_m'))}</span></div>
          <div class="stat"><span class="k">${t("pp_median")}</span><span class="v">${((p.real_med_price||0)/1e6).toFixed(2)} ${t('abbr_m')}</span></div>
          <div class="stat"><span class="k">${t("pp_median_psqm")}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')}</span></div>
          <div style="margin-top:8px"><button onclick='openDistrictByKey(${JSON.stringify(p.real_area_key)})' style="background:#0366d6;color:#fff;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600">${t("pp_open")}</button></div>
        ` : `
          <div class="stat"><span class="k">${t("pp_trans_placeholder")} <span class="src-tag src-fake">PLACEHOLDER</span></span><span class="v">${(p.count||0).toLocaleString('ru-RU')}</span></div>
          <div class="muted" style="font-size:11px;color:#888;margin-top:4px">${t("pp_no_csv")}</div>
        `;
        return `
          <h3>${p.name||'—'} <span class="src-tag src-osm">${sourceLabel}</span></h3>
          <div class="muted" style="margin-bottom:6px;color:#888">${p.name_ar||''}</div>
          ${dldRow}
          ${realRows}
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
  const fmt = METRIC_FMT[metric] || METRIC_FMT.count;
  const title = ({count:t('ch_count'),real_count:t('ch_count'),total_aed:t('pp_volume'),median_price_aed:t('pp_median'),avg_sqm:t('sc_area')})[metric] || t('ch_count');
  const all = [Math.min(...vs), ...breaks, Math.max(...vs)];
  let html = `<div style="font-weight:600;margin-bottom:4px">${title}</div>`;
  for(let i=0;i<RAMP.length;i++) html += `<div class="row"><span class="sw" style="background:${RAMP[i]}"></span>${fmt(all[i])} – ${fmt(all[i+1])}</div>`;
  html += `<div class="row"><span class="sw" style="background:#dde3ea;opacity:.5"></span>${t('legend_no_data')}</div>`;
  document.getElementById('legend').innerHTML = html;
}
// metric/scale selectors are hidden — listeners disabled
// document.getElementById('metric').addEventListener('change', renderChoro);
// document.getElementById('scale').addEventListener('change', renderChoro);

// ===================== METRO LINES + STATIONS =====================
// All metro lines and stations in a single toggle layer
const metroLayer = L.layerGroup();
for (const f of METRO_LINES.features) {
  L.geoJSON(f, {style: {color: f.properties.color, weight: 4, opacity: 0.9, dashArray: f.properties.status==='construction' ? '8,6' : null}}).addTo(metroLayer);
}
function getGroupLabel(g) { return ({red:t('metro_line_red'), green:t('metro_line_green'), blue:t('metro_line_blue')})[g]; }
const GROUP_PIN = {red:'metro-red', green:'metro-green', blue:'metro-blue'};
for (const s of METRO_STATIONS) {
  const groups = s.groups || [s.group];
  const labelLines = groups.map(g => getGroupLabel(g)).join(' / ');
  const isInterchange = groups.length > 1;
  // Render once per station, with the first group's colour (or red if multiple to highlight interchanges)
  const primary = groups[0];
  const icon = L.divIcon({className:'', html:`<div class="pin ${GROUP_PIN[primary]}">M</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => `
    <h3>🚇 ${s.name || t('station_default')} <span class="src-tag src-osm">OSM</span></h3>
    <div class="muted" style="color:#888;margin-bottom:4px">${labelLines}${isInterchange?(' · '+t('metro_interchange')):''}</div>
    ${s.line ? `<div class="stat"><span class="k">${t("metro_line")}</span><span class="v">${s.line}</span></div>` : ''}
  `);
  m.addTo(metroLayer);
}

// ===================== SCHOOLS (enriched) =====================
const schoolLayer = L.layerGroup();
const ratingColor = {Outstanding:'#0a7f00','Very good':'#3aaf2f',Good:'#90c443',Acceptable:'#f0a020',Weak:'#cc4040'};
const fmtAed = v => v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString();
for (const s of SCHOOLS) {
  const icon = L.divIcon({className:'', html:`<div class="pin school">🏫</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  const ratingClass = s.rating.replace(' ','');
  m.bindPopup(() => `
    <h3>🏫 ${s.name} <span class="src-tag src-fake">KHDA?</span></h3>
    <div class="stat"><span class="k">${t("sch_curr")}</span><span class="v">${s.curriculum}</span></div>
    <div class="stat"><span class="k">${t("sch_langs")}</span><span class="v">${s.languages.map(l=>`<span class="lang-chip">${l}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("sch_rating")}</span><span class="v"><span class="rating ${ratingClass}">${s.rating}</span></span></div>
    <div class="stat"><span class="k">${t("sch_fees")}</span><span class="v">${fmtAed(s.fee_low_aed)} – ${fmtAed(s.fee_high_aed)}</span></div>
    <div class="stat"><span class="k">${t("sch_capacity")}</span><span class="v">${s.capacity.toLocaleString('ru-RU')}</span></div>
    <div class="stat"><span class="k">${t("sch_enrol")}</span><span class="v">${s.enrolment.toLocaleString('ru-RU')} (${Math.round(s.enrolment/s.capacity*100)}%)</span></div>
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">⚠ Куррикулум/языки/цены — синтетика. Координаты и имя — OSM. Заменится из KHDA CSV.</div>
  `);
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
  const realRows = [];
  if (u.operator) realRows.push(`<div class="stat"><span class="k">${t("uni_op")}</span><span class="v">${u.operator}</span></div>`);
  if (u.operator_type) realRows.push(`<div class="stat"><span class="k">${t("uni_op_type")}</span><span class="v">${u.operator_type}</span></div>`);
  if (u.addr_city) realRows.push(`<div class="stat"><span class="k">${t("uni_city")}</span><span class="v">${u.addr_city}</span></div>`);
  if (u.website) realRows.push(`<div class="stat"><span class="k">${t("uni_web")}</span><span class="v"><a href="${u.website}" target="_blank">${u.website.replace(/^https?:\/\//,'').replace(/\/$/, '').slice(0,32)}</a></span></div>`);
  if (u.wikipedia) {
    const wpUrl = 'https://' + u.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
    realRows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${wpUrl}" target="_blank">${u.wikipedia}</a></span></div>`);
  }
  return `
    <h3>🎓 ${u.name} <span class="src-tag src-osm">OSM</span></h3>
    ${u.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${u.name_ar}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    <div class="stat"><span class="k">${t("uni_country")} <span class="src-tag src-fake">~</span></span><span class="v">${u.country_origin}</span></div>
    <div class="stat"><span class="k">${t("uni_progs")} <span class="src-tag src-fake">~</span></span><span class="v" style="text-align:right;max-width:170px">${u.programs.map(p=>`<span class="lang-chip">${p}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("uni_accred")} <span class="src-tag src-fake">~</span></span><span class="v">${u.accreditation}</span></div>
    <div class="stat"><span class="k">${t("uni_tuition")} <span class="src-tag src-fake">~</span></span><span class="v">${fmtAedU(u.tuition_low_aed)} – ${fmtAedU(u.tuition_high_aed)}</span></div>
    <div class="stat"><span class="k">${t("uni_students")} <span class="src-tag src-fake">~</span></span><span class="v">${u.students.toLocaleString('ru-RU')}</span></div>
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("uni_warn")}</div>
  `;
});
  m.addTo(uniLayer);
}

// ===================== HOSPITALS (enriched) =====================
const hospLayer = L.layerGroup();
const fmtAedH = v => v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString();
for (const h of HOSPITALS) {
  const icon = L.divIcon({className:'', html:`<div class="pin hospital">🏥</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([h.lat, h.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  if (h.emergency) {
    const yes = h.emergency === 'yes';
    realRows.push(`<div class="stat"><span class="k">${t("h_emerg")}</span><span class="v" style="color:${yes?'#0a7f00':'#666'}">${yes?t('yes_t'):t('no_t')}</span></div>`);
  }
  if (h.operator) realRows.push(`<div class="stat"><span class="k">${t("h_op")}</span><span class="v">${h.operator}</span></div>`);
  if (h.phone) realRows.push(`<div class="stat"><span class="k">${t("h_phone")}</span><span class="v"><a href="tel:${h.phone}">${h.phone}</a></span></div>`);
  if (h.website) realRows.push(`<div class="stat"><span class="k">${t("h_web")}</span><span class="v"><a href="${h.website}" target="_blank">${h.website.replace(/^https?:\/\//,'').replace(/\/$/, '').slice(0,32)}</a></span></div>`);
  if (h.wikipedia) {
    const wpUrl = 'https://' + h.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
    realRows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${wpUrl}" target="_blank">${h.wikipedia}</a></span></div>`);
  }
  if (h.addr_city) realRows.push(`<div class="stat"><span class="k">${t("h_city")}</span><span class="v">${h.addr_city}</span></div>`);
  if (h.real_specialties && h.real_specialties.length) {
    realRows.push(`<div class="stat"><span class="k">${t("h_specs_real")}</span><span class="v" style="text-align:right;max-width:170px">${h.real_specialties.map(s=>`<span class="lang-chip">${s}</span>`).join('')}</span></div>`);
  }
  return `
    <h3>🏥 ${h.name} <span class="src-tag src-osm">OSM</span></h3>
    ${h.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${h.name_ar}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    <div class="stat"><span class="k">${t("h_type")} <span class="src-tag src-fake">~</span></span><span class="v" style="color:${h.type==='Public'?'#1d4ed8':'#7a4c00'}">${h.type}</span></div>
    ${h.chain ? `<div class="stat"><span class="k">${t("h_chain")} <span class="src-tag src-fake">~</span></span><span class="v">${h.chain}</span></div>` : ''}
    <div class="stat"><span class="k">${t("h_specs")} <span class="src-tag src-fake">~</span></span><span class="v" style="text-align:right;max-width:170px">${h.specialties_synth.map(s=>`<span class="lang-chip">${s}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("h_doc_langs")} <span class="src-tag src-fake">~</span></span><span class="v">${h.languages.map(l=>`<span class="lang-chip">${l}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("h_ins")} <span class="src-tag src-fake">~</span></span><span class="v" style="text-align:right;max-width:180px;font-size:11px">${h.insurance.join(', ')}</span></div>
    <div class="stat"><span class="k">${t("h_beds")} <span class="src-tag src-fake">~</span></span><span class="v">${h.beds}</span></div>
    <div class="stat"><span class="k">${t("h_consult")} <span class="src-tag src-fake">~</span></span><span class="v">${fmtAedH(h.consult_fee_aed)}</span></div>
    <div class="stat"><span class="k">${t("h_jci")} <span class="src-tag src-fake">~</span></span><span class="v" style="color:${h.jci==='Yes'?'#0a7f00':'#666'}">${h.jci==='Yes'?'✓ да':'нет'}</span></div>
    <div class="stat"><span class="k">${t("h_dha")} <span class="src-tag src-fake">~</span></span><span class="v">${h.dha_rating}</span></div>
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("h_warn")}</div>
  `;
});
  m.addTo(hospLayer);
}

// ===================== MOSQUES (enriched) =====================
const mosqueLayer = L.layerGroup();
for (const mo of MOSQUES) {
  const icon = L.divIcon({className:'', html:`<div class="pin mosque">🕌</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([mo.lat, mo.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  if (mo.denomination) realRows.push(`<div class="stat"><span class="k">${t("mo_denom")}</span><span class="v">${mo.denomination}</span></div>`);
  if (mo.addr_street) realRows.push(`<div class="stat"><span class="k">${t("mo_street")}</span><span class="v">${mo.addr_street}</span></div>`);
  if (mo.addr_city) realRows.push(`<div class="stat"><span class="k">${t("mo_city")}</span><span class="v">${mo.addr_city}</span></div>`);
  if (mo.wheelchair) realRows.push(`<div class="stat"><span class="k">${t("mo_wheel")}</span><span class="v">${mo.wheelchair==='yes'?'✓ да':mo.wheelchair}</span></div>`);
  if (mo.image) realRows.push(`<div class="stat"><span class="k">${t("mo_image")}</span><span class="v"><a href="${mo.image}" target="_blank">${t("view_t")}</a></span></div>`);

  const synth = `
    <div class="stat"><span class="k">${t("mo_size")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.size_label}</span></div>
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

// ===================== PROJECTS (under construction, enriched) =====================
const projectLayer = L.layerGroup();
const fmtAedP = v => v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString();
for (const p of PROJECTS) {
  const icon = L.divIcon({className:'', html:`<div class="pin construction">🏗️</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([p.lat, p.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  if (p.building_type_osm) realRows.push(`<div class="stat"><span class="k">${t("pj_osm_building")}</span><span class="v">${p.building_type_osm}</span></div>`);
  if (p.levels) realRows.push(`<div class="stat"><span class="k">${t("pj_levels")}</span><span class="v">${p.levels}</span></div>`);
  if (p.height) realRows.push(`<div class="stat"><span class="k">${t("pj_height")}</span><span class="v">${p.height}</span></div>`);
  if (p.start_date) realRows.push(`<div class="stat"><span class="k">Старт</span><span class="v">${p.start_date}</span></div>`);
  if (p.operator) realRows.push(`<div class="stat"><span class="k">${t("pj_operator_osm")}</span><span class="v">${p.operator}</span></div>`);

  const cancelledBadge = p.cancelled ? '<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;background:#cc4040;color:#fff;margin-left:6px">CANCELLED</span>' : '';
  return `
    <h3>🏗️ ${p.name}${cancelledBadge} <span class="src-tag src-osm">OSM</span></h3>
    ${p.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${p.name_ar}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    <div class="stat"><span class="k">${t("pj_type")} <span class="src-tag src-fake">~</span></span><span class="v">${p.ptype}</span></div>
    <div class="stat"><span class="k">${t("pj_dev")} <span class="src-tag src-fake">~</span></span><span class="v">${p.developer}</span></div>
    ${p.mix_label!=='—' ? `<div class="stat"><span class="k">${t("pj_mix")} <span class="src-tag src-fake">~</span></span><span class="v">${p.mix_label}</span></div>` : ''}
    ${p.units ? `<div class="stat"><span class="k">${t("pj_units")} <span class="src-tag src-fake">~</span></span><span class="v">${p.units.toLocaleString('ru-RU')}</span></div>` : ''}
    ${p.handover_year ? `<div class="stat"><span class="k">${t("pj_handover")} <span class="src-tag src-fake">~</span></span><span class="v">${p.handover_year}</span></div>` : ''}
    <div class="stat"><span class="k">${t("pj_sale_status")} <span class="src-tag src-fake">~</span></span><span class="v" style="color:${p.cancelled?'#cc4040':p.sale_status==='Sold out'?'#0a7f00':'#b8590a'}">${p.sale_status}</span></div>
    ${p.price_from_aed ? `<div class="stat"><span class="k">${t("pj_price_from")} <span class="src-tag src-fake">~</span></span><span class="v">${fmtAedP(p.price_from_aed)} AED</span></div>` : ''}
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("pj_warn")}</div>
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
renderChoro();
// Built-in named layers
function poiBuiltinDefs() {
  return [
    {key:'metro',   label:t('metro_all'),     count:METRO_STATIONS.length, layer:metroLayer},
    {key:'schools', label:t('schools'),       count:SCHOOLS.length,        layer:schoolLayer},
    {key:'unis',    label:t('universities'),  count:UNIVERSITIES.length,   layer:uniLayer},
    {key:'hosps',   label:t('hospitals'),     count:HOSPITALS.length,      layer:hospLayer},
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


