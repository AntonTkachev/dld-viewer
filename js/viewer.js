// Wire buttons (deferred until DOM exists)
setTimeout(() => {
  // Lang buttons — wired later (see "Lang switcher" block at the bottom of
  // this setTimeout) so the navigation handler is the ONLY one attached.
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
  // Boot language: window.__INITIAL_LANG__ > URL prefix > ?lang= > default.
  let _bootLang = currentLang;
  try {
    if (typeof window.__INITIAL_LANG__ === 'string'
        && typeof I18N !== 'undefined' && I18N[window.__INITIAL_LANG__]) {
      _bootLang = window.__INITIAL_LANG__;
    } else {
      // Strip the project subpath (_BASE_PATH, e.g. /dld-viewer) before
      // matching the /(en|ar|hi|zh)/ language prefix — on GH Pages project
      // sites the path is /dld-viewer/en/sales/, not /en/sales/.
      const _pPath = ((window.location.pathname || '').slice(_BASE_PATH.length)) || '/';
      const pm = _pPath.match(/^\/(en|ar|hi|zh)(?:\/|$)/);
      if (pm && typeof I18N !== 'undefined' && I18N[pm[1]]) {
        _bootLang = pm[1];
      } else {
        const qp = new URLSearchParams(window.location.search).get('lang');
        if (qp && typeof I18N !== 'undefined' && I18N[qp]) _bootLang = qp;
      }
    }
  } catch (e) { /* sandbox / file:// edge — ignore */ }
  applyLang(_bootLang);

  // Inline hint above the table — explains the dual click behavior
  // (name = navigate to district page, row = fly to on map). Text is
  // translated and only set on boot (lang switch in table view is hidden).
  const tvHintEl = document.getElementById('tv-hint');
  if (tvHintEl) tvHintEl.textContent = t('tv_hint');

  // Lang switcher (middle panel) — navigate to /<newlang>/<mask>/[table/]
  // instead of just re-rendering labels in place. Preserves ?layers=… so
  // active POI overlays survive a language switch.
  document.querySelectorAll('#mp-lang-list .lang-btn').forEach(b => {
    b.addEventListener('click', e => {
      const target = b.dataset.lang;
      if (!target || target === currentLang) return;
      if (typeof _navigateToLang === 'function') {
        e.stopPropagation();
        _navigateToLang(target);
      }
    }, true);
  });

}, 0);


// ===================== DETAIL NAVIGATION =====================
// Click on a polygon / popup button / table row resolves district slug
// + current language and navigates to the per-district page.
function _slugify(s) {
  return (s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}
// XSS guards: `_h` HTML-escapes text + attribute values; `_safeUrl`
// whitelists http(s)/tel/mailto for href/src and drops anything else.
function _h(s) {
  return String(s == null ? '' : s).replace(/[&<>"'`]/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;', '`':'&#96;',
  })[c]);
}
function _safeUrl(u) {
  const s = String(u == null ? '' : u).trim();
  // /^scheme:/ is intentionally case-insensitive; "JaVaScRiPt:" is a known
  // bypass on filters that only check lowercase.
  if (/^(https?|tel|mailto):/i.test(s)) return s;
  // Same-origin relative paths \u2014 used by the popup "Open" button to navigate
  // to /sales/<slug>/. Allowed because the URL is generated by us, not by
  // any external POI / OSM author free-form input.
  // Reject `//evil.com/x` (protocol-relative \u2014 browser resolves to current
  // scheme + evil host) and `javascript:` / `data:` / etc.
  if (/^\/[^/]/.test(s) || s === '/') return s;
  // Protocol-relative (//evil.com/x) is denied \u2014 looks like a path but the
  // browser would resolve it against the current scheme + evil host.
  return '#';
}
// Auto-detected project subpath. Empty when served at the host root (custom
// domain, local http.server from the repo); '/dld-viewer' when served as a
// GH Pages project page.
//
// Inverted whitelist on purpose \u2014 we trust host root by default and ONLY
// promote known project-subpath names into _BASE_PATH. The previous design
// listed every content root and treated anything else as a project subpath,
// which silently broke every URL in the app the moment someone added a new
// top-level dir (/blog/, a new POI category, \u2026). With the inversion you
// have to opt a subpath in, so growth doesn't yield surprises.
const _PROJECT_SUBPATHS = new Set(['dld-viewer']);
const _BASE_PATH = (() => {
  if (typeof window === 'undefined') return '';
  const first = ((window.location.pathname || '').split('/').filter(Boolean)[0] || '');
  return _PROJECT_SUBPATHS.has(first) ? '/' + first : '';
})();
function _langUrlPrefix() {
  return _BASE_PATH + ((typeof currentLang === 'string' && currentLang !== 'ru') ? '/' + currentLang : '');
}
function _langUrlPrefixOf(lang) {
  return _BASE_PATH + ((lang && lang !== 'ru') ? '/' + lang : '');
}
// Navigate to the same mask/view in a different language, preserving
// ?layers= and any other relevant query state.
function _navigateToLang(targetLang) {
  if (!targetLang || typeof window === 'undefined') return;
  // Strip an existing /(en|ar|hi|zh)/ prefix from the current path to expose
  // the bare path (/sales/, /rents/table/, /metro/, …) — then prepend the
  // new language prefix. Also strip _BASE_PATH first (e.g. /dld-viewer)
  // so the regex against /en/, /ar/, /hi/, /zh/ matches on GH Pages.
  const p = (window.location.pathname || '/').slice(_BASE_PATH.length) || '/';
  let stripped = p.replace(/^\/(en|ar|hi|zh)(?=\/|$)/, '') || '/';
  // No /<lang>/index.html exists — only /<lang>/<mask>/ landings. The root
  // viewer (/, /index.html, /<lang>/) is effectively the sales landing in
  // RU; route the lang switch there so we don't land on a directory listing.
  if (stripped === '/' || stripped === '/index.html') {
    stripped = '/sales/';
  }
  const newPath = _langUrlPrefixOf(targetLang) + stripped;
  let url;
  try { url = new URL(newPath + window.location.search + window.location.hash, window.location.origin); }
  catch (e) { window.location.href = newPath; return; }
  // Drop a legacy ?lang=… now that language is encoded in the path.
  try { url.searchParams.delete('lang'); } catch (e) { /* ignore */ }
  window.location.href = url.pathname + (url.search || '') + (url.hash || '');
}
function _districtModePrefix(mask) {
  // Per-district pages exist only for sales + rents. growth/payback land on /sales/.
  return (mask === 'rents') ? 'rents' : 'sales';
}
function _districtHrefForKey(key, name, legacyKey, masterKey) {
  if (!key || key === '__dubai__') return _langUrlPrefix() + '/';
  // Mode-aware lookup: probe the current-mode aggregate first; fall through
  // to the other mode if the key isn't there (and route accordingly).
  // Probe order per side: polygon key → masterKey → legacyKey.
  const hasReal = (a, k) => a && a[k] && a[k].name && !a[k]._isStub;
  const mode = _districtModePrefix(typeof currentMask !== 'undefined' ? currentMask : 'sales');
  const PRIMARY   = (mode === 'rents' && typeof RENT_AGGREGATES !== 'undefined') ? RENT_AGGREGATES : (typeof AGGREGATES !== 'undefined' ? AGGREGATES : null);
  const SECONDARY = (mode === 'rents' && typeof AGGREGATES      !== 'undefined') ? AGGREGATES      : (typeof RENT_AGGREGATES !== 'undefined' ? RENT_AGGREGATES : null);
  const probes = [key, masterKey, legacyKey].filter(Boolean);
  let display = null, finalMode = mode;
  for (const probe of probes) {
    if (hasReal(PRIMARY, probe)) { display = PRIMARY[probe].name; break; }
  }
  if (!display) {
    for (const probe of probes) {
      if (hasReal(SECONDARY, probe)) {
        display = SECONDARY[probe].name;
        // Switch the URL to the mode whose aggregate matched, so we never
        // route to a /<mode>/<slug>/ page that doesn't exist for that mode.
        finalMode = (SECONDARY === AGGREGATES) ? 'sales' : 'rents';
        break;
      }
    }
  }
  if (!display) display = name || key;
  const slug = _slugify(display);
  return _langUrlPrefix() + '/' + finalMode + '/' + slug + '/';
}
// Open a district: navigate to the SEO page at /<lang>/<mode>/<slug>/.
window.openDistrictByKey = function(key) {
  window.location.href = _districtHrefForKey(key);
};
window.openDubai = function() { /* Dubai-wide overview moved off the slide-out panel; no-op for now. */ };
function openDistrict(props) {
  if (!props) return;
  const href = _districtHrefForKey(props.real_area_key, props.name, props.legacy_area_key, props.master_project_key);
  if (href) window.location.href = href;
}

