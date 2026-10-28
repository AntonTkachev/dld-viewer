// Map viewer: district data prep, mask state, page URL state, district search.
const PARENT_OVERRIDES = {
  'The Gardens':                          { parent_key: 'discovery gardens',  parent_name: 'Discovery Gardens' },
  'Jebel Ali Village':                    { parent_key: 'jabal ali first',    parent_name: 'Jabal Ali First' },
  'Al Jaddaf':                            { parent_key: 'sama al jadaf',      parent_name: 'Sama Al Jadaf' },
  'Nakhlat Jabal Ali':                    { parent_key: 'palm jabal ali',     parent_name: 'Palm Jabal Ali' },
  'Port Rashid':                          { parent_key: 'mina rashid',        parent_name: 'Mina Rashid' },
  'Al Ruwayyah 1':                        { parent_key: 'al rowaiyah first',  parent_name: 'Al Rowaiyah First' },
  'Al Ruwayyah 2':                        { parent_key: 'al rowaiyah first',  parent_name: 'Al Rowaiyah First' },
  'Al Ruwayyah 3':                        { parent_key: 'al rowaiyah first',  parent_name: 'Al Rowaiyah First' },
  'Al Barsha South 5':                    { parent_key: 'jumeirah village triangle', parent_name: 'Jumeirah Village Triangle' },
  'Wadi Al Safa 6':                       { parent_key: 'arabian ranches i',  parent_name: 'Arabian Ranches I' },
  'Dubai International Financial Centre': { parent_key: 'zaabeel second',     parent_name: 'Zaabeel Second' },
  'Emaar Beachfront':                     { parent_key: 'dubai harbour',      parent_name: 'Dubai Harbour' },
  'Downtown Dubai':                       { parent_key: 'burj khalifa',       parent_name: 'Burj Khalifa' },
  'Expo City Dubai':                      { parent_key: 'madinat al mataar',  parent_name: 'Madinat Al Mataar' },
  'Zabeel':                               { parent_key: 'zaabeel second',     parent_name: 'Zaabeel Second' },
  'Trade Centre':                         { parent_key: 'trade center second', parent_name: 'Trade Center Second' },
};
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

let currentMask = (typeof window !== 'undefined' && window.__INITIAL_MASK__ && MASKS[window.__INITIAL_MASK__]) ? window.__INITIAL_MASK__ : 'sales';
let _maskMoreExpanded = SECONDARY_MASKS.includes(currentMask);
let currentMaskPeriod = (typeof window !== 'undefined' && window.__INITIAL_PERIOD__ && MASKS[currentMask] && MASKS[currentMask].periods.includes(window.__INITIAL_PERIOD__)) ? window.__INITIAL_PERIOD__ : 'all';
let currentView = (typeof window !== 'undefined' && window.__INITIAL_VIEW__ === 'table') ? 'table' : 'map';

const _tableState = {};  

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

const _MASK_FIELDS = [
  'real_count','real_total_aed','real_med_price','real_med_ppsqm',
  'real_metric','real_med_then_ppsqm','real_n_sale','real_n_rent','real_fallback_yrs',
  'real_price_pct','real_rent_pct','real_pipeline','real_units_active','real_n_overdue',
  'real_post_launch',
  'real_strategy','real_yield','real_past1y','real_offplan_ppsqm','real_premium',
  'real_fresh','real_overdue','real_n_offplan','real_vs_peak','real_rent_trend',
  'real_renewal','real_net_yield','real_n_checks','real_checks',
  'real_n_op','real_n_rd','real_op_share','real_op_win','real_op_why','real_h_n','real_h_med','real_h_paid',
];

const _MASK_FIELDS_NULLABLE = new Set([
  'real_metric', 'real_fallback_yrs', 'real_price_pct', 'real_rent_pct',
  'real_strategy', 'real_yield', 'real_past1y', 'real_premium',
  'real_fresh', 'real_overdue', 'real_vs_peak', 'real_rent_trend', 'real_renewal',
  'real_net_yield', 'real_n_checks',
  'real_op_share', 'real_op_win', 'real_op_why', 'real_h_n', 'real_h_med', 'real_h_paid',
]);
function _resetMaskFields(p) {
  for (const f of _MASK_FIELDS) p[f] = _MASK_FIELDS_NULLABLE.has(f) ? null : 0;
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
  if (typeof _refreshViewSwitchLabel === 'function') _refreshViewSwitchLabel();
  if (view === 'table') {
    renderTable();

    if (typeof map !== 'undefined' && map.invalidateSize) {
      setTimeout(() => map.invalidateSize(), 50);
    }
  } else if (typeof map !== 'undefined' && map.invalidateSize) {

    setTimeout(() => map.invalidateSize(), 50);
    _declutterTicks(document.getElementById('legend'));
  }
  if (typeof renderMaskList === 'function') renderMaskList();
  if (typeof updateMaskCurrentLabel === 'function') updateMaskCurrentLabel();
  if (opts.pushUrl !== false) _pushPageUrl(currentMask, view);
}

const _SEO_MASKS = ['sales', 'rents', 'growth', 'payback', 'lifecycle', 'investor', 'income', 'formula', 'offplan'];

function _isSeoMask(m) { return _SEO_MASKS.indexOf(m) !== -1; }

function _currentPageState() {
  const p = (typeof window !== 'undefined' ? window.location.pathname : '') || '';
  for (const m of _SEO_MASKS) {
    if (new RegExp('/' + m + '/table/(index\\.html)?$').test(p)) return { mask: m, view: 'table' };
    if (new RegExp('/' + m + '/(index\\.html)?$').test(p))       return { mask: m, view: 'map' };
  }
  return { mask: null, view: 'map' };
}

function _hrefForPage(targetMask, targetView) {
  targetView = targetView || 'map';
  const cur = _currentPageState();
  if (cur.mask === targetMask && cur.view === targetView) return null;
  
  const upSteps = (cur.mask ? 1 : 0) + (cur.view === 'table' ? 1 : 0);
  let rel = upSteps ? '../'.repeat(upSteps) : './';
  rel += targetMask + '/';
  if (targetView === 'table') rel += 'table/';

  if (typeof window !== 'undefined' && window.location.protocol === 'file:') rel += 'index.html';
  try { return new URL(rel, window.location.href).href; } catch (e) { return null; }
}

function _pushPageUrl(maskId, view) {
  view = view || 'map';
  if (!_isSeoMask(maskId)) return;
  const cur = _currentPageState();
  if (cur.mask === maskId && cur.view === view) return;
  let href = _hrefForPage(maskId, view);
  if (!href) return;
  
  if (window.location.protocol === 'file:') { window.location.href = href; return; }
  const layers = new URLSearchParams(window.location.search).get('layers');
  if (layers) { const u = new URL(href); u.searchParams.set('layers', layers); href = u.href; }
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

  if (typeof _applyLayersFromUrl === 'function') _applyLayersFromUrl();
});

const _SEARCH_ALIASES = {
  'dubai harbour':             ['emaar beachfront', 'emaar beach front'],
  'madinat dubai almelaheyah': ['mina rashid', 'rashid yachts', 'rashid yachts and marina'],
  'um suqaim third':           ['madinat jumeirah living', 'mjl'],
};