// ===================== MAP =====================
// SVG pattern defs for the no-data hatched fill. Injected into the document
// (not Leaflet's overlay <svg>) so url(#nodata-hatch) resolves the moment any
// path is rendered, regardless of pane creation order.
document.body.insertAdjacentHTML('beforeend',
  '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
  + '<defs>'
  + '<pattern id="nodata-hatch" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">'
  +   '<line x1="0" y1="0" x2="0" y2="8" stroke="#94a3b8" stroke-width="1.4"/>'
  + '</pattern>'
  + '</defs></svg>');

const map = L.map('map', { zoomControl: false }).setView([25.12, 55.25], 10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
  maxZoom: 19,
}).addTo(map);

// ===================== CHOROPLETH =====================
const LIFECYCLE_PHASE_COLORS = {
  rising:     '#fde725',
  active:     '#21918c',
  mature:     '#5ec962',
  lagging:    '#3b528b',
  overheated: '#440154',
};
const LIFECYCLE_PHASE_TEXT = {
  rising:     '#0f172a',
  active:     '#ffffff',
  mature:     '#0f172a',
  lagging:    '#ffffff',
  overheated: '#ffffff',
};
const LIFECYCLE_PHASE_ORDER = ['rising', 'active', 'mature', 'lagging', 'overheated'];
function _lifecyclePhase(rec) {
  return (rec && rec.phase) ? rec.phase : null;
}

const RAMP_VIRIDIS = ['#440154','#3b528b','#21918c','#5ec962','#fde725'];
const RAMP_BLUE    = ['#eaf2fb','#b8d0f0','#7da4e2','#3f73d4','#1d4ed8'];
const RAMP_GREEN   = ['#ebf6ee','#b6dcc2','#7bc090','#3a9a55','#188a37'];
const _PALETTE_KEY = 'dxbc_choro_palette';
const _PALETTES = {viridis: RAMP_VIRIDIS, blue: RAMP_BLUE, green: RAMP_GREEN};
const _PALETTE_ORDER = ['viridis', 'blue', 'green'];
let _paletteName = _PALETTES[localStorage.getItem(_PALETTE_KEY)] ? localStorage.getItem(_PALETTE_KEY) : 'viridis';
let RAMP = _PALETTES[_paletteName];
window.togglePalette = function() {
  const next = _PALETTE_ORDER[(_PALETTE_ORDER.indexOf(_paletteName) + 1) % _PALETTE_ORDER.length];
  _paletteName = next;
  RAMP = _PALETTES[next];
  localStorage.setItem(_PALETTE_KEY, next);
  if (typeof renderChoro === 'function') renderChoro();
};
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

// Manual parent-fallback for polygons without a direct CSV row — route them
// to the bucket where deals are actually counted.
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
const _LIFECYCLE = (typeof LIFECYCLE       !== 'undefined') ? LIFECYCLE       : {};
const _PAYBACK_P = (typeof PAYBACK_PERIODS !== 'undefined') ? PAYBACK_PERIODS : {};

// Stub aggregates for split sub-zone keys that don't exist in the rich
// legacy AGGREGATES bucket — keeps the "Open details" path alive.
// Fill in a minimal shape so renderBodySale/Rent render with empty timelines
// and empty tables instead of crashing.
(function _stubSplitAggregates() {
  const EMPTY_BUCKET = {n:0,total:0,med:0,mean:0,p25:0,p75:0,p90:0,med_sqm:0,med_ppsqm:0};
  function stubSale(r) {
    return {
      name: r.name || '', n: r.n || 0, total: r.total || 0,
      med: r.med || 0, mean: r.med || 0,
      p25: 0, p75: 0, p90: 0,
      med_sqm: r.med_sqm || 0, med_ppsqm: r.med_ppsqm || 0,
      avg_per_day: 0,
      flat: {...EMPTY_BUCKET}, villa: {...EMPTY_BUCKET},
      commercial: {...EMPTY_BUCKET}, land: {...EMPTY_BUCKET},
      rooms_flat: {}, rooms_villa: {}, offplan: {},
      timeline: [], top_projects: [], top_deals: [], recent: [],
      _isStub: true,
    };
  }
  function stubRent(r) {
    return {
      name: r.name || '', n: r.n || 0,
      med: r.med || 0, med_annual: r.med || 0, mean: r.med || 0,
      p25: 0, p75: 0, p90: 0,
      med_sqm: r.med_sqm || 0, med_ppsqm: r.med_ppsqm || 0,
      ejari: {}, rooms: {}, timeline: [], top_projects: [], recent: [],
      _isStub: true,
    };
  }
  if (typeof AGGREGATES !== 'undefined') {
    const tx = (_TX_P && _TX_P.all) || {};
    for (const k of Object.keys(tx)) {
      if (!AGGREGATES[k]) AGGREGATES[k] = stubSale(tx[k]);
    }
  }
  if (typeof RENT_AGGREGATES !== 'undefined') {
    const rt = (_RENTS_P && _RENTS_P.all) || {};
    for (const k of Object.keys(rt)) {
      if (!RENT_AGGREGATES[k]) RENT_AGGREGATES[k] = stubRent(rt[k]);
    }
  }
})();
const MASKS = {
  sales: {
    labelKey: 'mask_sales', descKey: 'mask_sales_desc',
    periods: ['1y','3y','5y','10y','all'], defaultPeriod: 'all',
    // typeof guard: AGGREGATES ships as an external <script src>; if it
    // 404s the page falls back to period-only data instead of crashing.
    data: {
      all:   Object.assign({}, (typeof AGGREGATES !== 'undefined' ? AGGREGATES : {}), _TX_P['all'] || {}),
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
      // Same overlay pattern as sales — _RENTS_P['all'] adds the split keys.
      //
      all:   Object.assign({},
              (typeof RENT_AGGREGATES !== 'undefined') ? RENT_AGGREGATES : {},
              _RENTS_P['all'] || {}),
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
      <div class="stat"><span class="k">${t('pp_growth_pct')}</span><span class="v" style="font-weight:700">${p.real_metric >= 0 ? '+' : ''}${p.real_metric.toFixed(1)}%</span></div>
      <div class="stat"><span class="k">${t('pp_med_now_psqm')}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')}</span></div>
      <div class="stat"><span class="k">${t('pp_med_then_psqm')}</span><span class="v">${(p.real_med_then_ppsqm||0).toLocaleString('ru-RU')}</span></div>
      ${fb}
      <div class="stat"><span class="k">${t('pp_trans_ytd_growth')}</span><span class="v">${p.real_count.toLocaleString('ru-RU')}</span></div>
    `;
    },
    tableColumns: [
      { key: 'name',         labelKey: 'tv_col_district',    type: 'str',     width: '30%' },
      { key: 'growth_pct',   labelKey: 'tv_col_growth_pct',  type: 'pct',     width: '14%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'med_now',      labelKey: 'tv_col_med_now',     type: 'int',     width: '18%' },
      { key: 'med_then',     labelKey: 'tv_col_med_then',    type: 'int',     width: '18%' },
      { key: 'n',            labelKey: 'tv_col_n_last_year', type: 'int',     width: '20%' },
    ],
  },
  lifecycle: {
    labelKey: 'mask_lifecycle', descKey: 'mask_lifecycle_desc',
    periods: ['all'], defaultPeriod: 'all',
    data: { all: _LIFECYCLE },
    pluck: r => ({
      real_count: r.n_active || 0,
      real_total_aed: 0,
      real_med_price: 0,
      real_med_ppsqm: 0,
      real_metric: (typeof r.vitality === 'number') ? r.vitality * 100 : null,
      real_phase: _lifecyclePhase(r),
      real_price_pct: (typeof r.price_pct === 'number') ? r.price_pct : null,
      real_rent_pct:  (typeof r.rent_pct  === 'number') ? r.rent_pct  : null,
      real_pipeline:  (typeof r.pipeline  === 'number') ? r.pipeline  : 0,
      real_units_active: r.units_active || 0,
      real_n_overdue:    r.n_overdue    || 0,
      real_post_launch:  !!r.post_launch,
    }),
    legendKey: 'legend_lifecycle', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'categorical', allowZero: true,
    overlay: () => null,
    popupRows: (p, t) => {
      const phaseId = p.real_phase;
      if (!phaseId) return '';
      const pricePct = p.real_price_pct;
      const rentPct  = p.real_rent_pct;
      const pipeShare = (p.real_pipeline * 100).toFixed(0);
      const fmtPct = v => (typeof v === 'number')
        ? ((v >= 0 ? '+' : '') + v.toFixed(1) + '%')
        : '—';
      const color = LIFECYCLE_PHASE_COLORS[phaseId];
      const textColor = LIFECYCLE_PHASE_TEXT[phaseId] || '#0f172a';
      const phaseLabel = t('lifecycle_phase_' + phaseId);
      return `
        <div class="stat"><span class="k">${t('pp_lifecycle_phase')}</span><span class="v"><span style="display:inline-block;padding:2px 8px;border-radius:10px;background:${color};color:${textColor};font-weight:600;font-size:12px">${phaseLabel}</span></span></div>
        <div class="stat"><span class="k">${t('pp_lifecycle_price')}</span><span class="v">${fmtPct(pricePct)}</span></div>
        <div class="stat"><span class="k">${t('pp_lifecycle_rent')}</span><span class="v">${fmtPct(rentPct)}</span></div>
        <div class="stat"><span class="k">${t('pp_lifecycle_pipeline')}</span><span class="v">${pipeShare}%</span></div>
      `;
    },
    tableColumns: [
      { key: 'name',       labelKey: 'tv_col_district',         type: 'str', width: '32%' },
      { key: r => {
          if (typeof r.vitality !== 'number') return null;
          if (r.post_launch) return -Infinity;
          return Math.round(r.vitality * 100);
        },
        rawKey: r => _lifecyclePhase(r),
        labelKey: 'tv_col_lifecycle_score',  type: 'phase', width: '20%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'price_pct',  labelKey: 'tv_col_lifecycle_price',  type: 'pct', width: '16%' },
      { key: 'rent_pct',   labelKey: 'tv_col_lifecycle_rent',   type: 'pct', width: '16%' },
      { key: r => Math.round((r.pipeline || 0) * 100),
                           labelKey: 'tv_col_lifecycle_pipeline', type: 'pct', width: '16%' },
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
      <div class="stat"><span class="k">${t('pp_payback_years')}</span><span class="v" style="font-weight:700">${p.real_metric.toFixed(1)} ${t('unit_years')}</span></div>
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

// Snapshot baseline real_* so applyMask can restore cleanly.
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
  'real_price_pct','real_rent_pct','real_pipeline','real_units_active','real_n_overdue',
  'real_post_launch',
];
// real_metric / real_fallback_yrs / real_price_pct / real_rent_pct stay nullable
// so the popup can show '—' for missing components; everything else falls back
// to 0 because the templates do numeric formatting on them.
const _MASK_FIELDS_NULLABLE = new Set([
  'real_metric', 'real_fallback_yrs', 'real_price_pct', 'real_rent_pct',
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
    // Split layout: map shrinks from 100% to 50% (or vice versa on map view).
    // Leaflet needs a tick to recompute tile coverage after the container size
    // changes. Skipping this leaves the right half of the map blank until the
    // next user pan/zoom.
    if (typeof map !== 'undefined' && map.invalidateSize) {
      setTimeout(() => map.invalidateSize(), 50);
    }
  } else if (typeof map !== 'undefined' && map.invalidateSize) {
    // Going map-only: map expands back to full width.
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
const _SEO_MASKS = ['sales', 'rents', 'growth', 'payback', 'lifecycle'];

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
  // Re-sync POI layer toggles with the new URL (covers back/forward across
  // /sales/?layers=metro,schools ↔ /sales/, etc.).
  if (typeof _applyLayersFromUrl === 'function') _applyLayersFromUrl();
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
    case 'phase':   return v;  // formatted by renderCell directly
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

const PAGE_SIZE = 25;

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

  // Per-numeric-column max on the current page (excluding the Dubai rollup).
  // Drives the inline magnitude bar width inside numeric cells — turns
  // empty whitespace into a quick at-a-glance comparator.
  const colMax = new Map();
  for (const c of mask.tableColumns) {
    if (c.type !== 'int' && c.type !== 'aed_big') continue;
    let m = 0;
    for (const r of pageRows) {
      const v = _tableValue(c, r);
      if (typeof v === 'number' && !isNaN(v) && v > m) m = v;
    }
    colMax.set(_tableColIdent(c), m);
  }

  // Rank column prepended to colgroup + thead + every row.
  const rankCol = `<col style="width:48px">`;
  const cols = rankCol + mask.tableColumns.map(c => `<col${c.width ? ' style="width:' + c.width + '"' : ''}>`).join('');
  const rankTh = `<th class="rank">#</th>`;
  const ths = rankTh + mask.tableColumns.map(c => {
    const ident = _tableColIdent(c);
    const sortedCls = (ident === state.sortKey) ? (' sorted-' + state.sortDir) : '';
    const numCls = (c.type !== 'str') ? 'num' : '';
    const cls = (numCls + sortedCls).trim();
    const label = t(c.labelKey);
    // title= shows the full label as a native tooltip when the header is
    // truncated by ellipsis — common on Growth/Payback masks with longer names.
    return `<th data-col="${ident}"${cls ? ' class="' + cls + '"' : ''} title="${_h(label)}">${_h(label)}</th>`;
  }).join('');

  const renderCell = (c, rec, isDubai) => {
    const v = _tableValue(c, rec);
    const isNum = c.type !== 'str' && c.type !== 'phase';
    const txt = _tableFmt(c, v);
    let cls = isNum ? 'num' : '';
    if (c.type === 'pct' && typeof v === 'number' && !isDubai) cls += ' ' + (v >= 0 ? 'pos' : 'neg');
    cls = cls.trim();
    // Phase cell — colored pill.
    if (c.type === 'phase') {
      const phaseId = c.rawKey ? c.rawKey(rec) : null;
      if (!phaseId) return `<td class="num">—</td>`;
      const color = LIFECYCLE_PHASE_COLORS[phaseId] || '#cbd5e1';
      const textColor = LIFECYCLE_PHASE_TEXT[phaseId] || '#0f172a';
      const label = t('lifecycle_phase_' + phaseId);
      return `<td class="num"><span style="display:inline-block;padding:2px 10px;border-radius:10px;background:${color};color:${textColor};font-weight:600;font-size:12px;white-space:nowrap">${_h(label)}</span></td>`;
    }
    // title attr surfaces the full cell value as a native tooltip when
    // truncation hides it (long district names, big numbers, etc.).
    const titleAttr = ` title="${_h(String(txt))}"`;
    // District-name cell — clickable link if a polygon exists for this key
    // (or always for the DUBAI rollup row, which opens the city-wide panel).
    // Unmatchable rows stay as muted plain text so the user can see at a
    // glance which districts have no polygon on the map.
    // txt comes from _tableFmt; for non-numeric ('str') columns it's raw
    // polygon `name` / `name_ar` which originate from OSM/GEOJSON, so escape.
    if (c.key === 'name') {
      const cellHtml = _h(String(txt));
      const areaKey = isDubai ? '__dubai__' : (rec && rec._k);
      const hasPolygon = isDubai || (areaKey && _FEAT_BY_KEY.has(areaKey));
      if (areaKey && hasPolygon) {
        // Dubai rollup has no per-district page; keep as bare link (row click
        // fits the map to all of Dubai). Real districts get a real href to
        // /<lang>/<mode>/<slug>/ — name click navigates, row click flies-to.
        const href = isDubai ? '' : (_districtHrefForKey(areaKey) || '');
        const hrefAttr = href ? ` href="${_h(href)}"` : '';
        return `<td${cls ? ' class="' + cls + '"' : ''}${titleAttr}><a class="tv-district-link" data-key="${_h(areaKey)}"${hrefAttr}>${cellHtml}</a></td>`;
      }
      return `<td${cls ? ' class="' + cls + ' tv-no-polygon"' : ' class="tv-no-polygon"'} title="${_h(t('tv_no_polygon'))}">${cellHtml}</td>`;
    }
    if (!isNum) {
      return `<td${cls ? ' class="' + cls + '"' : ''}${titleAttr}>${_h(String(txt))}</td>`;
    }
    // Magnitude bar (right-anchored) for int/aed_big columns. pct gets a chip
    // via .pos/.neg class instead; yrs stays as plain text — low precision
    // bars on 2-digit values add noise without signal.
    let barHtml = '';
    if (!isDubai && (c.type === 'int' || c.type === 'aed_big')) {
      const max = colMax.get(_tableColIdent(c)) || 0;
      if (max > 0 && typeof v === 'number' && !isNaN(v) && v > 0) {
        const pct = Math.max(0, Math.min(100, (v / max) * 100));
        if (pct >= 1) barHtml = `<span class="bar" style="width:${pct.toFixed(1)}%"></span>`;
      }
    }
    return `<td${cls ? ' class="' + cls + '"' : ''}${titleAttr}>${barHtml}<span class="v">${txt}</span></td>`;
  };

  // Rank cell — global rank within the filtered+sorted list (1-based, with
  // page offset). Dubai rollup is outside the rank stream → "Σ".
  const rankCell = (i, isDubai) => isDubai
    ? `<td class="rank">Σ</td>`
    : `<td class="rank">${start + i + 1}</td>`;

  // Dubai rollup pinned at the top of page 1 (and ONLY there) so the
  // city-wide reference number is visible without polluting later pages.
  let dubaiHtml = '';
  if (state.page === 1 && data[dubaiKey] && matches(data[dubaiKey])) {
    dubaiHtml = `<tr class="dubai-row clickable" data-key="${_h(dubaiKey)}">` + rankCell(0, true) + mask.tableColumns.map(c => renderCell(c, data[dubaiKey], true)).join('') + '</tr>';
  }
  const bodyHtml = pageRows.length
    ? pageRows.map((rec, i) => {
        const areaKey = rec._k || '';
        const hasPoly = areaKey && _FEAT_BY_KEY.has(areaKey);
        const trCls = hasPoly ? 'clickable' : '';
        const dataAttr = areaKey ? ` data-key="${_h(areaKey)}"` : '';
        return `<tr${trCls ? ' class="' + trCls + '"' : ''}${dataAttr}>` + rankCell(i, false) + mask.tableColumns.map(c => renderCell(c, rec, false)).join('') + '</tr>';
      }).join('')
    : `<tr><td colspan="${mask.tableColumns.length + 1}" class="tv-empty">${t('search_empty')}</td></tr>`;

  const tbl = document.getElementById('tv-table');
  if (!tbl) return;
  // Per-mask hook for header sizing (Growth/Payback have longer labels and get
  // a smaller header font via .mask-growth / .mask-payback selectors).
  tbl.className = 'mask-' + currentMask;
  tbl.innerHTML = `<colgroup>${cols}</colgroup><thead><tr>${ths}</tr></thead><tbody>${dubaiHtml}${bodyHtml}</tbody>`;

  const cnt = document.getElementById('tv-count');
  if (cnt) cnt.textContent = total.toLocaleString('ru-RU') + ' ' + t('tv_count_label');

  _renderTvPager(state.page, totalPages, total);

  tbl.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.col;
      if (state.sortKey === k) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = k; state.sortDir = (sortCol.type === 'str') ? 'asc' : 'desc'; }
      state.page = 1;
      renderTable();
    });
  });
  // Row-level click: anywhere in a row with [data-key] flies the map (in split
  // layout) or navigates (mobile fallback). Delegation keeps a single listener
  // even after sort/pagination rerenders.
  //
  // Clicks on the district-name link (`a.tv-district-link[href]`) bypass this
  // handler so the browser performs a real navigation to the district page —
  // name = open page, anywhere else in the row = fly the map. Dubai rollup's
  // link has no href, so its row click still falls through to fly-to-city.
  const tbody = tbl.querySelector('tbody');
  if (tbody && !tbody._wired) {
    tbody._wired = true;
    tbody.addEventListener('click', e => {
      if (e.target.closest('a.tv-district-link[href]')) return;
      const tr = e.target.closest('tr.clickable');
      if (!tr) return;
      const key = tr.getAttribute('data-key');
      if (!key) return;
      e.preventDefault();
      _openDistrictFromTable(key);
    });
  }
}