let _searchIndex = null;
function _buildSearchIndex(){
  return GEOJSON.features
    .filter(f => f.properties.name)
    .map(f => ({
      name:    f.properties.name,
      nameAr:  f.properties.name_ar || '',
      aliases: _SEARCH_ALIASES[f.properties.key] || [],
      rc:      f.properties.real_count || 0,
      level:   f._level || 0,
      feat:    f,
    }))
    .sort((a,b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
}
// Buildings are ALL CAPS in DLD, mixed case from OSM — title-case the
// shouty ones for readability, same normalization the blog uses.
function _bldDisplayName(n) {
  return n === n.toUpperCase() ? n.replace(/\w\S*/g, w => w[0] + w.slice(1).toLowerCase()) : n;
}
let _buildingSearchIndex = null;
function _buildBuildingSearchIndex(){
  if (typeof BUILDINGS === 'undefined') return [];
  return BUILDINGS
    .filter(b => b.s) // only buildings a search slug actually resolves
    .map(b => ({name: b.n, display: _bldDisplayName(b.n), area: b.a || '', slug: b.s}))
    .sort((a,b) => a.display.toLowerCase().localeCompare(b.display.toLowerCase()));
}
function _renderSearchResults(query){
  if (!_searchIndex) _searchIndex = _buildSearchIndex();
  const q = (query||'').toLowerCase().trim();
  let districts = _searchIndex;
  if (q) {
    districts = _searchIndex.filter(x =>
      x.name.toLowerCase().includes(q) ||
      (x.nameAr && x.nameAr.includes(query)) ||
      x.aliases.some(a => a.includes(q)));

    districts.sort((a,b) => {
      const nameMatch = n => n.toLowerCase().startsWith(q) ? 0 : 1;
      const aliasMatch = x => x.aliases.some(a => a.startsWith(q)) ? 0 : 1;
      const ap = Math.min(nameMatch(a.name), aliasMatch(a));
      const bp = Math.min(nameMatch(b.name), aliasMatch(b));
      if (ap !== bp) return ap - bp;
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });
    districts = districts.slice(0, 10);
  }

  // Buildings only join in once there's an actual query — browsing all
  // ~2,400 of them isn't useful the way browsing the district list is.
  let buildings = [];
  if (q) {
    if (typeof BUILDINGS === 'undefined') {
      // re-render once data arrives, if the query is still the same
      _ensureBuildingsData().then(() => {
        const inp = document.getElementById('search-input');
        if (inp && inp.value.toLowerCase().trim() === q) _renderSearchResults(inp.value);
      });
    } else {
      if (!_buildingSearchIndex) _buildingSearchIndex = _buildBuildingSearchIndex();
      buildings = _buildingSearchIndex.filter(x => x.name.toLowerCase().includes(q));
      buildings.sort((a,b) => {
        const nameMatch = n => n.toLowerCase().startsWith(q) ? 0 : 1;
        const ap = nameMatch(a.name), bp = nameMatch(b.name);
        if (ap !== bp) return ap - bp;
        return a.display.toLowerCase().localeCompare(b.display.toLowerCase());
      });
      buildings = buildings.slice(0, 10);
    }
  }

  const el = document.getElementById('search-results');
  if (!el) return;
  if (!districts.length && !buildings.length) {
    el.innerHTML = `<div class="sr-empty">${t('search_empty')}</div>`;
    return;
  }

  let html = '';
  if (districts.length) {
    html += `<div class="sr-group">${_h(t('search_group_districts'))}</div>` + districts.map((x, i) =>
      `<div class="sr-item" data-kind="district" data-i="${i}"><span class="sr-name">${_h(x.name)}</span><span class="sr-meta">L${x.level|0}${x.rc?(' · '+x.rc.toLocaleString('ru-RU')):''}</span></div>`
    ).join('');
  }
  if (buildings.length) {
    html += `<div class="sr-group">${_h(t('search_group_buildings'))}</div>` + buildings.map((x, i) =>
      `<div class="sr-item" data-kind="building" data-i="${i}"><span class="sr-name">${_BLD_ICON_SVG}${_h(x.display)}</span><span class="sr-meta">${_h(x.area)}</span></div>`
    ).join('');
  }
  el.innerHTML = html;

  el.querySelectorAll('.sr-item[data-kind="district"]').forEach((it, i) => {
    it.addEventListener('click', () => _onSearchSelect(districts[i].feat));
  });
  el.querySelectorAll('.sr-item[data-kind="building"]').forEach((it, i) => {
    it.addEventListener('click', () => _onSearchSelectBuilding(buildings[i].slug));
  });
}
function _onSearchSelect(feat){
  if (feat._level !== undefined && feat._level < minLevel) _switchLevel(0);
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

  if (typeof _setSelected === 'function') _setSelected(feat);
}
function _onSearchSelectBuilding(slug){
  const entry = _bldShapes.get(slug);
  if (!entry) return;
  const {shape, b} = entry;
  _switchLevel(99);
  document.getElementById('mp-search').classList.remove('open');
  map.once('moveend', () => shape.openPopup());
  map.flyTo([b.lat, b.lon], 17, {duration: 0.6});
}