// Close the table view, switch to map, and zoom + open the polygon popup
// for the given area_key. Used by district-name links in the table view.
// Lookup table built once at boot: area_key (lowercase) → feature. Includes
// every polygon's real_area_key plus a fallback by lowercased display name
// so JSON aggregates that don't share the polygon's exact key still resolve.
const _FEAT_BY_KEY = (function () {
  const m = new Map();
  for (const f of GEOJSON.features) {
    const p = f.properties || {};
    if (p.real_area_key && !m.has(p.real_area_key)) m.set(p.real_area_key, f);
    if (p.name) {
      const n = String(p.name).toLowerCase();
      if (!m.has(n)) m.set(n, f);
    }
  }
  return m;
})();

function _featureForAreaKey(areaKey) {
  if (!areaKey || areaKey === '__dubai__') return null;
  return _FEAT_BY_KEY.get(areaKey) || _FEAT_BY_KEY.get(String(areaKey).toLowerCase()) || null;
}

function _openDistrictByKey(areaKey) {
  // Single-key entry point: navigate straight to the per-district page.
  window.openDistrictByKey(areaKey);
}

function _openDistrictFromTable(areaKey) {
  if (!areaKey) return;
  // Narrow viewport: split layout collapses to table-only (CSS @media). Map
  // is hidden, so fly-to is invisible — fall back to per-district navigation.
  if (window.matchMedia && window.matchMedia('(max-width:900px)').matches) {
    window.openDistrictByKey(areaKey);
    return;
  }
  // Dubai rollup row → fit to the full city extent.
  if (areaKey === '__dubai__') {
    if (typeof map !== 'undefined' && map.fitBounds && typeof GEOJSON !== 'undefined' && typeof L !== 'undefined') {
      map.fitBounds(L.geoJSON(GEOJSON).getBounds(), {padding:[20,20]});
    }
    if (typeof _setSelected === 'function') _setSelected(null);
    return;
  }
  // Split mode: reuse the search-box selection flow (flies the map, opens the
  // polygon popup with the standard stats panel). If no polygon exists for
  // this key, fall back to navigation.
  const feat = (typeof _featureForAreaKey === 'function') ? _featureForAreaKey(areaKey) : null;
  if (feat && typeof _onSearchSelect === 'function') {
    _onSearchSelect(feat);
  } else {
    window.openDistrictByKey(areaKey);
  }
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
    let periodHTML = '';
    if (mask.periods.length > 1) {
      const curP = (id === currentMask) ? currentMaskPeriod : mask.defaultPeriod;
      const idx  = Math.max(0, mask.periods.indexOf(curP));
      const maxIdx = mask.periods.length - 1;
      const ticks = mask.periods.map((p, i) =>
        `<span class="period-tick${(id===currentMask && i===idx)?' active':''}" data-idx="${i}">${_periodLabel(mask, p)}</span>`
      ).join('');
      periodHTML = `<div class="mask-row-periods">
           <span class="pc-lbl">${t(mask.periodLabelKey || 'mask_period_label')}</span>
           <div class="period-slider-wrap">
             <input type="range" class="period-slider" min="0" max="${maxIdx}" step="1" value="${idx}" aria-label="${t(mask.periodLabelKey || 'mask_period_label')}">
             <div class="period-slider-ticks">${ticks}</div>
           </div>
         </div>`;
    }
    row.innerHTML = `
      <div class="mask-row-head">
        <div class="mask-row-radio"></div>
        <div class="mask-row-title">${t(mask.labelKey)}</div>
      </div>
      <div class="mask-row-desc">${t(mask.descKey)}</div>
      ${periodHTML}
    `;
    row.addEventListener('click', e => {
      if (e.target.closest('.period-slider-wrap')) return;
      applyMask(id, (id === currentMask) ? currentMaskPeriod : mask.defaultPeriod);
      renderMaskList();
    });
    const slider = row.querySelector('.period-slider');
    if (slider) {
      slider.addEventListener('input', e => {
        e.stopPropagation();
        const i = parseInt(slider.value, 10);
        const p = mask.periods[i];
        if (p) { applyMask(id, p); renderMaskList(); }
      });
      slider.addEventListener('click', e => e.stopPropagation());
    }
    row.querySelectorAll('.period-tick').forEach(tick => {
      tick.addEventListener('click', e => {
        e.stopPropagation();
        const i = parseInt(tick.dataset.idx, 10);
        const p = mask.periods[i];
        if (p) { applyMask(id, p); renderMaskList(); }
      });
    });
    list.appendChild(row);
  }
  // View toggle now lives as a single fixed-position #view-switch button in
  // the top-right corner (see index.html + _wireViewSwitch below).
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
  const viewSwitch = document.getElementById('view-switch');
  if (viewSwitch) {
    viewSwitch.addEventListener('click', () => setView(currentView === 'map' ? 'table' : 'map'));
  }
})();
function _refreshViewSwitchLabel() {
  const btn = document.getElementById('view-switch');
  if (!btn) return;
  btn.innerHTML = currentView === 'map' ? `▦ ${t('view_table')}` : `⌖ ${t('view_map')}`;
}
_refreshViewSwitchLabel();

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
    `<div class="sr-item" data-i="${i}"><span class="sr-name">${_h(x.name)}</span><span class="sr-meta">L${x.level|0}${x.rc?(' · '+x.rc.toLocaleString('ru-RU')):''}</span></div>`
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
  // Persistent selection outline so the user can locate the district on the
  // map after the flyTo completes (table-row click flow, mainly).
  if (typeof _setSelected === 'function') _setSelected(feat);
}

let choro;
// Color by sign of label ("+12%" green, "-3%" red, unsigned neutral)
function _overlayColorFor(label) {
  const s = String(label);
  const sign = s[0] === '+' ? 'pos' : (s[0] === '-' ? 'neg' : 'neu');
  return sign === 'pos' ? '#0a7f00' : sign === 'neg' ? '#b91c1c' : '#1f2933';
}

let overlayLayer = null;
function _refreshOverlay(mask) {
  if (overlayLayer) { map.removeLayer(overlayLayer); overlayLayer = null; }
  if (!mask || typeof mask.overlay !== 'function') return;
  const data = mask.data[currentMaskPeriod] || {};
  const zoom = map.getZoom();

  // First pass: collect items with magnitudes so we can normalize per-metric.
  // Without this, low-range metrics (payback: 5..20 years) get uniformly tiny
  // badges while wide-range metrics (growth: ±50%) get full dynamic range.
  const items = [];
  for (const f of GEOJSON.features) {
    if (f._level !== undefined && f._level < minLevel) continue;
    const key = f.properties.real_area_key;
    if (!key) continue;
    const rec = data[key];
    if (!rec) continue;
    const label = mask.overlay(rec);
    if (label === null || label === undefined || label === '') continue;
    const num = Math.abs(parseFloat(String(label).replace(/[^0-9.\-]/g, '')) || 0);
    items.push({ f, label, num });
  }
  if (!items.length) return;
  // Clip the top at the 90th percentile so a couple of extreme outliers don't
  // compress everyone else into tiny badges. Growth had 1-2 districts at
  // +50%/-30% pinning most others into 0..0.3 normalised — barely visible.
  const sorted = items.map(i => i.num).slice().sort((a, b) => a - b);
  const lo = sorted[0];
  const hi = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.90))];
  const range = (hi - lo) || 1;
  const zoomFactor = 1 + Math.max(0, zoom - 10) * 0.20;

  overlayLayer = L.layerGroup();
  for (const item of items) {
    const f = item.f;
    let norm = Math.max(0, Math.min(1, (item.num - lo) / range));  // 0..1, outliers clipped
    if (mask.invertRamp) norm = 1 - norm;          // payback: fewer years → bigger badge
    const fontSize = Math.round((4 + norm * 4) * zoomFactor * 10) / 10;
    const color = _overlayColorFor(item.label);
    const bb = _bbox(f.geometry);
    const icon = L.divIcon({
      className: 'choro-overlay',
      html: `<span class="choro-overlay-text" style="font-size:${fontSize}px;color:${color}">${item.label}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
    const marker = L.marker([bb.cy, bb.cx], { icon, interactive: true, keyboard: false, bubblingMouseEvents: false });
    // Route badge click to THIS feature's polygon — bypasses the under-the-cursor
    // routing that would otherwise hit the parent for narrow districts like JBR.
    marker.on('click', function(e) {
      L.DomEvent.stopPropagation(e);
      _openFeaturePopup(f, marker.getLatLng());
    });
    // Hover-highlight is handled by the map-level mousemove handler — native
    // DOM bubbling carries the event to the map even when over the badge.
    marker.addTo(overlayLayer);
  }
  overlayLayer.addTo(map);
}

map.on('zoomend', () => {
  const m = MASKS[currentMask];
  if (m && typeof m.overlay === 'function') _refreshOverlay(m);
});

// Build popup HTML for any feature; extracted from onEachFeature so we can
// open popups manually regardless of which polygon Leaflet's hit-testing picks.
function _featurePopupHtml(f) {
  const p = f.properties;
  const m = MASKS[currentMask] || MASKS.sales;
  const newDev = p._new_dev_count || 0;
  const newDevRow = newDev ? `<div class="stat"><span class="k">${t("new_buildings")}</span><span class="v">${newDev|0}</span></div>` : '';
  const detailsBtn = p.real_area_key
    ? `<div style="margin-top:8px"><a href="${_h(_safeUrl(_districtHrefForKey(p.real_area_key, p.name, p.legacy_area_key, p.master_project_key)))}" style="background:#0366d6;color:#fff;text-decoration:none;padding:6px 12px;border-radius:4px;font-size:12px;font-weight:600;display:inline-block">${t("pp_open")}</a></div>`
    : '';
  let bodyRows;
  if (typeof m.popupRows === 'function') {
    const rendered = m.popupRows(p, t);
    bodyRows = rendered
      ? `${rendered}${newDevRow}${detailsBtn}`
      : `${newDevRow}<div class="muted" style="font-size:11px;color:#888;padding:4px 0">${t("no_dld_data")}</div>`;
  } else {
    const volumeRow = m.showVolume ? `<div class="stat"><span class="k">${t("pp_volume")}</span><span class="v">${(p.real_total_aed||0)>=1e9?((p.real_total_aed/1e9).toFixed(2)+' '+t('abbr_b')):((p.real_total_aed/1e6).toFixed(1)+' '+t('abbr_m'))}</span></div>` : '';
    bodyRows = p.real_count ? `
      <div class="stat"><span class="k">${t(m.popupCountKey || "pp_trans_ytd")}${p.real_match_kind==='parent'?' <span class="src-tag" style="background:#fff5e6;color:#7a4c00">parent: '+_h(p.real_parent_name||'')+'</span>':''}</span><span class="v">${p.real_count.toLocaleString('ru-RU')}</span></div>
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
    <h3>${p.name ? _h(p.name) : '—'}</h3>
    <div class="muted" style="margin-bottom:6px;color:#888">${_h(p.name_ar||'')}</div>
    ${bodyRows}
  `;
}

function _openFeaturePopup(f, latlng) {
  L.popup().setLatLng(latlng).setContent(_featurePopupHtml(f)).openOn(map);
}

// Click anywhere on a polygon → open the SMALLEST visible polygon that contains
// the click point. Bypasses Leaflet's z-order-only routing; works for narrow or
// nested districts whose centroid sits outside their own shape (JBR, Dubai Hills).
function _findSmallestAt(latlng) {
  const pt = [latlng.lng, latlng.lat];
  let smallest = null;
  for (const f of GEOJSON.features) {
    if (f._level !== undefined && f._level < minLevel) continue;
    if (!f._layer) continue;
    if (!_featContains(f, pt)) continue;
    if (!smallest || f._bboxArea < smallest._bboxArea) smallest = f;
  }
  return smallest;
}

function _openSmallestPopup(latlng) {
  const f = _findSmallestAt(latlng);
  if (f) _openFeaturePopup(f, latlng);
}

// Two layers of polygon outline:
//   hover    — transient, black 2px, follows the cursor
//   selected — persistent, brand-blue 3.5px, marks the last user pick (table
//              row, search box, map click). Stays until next pick.
// Hover wins visually when both apply (immediate cursor feedback), then the
// selected style is restored when the cursor leaves.
let _hoveredFeat = null;
let _selectedFeat = null;
let _hoverRaf = 0;
const _STYLE_HOVER    = {weight: 2,   color: '#000'};
const _STYLE_SELECTED = {weight: 3.5, color: '#000'};

function _restoreStyle(f) {
  if (!f || !f._layer) return;
  if (f === _hoveredFeat)        f._layer.setStyle(_STYLE_HOVER);
  else if (f === _selectedFeat)  f._layer.setStyle(_STYLE_SELECTED);
  else if (choro)                choro.resetStyle(f._layer);
}

function _setHover(f) {
  if (f === _hoveredFeat) return;
  const prev = _hoveredFeat;
  _hoveredFeat = f;
  _restoreStyle(prev);
  if (f && f._layer) f._layer.setStyle(_STYLE_HOVER);
}

function _setSelected(f) {
  if (f === _selectedFeat) return;
  const prev = _selectedFeat;
  _selectedFeat = f;
  _restoreStyle(prev);
  // Only paint selected when cursor isn't on top — hover wins for the
  // immediate-feedback layer.
  if (f && f._layer && f !== _hoveredFeat) f._layer.setStyle(_STYLE_SELECTED);
}

map.on('mousemove', (e) => {
  if (_hoverRaf) return;
  _hoverRaf = requestAnimationFrame(() => {
    _hoverRaf = 0;
    _setHover(_findSmallestAt(e.latlng));
  });
});
map.on('mouseout', () => _setHover(null));

function renderChoro(){
  const mask = MASKS[currentMask] || MASKS.sales;
  const metricKey = mask.metricKey || 'real_count';
  const scale     = mask.scaleMode || 'log';
  const allowZero = !!mask.allowZero;
  const isCategorical = scale === 'categorical';
  const isMissing = isCategorical
    ? (f) => !f.properties.real_phase
    : (v) => v === null || v === undefined || isNaN(v) || (!allowZero && v === 0);
  // breaks only used for continuous scales
  let breaks = null;
  if (!isCategorical) {
    const vs = GEOJSON.features
      .map(f => f.properties[metricKey])
      .filter(v => !isMissing(v));
    breaks = vs.length
      ? (scale==='quantile' ? qBreaks(vs,RAMP.length)
         : scale==='log'    ? logBreaks(vs,RAMP.length)
         :                    lBreaks(vs,RAMP.length))
      : Array(RAMP.length - 1).fill(0);
  }
  if(choro) map.removeLayer(choro);
  choro = L.geoJSON(GEOJSON,{
    filter: f => (f._level !== undefined ? f._level >= minLevel : true),
    style: f => {
      if (isCategorical) {
        const phase = f.properties.real_phase;
        if (!phase) return {weight:0.8,color:'#64748b',fillColor:'url(#nodata-hatch)',fillOpacity:1,dashArray:'4,3'};
        return {weight:0.6,color:'#1f2933',fillColor:LIFECYCLE_PHASE_COLORS[phase] || '#cbd5e1',fillOpacity:0.7};
      }
      const v = f.properties[metricKey], z = isMissing(v);
      if (z) return {weight:0.8,color:'#64748b',fillColor:'url(#nodata-hatch)',fillOpacity:1,dashArray:'4,3'};
      let idx = classify(v, breaks);
      if (mask.invertRamp) idx = RAMP.length - 1 - idx;
      return {weight:0.6,color:'#1f2933',fillColor:RAMP[idx],fillOpacity:0.7};
    },
    onEachFeature: (f, layer) => {
      layer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        _openSmallestPopup(e.latlng);
      });
      // Stored so overlay badges can open THEIR feature's popup directly
      // (badges sit at bbox centroid, which may fall outside the actual
      // polygon or under a parent — see JBR / Dubai Hills).
      // Hover-highlight is handled at the map level (see _setHover).
      f._layer = layer;
    },
  }).addTo(map);
  choro.bringToBack();

  // Legend
  const title = t(mask.legendKey || 'ch_count');
  let html;
  if (isCategorical) {
    html = `<div style="margin-bottom:4px"><span style="font-weight:600">${title}</span></div>`;
    for (const id of LIFECYCLE_PHASE_ORDER) {
      html += `<div class="row"><span class="sw" style="background:${LIFECYCLE_PHASE_COLORS[id]}"></span>${t('lifecycle_phase_' + id)}</div>`;
    }
    html += `<div class="row"><span class="sw" style="background:repeating-linear-gradient(45deg,transparent,transparent 3px,#94a3b8 3px,#94a3b8 4px)"></span>${t('legend_no_data')}</div>`;
  } else {
    const fmt = mask.legendFmt || METRIC_FMT.count;
    const vs = GEOJSON.features
      .map(f => f.properties[metricKey])
      .filter(v => !isMissing(v));
    const lo = vs.length ? Math.min(...vs) : 0;
    const hi = vs.length ? Math.max(...vs) : 0;
    const all = [lo, ...breaks, hi];
    const paletteName = _paletteName.charAt(0).toUpperCase() + _paletteName.slice(1);
    html = `<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:4px"><span style="font-weight:600">${title}</span><button type="button" onclick="togglePalette()" title="Сменить палитру (A/B-тест)" style="border:1px solid #d1d5db;background:#fff;border-radius:4px;padding:1px 7px;cursor:pointer;font-size:11px;color:#374151;line-height:1.4">🎨 ${paletteName}</button></div>`;
    for(let i=0;i<RAMP.length;i++) {
      const cIdx = mask.invertRamp ? (RAMP.length - 1 - i) : i;
      html += `<div class="row"><span class="sw" style="background:${RAMP[cIdx]}"></span>${fmt(all[i])} – ${fmt(all[i+1])}</div>`;
    }
    html += `<div class="row"><span class="sw" style="background:repeating-linear-gradient(45deg,transparent,transparent 3px,#94a3b8 3px,#94a3b8 4px)"></span>${t('legend_no_data')}</div>`;
  }
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
    <h3>🚇 ${_h(s.name || t('station_default'))} <span class="src-tag src-osm">OSM</span></h3>
    <div class="muted" style="color:#888;margin-bottom:4px">${_h(labelLines)}${isInterchange?(' · '+t('metro_interchange')):''}</div>
    ${s.line ? `<div class="stat"><span class="k">${t("metro_line")}</span><span class="v">${_h(s.line)}</span></div>` : ''}
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
      ? `<span${titleAttr}>${_h(s.name)}</span>`
      : ('<span style="color:#888">' + _h(t('no_name')) + '</span>');
    const arSubtitle = (s.name_ar && s.name_ar !== s.name)
      ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${_h(s.name_ar)}</div>`
      : '';
    if (!s.in_khda) {
      const osmRows = [];
      if (s.operator)       osmRows.push(`<div class="stat"><span class="k">${t('h_op')}</span><span class="v">${_h(s.operator)}</span></div>`);
      if (s.school_type)    osmRows.push(`<div class="stat"><span class="k">${t('sch_curr')}</span><span class="v">${_h(s.school_type)}</span></div>`);
      if (s.school_gender)  osmRows.push(`<div class="stat"><span class="k">${t('sch_gender')}</span><span class="v">${_h(s.school_gender)}</span></div>`);
      if (s.addr_suburb)    osmRows.push(`<div class="stat"><span class="k">${t('sch_area')}</span><span class="v">${_h(s.addr_suburb)}</span></div>`);
      if (s.website)        osmRows.push(`<div class="stat"><span class="k">${t('h_web')}</span><span class="v"><a href="${_h(_safeUrl(s.website))}" target="_blank" rel="noopener noreferrer">${_h(s.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32))}</a></span></div>`);
      if (s.wikidata)       osmRows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${encodeURIComponent(s.wikidata)}" target="_blank" rel="noopener noreferrer">${_h(s.wikidata)}</a></span></div>`);
      return `
        <h3>🏫 ${displayName} <span class="src-tag src-osm">OSM</span></h3>
        ${arSubtitle}
        ${osmRows.join('')}
        <div class="muted" style="font-size:11px;color:#888;margin-top:6px">${t('sch_not_in_khda')}</div>
      `;
    }
    const srcTag = '<span class="src-tag" style="background:#e6f7e6;color:#0a7f00">KHDA</span>';
    const manualTag = s.manual_coords
      ? ' <span class="src-tag" style="background:#fff5e0;color:#b35900" title="Coordinates set manually — school missing from OSM">~coords</span>'
      : '';
    const rows = [];
    if (s.curriculum)  rows.push(`<div class="stat"><span class="k">${t('sch_curr')}</span><span class="v">${_h(s.curriculum)}</span></div>`);
    if (s.grade_range) rows.push(`<div class="stat"><span class="k">${t('sch_grade_range')}</span><span class="v">${_h(s.grade_range)}</span></div>`);
    if (s.area)        rows.push(`<div class="stat"><span class="k">${t('sch_area')}</span><span class="v">${_h(s.area)}</span></div>`);
    if (s.phone)       rows.push(`<div class="stat"><span class="k">${t('sch_phone')}</span><span class="v"><a href="tel:${encodeURIComponent(s.phone)}">${_h(s.phone)}</a></span></div>`);
    if (s.rating)      rows.push(`<div class="stat"><span class="k">${t('sch_rating')}</span><span class="v"><span class="rating ${_h(_rcls(s.rating))}">${_h(s.rating)}</span></span></div>`);
    if (s.wellbeing)   rows.push(`<div class="stat"><span class="k">${t('sch_wellbeing')}</span><span class="v"><span class="rating ${_h(_rcls(s.wellbeing))}">${_h(s.wellbeing)}</span></span></div>`);
    if (s.inclusion)   rows.push(`<div class="stat"><span class="k">${t('sch_inclusion')}</span><span class="v"><span class="rating ${_h(_rcls(s.inclusion))}">${_h(s.inclusion)}</span></span></div>`);
    const detailsUrl = `https://web.khda.gov.ae/en/Education-Directory/Schools/School-Details?Id=${encodeURIComponent(s.khda_id)}&CenterID=${encodeURIComponent(s.center_id)}`;
    return `
      <h3>🏫 ${displayName} ${srcTag}${manualTag}</h3>
      ${arSubtitle}
      ${rows.join('')}
      <div style="margin-top:6px"><a href="${detailsUrl}" target="_blank" rel="noopener noreferrer" style="font-size:11px">KHDA School Details ↗</a></div>
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
    const icon = L.divIcon({className:'', html:`<div class="pin ${_h(key)}">${def.emoji}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
    const m = L.marker([p.lat, p.lon], {icon});
    const lines = [`<h3>${def.emoji} ${p.name ? _h(p.name) : ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>`];
    lines.push(`<div class="muted" style="color:#888;margin-bottom:4px">${_h(def.label)}</div>`);
    if (p.op) lines.push(`<div class="stat"><span class="k">${t('uni_op')}</span><span class="v">${_h(p.op)}</span></div>`);
    if (p.kind) lines.push(`<div class="stat"><span class="k">${t('uni_op_type')}</span><span class="v">${_h(p.kind)}</span></div>`);
    if (p.start_date) lines.push(`<div class="stat"><span class="k">${t("pj_start")}</span><span class="v">${_h(p.start_date)}</span></div>`);
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
    const displayName = hasName ? `<span${titleAttr}>${_h(u.name)}</span>` : `<span style="color:#888">${t('no_name')}</span>`;
    const arSub = (u.name_ar && u.name_ar !== u.name)
      ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${_h(u.name_ar)}</div>`
      : '';
    const srcTag = u.in_khda
      ? '<span class="src-tag" style="background:#e6f7e6;color:#0a7f00">KHDA</span>'
      : '<span class="src-tag src-osm">OSM</span>';
    const rows = [];
    if (u.in_khda) {
      if (u.khda_area)        rows.push(`<div class="stat"><span class="k">${t('uni_city')}</span><span class="v">${_h(u.khda_area)}</span></div>`);
      if (u.khda_established) rows.push(`<div class="stat"><span class="k">${t('uni_established')}</span><span class="v">${_h(u.khda_established)}</span></div>`);
      if (u.khda_stars)       rows.push(`<div class="stat"><span class="k">${t('uni_khda_stars')}</span><span class="v"><span class="rating Verygood">${'★'.repeat(parseInt(u.khda_stars,10)||0)}${'☆'.repeat(5-(parseInt(u.khda_stars,10)||0))}</span> ${u.khda_rating_year ? `<span style="color:#888;font-size:11px">${_h(u.khda_rating_year)}</span>` : ''}</span></div>`);
    }
    if (u.operator)      rows.push(`<div class="stat"><span class="k">${t('uni_op')}</span><span class="v">${_h(u.operator)}</span></div>`);
    if (u.website)       rows.push(`<div class="stat"><span class="k">${t('uni_web')}</span><span class="v"><a href="${_h(_safeUrl(u.website))}" target="_blank" rel="noopener noreferrer">${_h(u.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32))}</a></span></div>`);
    if (u.wikipedia) {
      const wpUrl = 'https://' + u.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${_h(_safeUrl(wpUrl))}" target="_blank" rel="noopener noreferrer">${_h(u.wikipedia)}</a></span></div>`);
    }
    if (u.wikidata && !u.wikipedia) rows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${encodeURIComponent(u.wikidata)}" target="_blank" rel="noopener noreferrer">${_h(u.wikidata)}</a></span></div>`);
    const detailsLink = u.khda_uni_id
      ? `<div style="margin-top:6px"><a href="https://web.khda.gov.ae/en/Education-Directory/Higher-Education/Higher-Education-Details?CenterID=${encodeURIComponent(u.khda_uni_id)}" target="_blank" rel="noopener noreferrer" style="font-size:11px">KHDA Details ↗</a></div>`
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
      rows.push(`<div class="stat"><span class="k">${t('h_specs_real')}</span><span class="v" style="text-align:right;max-width:200px;white-space:normal;font-size:11px">${specs.map(s => `<span class="lang-chip">${_h(s)}</span>`).join('')}</span></div>`);
    }
    if (m.operator) rows.push(`<div class="stat"><span class="k">${t('h_op')}</span><span class="v">${_h(m.operator)}</span></div>`);
    if (m.phone)    rows.push(`<div class="stat"><span class="k">${t('h_phone')}</span><span class="v"><a href="tel:${encodeURIComponent(m.phone)}">${_h(m.phone)}</a></span></div>`);
    if (m.website)  rows.push(`<div class="stat"><span class="k">${t('h_web')}</span><span class="v"><a href="${_h(_safeUrl(m.website))}" target="_blank" rel="noopener noreferrer">${_h(m.website.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 32))}</a></span></div>`);
    if (m.wikipedia) {
      const wpUrl = 'https://' + m.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g, '_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${_h(_safeUrl(wpUrl))}" target="_blank" rel="noopener noreferrer">${_h(m.wikipedia)}</a></span></div>`);
    }
    if (m.opening_hours) rows.push(`<div class="stat"><span class="k">${t('ml_hours')}</span><span class="v" style="font-size:11.5px">${_h(m.opening_hours)}</span></div>`);
    if (m.addr_city)     rows.push(`<div class="stat"><span class="k">${t('h_city')}</span><span class="v">${_h(m.addr_city)}</span></div>`);
    return `
      <h3>${meta.emoji} ${m.name ? _h(m.name) : ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>
      ${m.name_ar ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${_h(m.name_ar)}</div>` : ''}
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
    realRows.push(`<div class="stat"><span class="k">${t("mo_denom")}</span><span class="v">${_h(mo.denomination)}</span></div>`);
  }
  if (mo.addr_street) realRows.push(`<div class="stat"><span class="k">${t("mo_street")}</span><span class="v">${_h(mo.addr_street)}</span></div>`);
  if (mo.addr_city) realRows.push(`<div class="stat"><span class="k">${t("mo_city")}</span><span class="v">${_h(mo.addr_city)}</span></div>`);
  if (mo.wheelchair) realRows.push(`<div class="stat"><span class="k">${t("mo_wheel")}</span><span class="v">${mo.wheelchair==='yes'?'✓ да':_h(mo.wheelchair)}</span></div>`);
  if (mo.image) realRows.push(`<div class="stat"><span class="k">${t("mo_image")}</span><span class="v"><a href="${_h(_safeUrl(mo.image))}" target="_blank" rel="noopener noreferrer">${t("view_t")}</a></span></div>`);

  // Drop the synthetic "size" row — it duplicates capacity and "Mahalla" is untranslated.
  const synth = `
    <div class="stat"><span class="k">${t("mo_cap")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.capacity.toLocaleString('ru-RU')}</span></div>
    <div class="stat"><span class="k">${t("mo_khutbah")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.khutbah_langs.map(l=>`<span class="lang-chip">${_h(l)}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("mo_women")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.women_section?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_park")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.parking?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_classes")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.classes?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_iftar")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.iftar?t('yes_t'):t('no_t')}</span></div>
  `;
  return `
    <h3>🕌 ${mo.name ? _h(mo.name) : ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>
    ${mo.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${_h(mo.name_ar)}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    ${synth}
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("mo_warn")}</div>
  `;
});
  m.addTo(mosqueLayer);
}

// ===================== CONSTRUCTION PROJECTS =====================
// One marker per project bucket — NOT per individual project.
// Badge shows in-flight count; popup breaks down by status, lists top
// developers, sums composition.
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
    // currently happening. Overdue surfaces as its own red chip when
    // non-zero (it's a subset of ACTIVE in `by_status`).
    const order = ['ACTIVE','NOT_STARTED','PENDING','CONDITIONAL_ACTIVATING','FINISHED','CANCELLED','FRIEZED'];
    const chips = [];
    if (d.overdue) {
      chips.push(`<span class="pj-status-chip" style="background:#fee2e21f;color:#991b1b">${t('pj_status_overdue') || 'Overdue'} · ${d.overdue}</span>`);
    }
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
        `<div style="display:flex;justify-content:space-between;gap:8px;font-size:11.5px"><span dir="rtl" style="flex:1;text-align:right">${_h(name)}</span><span style="color:#888">${count|0}</span></div>`
      ).join('');
      rows.push(`<div class="stat"><span class="k">${t('pj_top_devs')}</span><span class="v" style="text-align:right;max-width:220px">${devLines}</span></div>`);
    }

    const geoNote = d.geocode_kind === 'area'
      ? `<div class="muted" style="margin-top:6px;font-size:11px;color:#888">${t('pj_geocode_area')}</div>`
      : '';
    // Deep-link to /construction/?q=<district name>. The page reads ?q=
    // on load, drops it into the search box, and the existing filter
    // pipeline narrows the table + all four charts to just this district.
    // Uses the master-project name (d.name) as the search term since
    // that's what the page's master / area / project fields match.
    const constructionHref = (typeof _langUrlPrefix === 'function' ? _langUrlPrefix() : '')
      + '/construction/?q=' + encodeURIComponent(d.name);
    const openAll = `<div style="margin-top:8px"><a class="pj-open-all" href="${constructionHref}">${t('pj_open_all')} (${d.total|0}) →</a></div>`;

    return `
      <h3>🏗️ ${_h(d.name)} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">RERA</span></h3>
      <div class="muted" style="color:#888;margin-bottom:4px;font-size:11.5px">${d.in_flight|0} ${t('pj_in_flight_label')} / ${d.total|0} ${t('pj_total_label')}</div>
      ${rows.join('')}
      ${geoNote}
      ${openAll}
    `;
  });
  m.addTo(projectLayer);
}

// ===================== MALLS (OSM) =====================
const mallLayer = L.layerGroup();
for (const ml of MALLS) {
  const emoji = ml.kind === 'souq' ? '🏛️' : '🛍️';
  const cls   = ml.kind === 'souq' ? 'pin mall souq' : 'pin mall';
  const icon = L.divIcon({className:'', html:`<div class="${cls}">${emoji}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([ml.lat, ml.lon], {icon});
  m.bindPopup(() => {
    const rows = [];
    const kindLabel = t(ml.kind === 'souq' ? 'ml_kind_souq' : 'ml_kind_mall');
    rows.push(`<div class="stat"><span class="k">${t('ml_kind')}</span><span class="v">${kindLabel}</span></div>`);
    if (ml.opening_hours) rows.push(`<div class="stat"><span class="k">${t('ml_hours')}</span><span class="v" style="font-size:11.5px">${_h(ml.opening_hours)}</span></div>`);
    if (ml.operator) rows.push(`<div class="stat"><span class="k">${t('ml_op')}</span><span class="v">${_h(ml.operator)}</span></div>`);
    if (ml.brand) rows.push(`<div class="stat"><span class="k">${t('ml_brand')}</span><span class="v">${_h(ml.brand)}</span></div>`);
    if (ml.phone) rows.push(`<div class="stat"><span class="k">${t('ml_phone')}</span><span class="v"><a href="tel:${encodeURIComponent(ml.phone)}">${_h(ml.phone)}</a></span></div>`);
    if (ml.website) rows.push(`<div class="stat"><span class="k">${t('ml_web')}</span><span class="v"><a href="${_h(_safeUrl(ml.website))}" target="_blank" rel="noopener noreferrer">${_h(ml.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32))}</a></span></div>`);
    if (ml.wikipedia) {
      const wpUrl = 'https://' + ml.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${_h(_safeUrl(wpUrl))}" target="_blank" rel="noopener noreferrer">${_h(ml.wikipedia)}</a></span></div>`);
    } else if (ml.wikidata) {
      rows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${encodeURIComponent(ml.wikidata)}" target="_blank" rel="noopener noreferrer">${_h(ml.wikidata)}</a></span></div>`);
    }
    if (ml.building_levels) rows.push(`<div class="stat"><span class="k">${t('ml_levels')}</span><span class="v">${_h(ml.building_levels)}</span></div>`);
    const addr = [ml.addr_street, ml.addr_suburb, ml.addr_city].filter(Boolean).join(', ');
    if (addr) rows.push(`<div class="stat"><span class="k">${t('ml_addr')}</span><span class="v" style="font-size:11.5px;max-width:200px;text-align:right">${_h(addr)}</span></div>`);
    if (ml.wheelchair === 'yes') rows.push(`<div class="stat"><span class="k">${t('ml_access')}</span><span class="v" style="color:#0a7f00">✓ wheelchair</span></div>`);
    if (ml.internet_access === 'yes' || ml.internet_access === 'wlan') rows.push(`<div class="stat"><span class="k">${t('ml_wifi')}</span><span class="v" style="color:#0a7f00">✓</span></div>`);
    if (ml.description) rows.push(`<div class="muted" style="margin-top:6px;font-size:11px;color:#555">${_h(ml.description)}</div>`);
    const srcTag = ml.manual
      ? '<span class="src-tag" style="background:#fff5e0;color:#b35900" title="Hand-added; tagged building=retail / landuse=retail in OSM, not shop=mall">~coords</span>'
      : '<span class="src-tag src-osm">OSM</span>';
    return `
      <h3>${emoji} ${ml.name ? _h(ml.name) : '—'} ${srcTag}</h3>
      ${ml.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px" dir="rtl">${_h(ml.name_ar)}</div>` : ''}
      ${rows.join('')}
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
// ===================== POI URL STATE =====================
// Active POI layers are encoded in ?layers=metro,schools,... so SEO landing
// pages (/metro/, /schools/, ...) can deep-link back to the map with the
// matching overlay pre-enabled, and so users can share a view.
// Built-in keys are the same strings poiBuiltinDefs() returns. Custom POIs
// keep their 'poi-<key>' prefix.
let _POI_DEFS = [];
function _allPoiDefs() {
  const defs = poiBuiltinDefs();
  for (const [key, def] of Object.entries(POI_DEFS)) {
    defs.push({key:'poi-'+key, label:`${def.emoji} ${def.label}`, count:(POIS[key]||[]).length, layer:POI_LAYERS[key]});
  }
  return defs;
}
function _readLayersFromUrl() {
  try {
    const raw = new URLSearchParams(window.location.search).get('layers') || '';
    return new Set(raw.split(',').map(s => s.trim()).filter(Boolean));
  } catch (e) { return new Set(); }
}
function _writeLayersToUrl(activeKeys) {
  if (typeof window === 'undefined' || window.location.protocol === 'file:') return;
  try {
    const url = new URL(window.location.href);
    if (activeKeys && activeKeys.size) {
      url.searchParams.set('layers', Array.from(activeKeys).join(','));
    } else {
      url.searchParams.delete('layers');
    }
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  } catch (e) { /* ignore */ }
}
function _applyLayersFromUrl() {
  const want = _readLayersFromUrl();
  _POI_DEFS.forEach(d => {
    const should = want.has(d.key);
    const has = map.hasLayer(d.layer);
    if (should && !has) d.layer.addTo(map);
    if (!should && has) map.removeLayer(d.layer);
  });
  // Re-sync checkboxes if list is mounted
  const el = document.getElementById('mp-poi-list');
  if (el) el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    const def = _POI_DEFS[i];
    if (inp && def) inp.checked = want.has(def.key);
  });
}
function _currentActiveLayerKeys() {
  const out = new Set();
  _POI_DEFS.forEach(d => { if (map.hasLayer(d.layer)) out.add(d.key); });
  return out;
}

function renderPoiList() {
  const el = document.getElementById('mp-poi-list');
  if (!el) return;
  _POI_DEFS = _allPoiDefs();
  el.innerHTML = _POI_DEFS.map((d,i) => {
    const checked = map.hasLayer(d.layer) ? 'checked' : '';
    return `<label data-i="${i}"><input type="checkbox" ${checked}><span class="poi-label">${d.label}</span><span class="poi-count">${d.count}</span></label>`;
  }).join('');
  el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    inp.addEventListener('change', () => {
      const d = _POI_DEFS[i];
      if (inp.checked) d.layer.addTo(map);
      else map.removeLayer(d.layer);
      _writeLayersToUrl(_currentActiveLayerKeys());
    });
  });
}
renderPoiList();
// Activate layers requested in ?layers=...
_applyLayersFromUrl();

// First render
map.fitBounds(L.geoJSON(GEOJSON).getBounds(), {padding:[20,20]});


