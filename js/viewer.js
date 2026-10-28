
setTimeout(() => {

  // Defensive guard for externalized data bundles. Each landing pulls
  // GEOJSON / AGGREGATES / RENT_AGGREGATES / *_PERIODS / LIFECYCLE from
  // separate <script src=…> tags now. If any of those fail to load
  // (CDN blip, stale cache, broken rebuild), the existing
  // `typeof X !== 'undefined' ? X : {}` fallbacks lower in this file
  // would silently render an empty map — worse UX than failing loud.
  // NB: bundles use top-level `const X = …` which sits in the global
  // lexical environment, NOT on `window`. `typeof window.X` would always
  // return 'undefined' even when X was successfully defined — use bare
  // `typeof X` instead, which checks the lexical scope.
  const missing = [];
  if (typeof GEOJSON         === 'undefined') missing.push('GEOJSON');
  if (typeof AGGREGATES      === 'undefined') missing.push('AGGREGATES');
  if (typeof RENT_AGGREGATES === 'undefined') missing.push('RENT_AGGREGATES');
  if (typeof TX_PERIODS          === 'undefined') missing.push('TX_PERIODS');
  if (typeof RENTS_PERIODS       === 'undefined') missing.push('RENTS_PERIODS');
  if (typeof GROWTH_PERIODS      === 'undefined') missing.push('GROWTH_PERIODS');
  if (typeof PAYBACK_PERIODS     === 'undefined') missing.push('PAYBACK_PERIODS');
  if (typeof YEARLY_SELL_PERIODS === 'undefined') missing.push('YEARLY_SELL_PERIODS');
  if (typeof YEARLY_RENT_PERIODS === 'undefined') missing.push('YEARLY_RENT_PERIODS');
  if (typeof INVESTOR_PERIODS    === 'undefined') missing.push('INVESTOR_PERIODS');
  if (typeof INCOME_PERIODS      === 'undefined') missing.push('INCOME_PERIODS');
  if (typeof FORMULA_PERIODS     === 'undefined') missing.push('FORMULA_PERIODS');
  if (typeof OFFPLAN_PERIODS     === 'undefined') missing.push('OFFPLAN_PERIODS');
  if (typeof LIFECYCLE       === 'undefined') missing.push('LIFECYCLE');
  if (missing.length) {
    console.error('viewer.js: required data bundles missing:', missing.join(', '));
    document.body.innerHTML =
      '<div style="max-width:480px;margin:80px auto;padding:32px;font:14px/1.5 system-ui;background:#fef2f2;border:1px solid #fca5a5;color:#991b1b;border-radius:8px">'
      + '<h2 style="margin:0 0 12px;font-size:18px">Data failed to load</h2>'
      + '<p style="margin:0 0 16px">Map can\'t render. Reloading usually fixes this — a CDN blip or stale cache.</p>'
      + '<p style="margin:0;font-family:monospace;font-size:12px;color:#7f1d1d">missing: '
      + missing.join(', ') + '</p>'
      + '<button onclick="location.reload()" style="margin-top:16px;padding:8px 16px;background:#dc2626;color:#fff;border:none;border-radius:6px;cursor:pointer;font:inherit">Reload</button>'
      + '</div>';
    return;
  }

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
          _ensureBuildingsData(); // preload so building results are ready by the time they type
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
  
  document.querySelectorAll('#mp-level-list .ls-btn').forEach(b => {
    b.addEventListener('click', () => {
      _switchLevel(parseInt(b.dataset.minLevel, 10));
      document.getElementById('mp-level').classList.remove('open');
    });
  });
  
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
  
  let _bootLang = currentLang;
  try {
    if (typeof window.__INITIAL_LANG__ === 'string'
        && typeof I18N !== 'undefined' && I18N[window.__INITIAL_LANG__]) {
      _bootLang = window.__INITIAL_LANG__;
    } else {

      const _pPath = ((window.location.pathname || '').slice(_BASE_PATH.length)) || '/';
      const pm = _pPath.match(/^\/(ru|en|ar|hi|zh)(?:\/|$)/);
      if (pm && typeof I18N !== 'undefined' && I18N[pm[1]]) {
        _bootLang = pm[1];
      } else {
        const qp = new URLSearchParams(window.location.search).get('lang');
        if (qp && typeof I18N !== 'undefined' && I18N[qp]) _bootLang = qp;
      }
    }
  } catch (e) {  }
  applyLang(_bootLang);

  const tvHintEl = document.getElementById('tv-hint');
  if (tvHintEl) tvHintEl.textContent = t('tv_hint');

  const bldNoteEl = document.getElementById('ls-building-note');
  if (bldNoteEl) bldNoteEl.textContent = t('bld_coverage_note');

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

function _slugify(s) {
  return (s || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function _h(s) {
  return String(s == null ? '' : s).replace(/[&<>"'`]/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;', '`':'&#96;',
  })[c]);
}
// Shared building glyph — reused in building popups and the district-search
// building rows, so both spots stay visually identical.
const _BLD_ICON_SVG = '<svg width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:-1px;margin-inline-end:2px"><rect x="4" y="3" width="16" height="18" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="7.4" y="6.5" width="2.2" height="2.2" fill="currentColor"/><rect x="14.4" y="6.5" width="2.2" height="2.2" fill="currentColor"/><rect x="7.4" y="11.4" width="2.2" height="2.2" fill="currentColor"/><rect x="14.4" y="11.4" width="2.2" height="2.2" fill="currentColor"/><rect x="7.4" y="16.3" width="2.2" height="2.2" fill="currentColor"/><rect x="14.4" y="16.3" width="2.2" height="2.2" fill="currentColor"/></svg>';

function _safeUrl(u) {
  const s = String(u == null ? '' : u).trim();

  if (/^(https?|tel|mailto):/i.test(s)) return s;

  if (/^\/[^/]/.test(s) || s === '/') return s;

  return '#';
}

const _PROJECT_SUBPATHS = new Set(['dld-viewer']);
const _BASE_PATH = (() => {
  if (typeof window === 'undefined') return '';
  const first = ((window.location.pathname || '').split('/').filter(Boolean)[0] || '');
  return _PROJECT_SUBPATHS.has(first) ? '/' + first : '';
})();
function _langUrlPrefix() {
  return _BASE_PATH + (typeof currentLang === 'string' && currentLang ? '/' + currentLang : '');
}
function _langUrlPrefixOf(lang) {
  return _BASE_PATH + (lang ? '/' + lang : '');
}

function _navigateToLang(targetLang) {
  if (!targetLang || typeof window === 'undefined') return;

  const p = (window.location.pathname || '/').slice(_BASE_PATH.length) || '/';
  let stripped = p.replace(/^\/(ru|en|ar|hi|zh)(?=\/|$)/, '') || '/';

  if (stripped === '/' || stripped === '/index.html') {
    stripped = '/sales/';
  }
  const newPath = _langUrlPrefixOf(targetLang) + stripped;
  let url;
  try { url = new URL(newPath + window.location.search + window.location.hash, window.location.origin); }
  catch (e) { window.location.href = newPath; return; }
  
  try { url.searchParams.delete('lang'); } catch (e) {  }
  window.location.href = url.pathname + (url.search || '') + (url.hash || '');
}
function _districtModePrefix(mask) {

  return (mask === 'rents' || mask === 'yearly_rent') ? 'rents' : 'sales';
}
function _districtHrefForKey(key, name, legacyKey, masterKey) {
  if (!key) return _langUrlPrefix() + '/';
  if (key === '__dubai__') {
    const mode = _districtModePrefix(typeof currentMask !== 'undefined' ? currentMask : 'sales');
    return _langUrlPrefix() + '/' + mode + '/dubai/';
  }

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

        finalMode = (SECONDARY === AGGREGATES) ? 'sales' : 'rents';
        break;
      }
    }
  }
  if (!display) display = name || key;
  const slug = _slugify(display);
  return _langUrlPrefix() + '/' + finalMode + '/' + slug + '/';
}

window.openDistrictByKey = function(key) {
  window.location.href = _districtHrefForKey(key);
};

document.body.insertAdjacentHTML('beforeend',
  '<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
  + '<defs>'
  + '<pattern id="nodata-hatch" patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">'
  +   '<line x1="0" y1="0" x2="0" y2="8" stroke="#94a3b8" stroke-width="1.4"/>'
  + '</pattern>'
  + '</defs></svg>');

const map = L.map('map', { zoomControl: false }).setView([25.12, 55.25], 10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  className: 'base-muted',
  maxZoom: 19,
}).addTo(map);
// Keep auto-panned popups clear of the top panel (it wraps to 3 rows on phones)
function _syncPopupPad() {
  const el = document.getElementById('mp-panel');
  const top = el && el.offsetParent ? Math.round(el.getBoundingClientRect().bottom) + 12 : 16;
  L.Popup.mergeOptions({autoPanPaddingTopLeft: [16, top], autoPanPaddingBottomRight: [16, 16]});
}
_syncPopupPad();
window.addEventListener('resize', _syncPopupPad);
window.addEventListener('load', _syncPopupPad);

const RAMP_VIRIDIS = ['#440154','#3b528b','#21918c','#5ec962','#fde725'];
const RAMP_BLUE    = ['#eaf2fb','#b8d0f0','#7da4e2','#3f73d4','#1d4ed8'];
const RAMP_GREEN   = ['#ebf6ee','#b6dcc2','#7bc090','#3a9a55','#188a37'];
const _PALETTE_KEY = 'dxbc_choro_palette';
const _PALETTES = {viridis: RAMP_VIRIDIS, blue: RAMP_BLUE, green: RAMP_GREEN};
const _PALETTE_ORDER = ['viridis', 'blue', 'green'];
let _paletteName = 'viridis';
try { const v = localStorage.getItem(_PALETTE_KEY); if (_PALETTES[v]) _paletteName = v; } catch (e) {}
let RAMP = _PALETTES[_paletteName];
window.togglePalette = function() {
  const next = _PALETTE_ORDER[(_PALETTE_ORDER.indexOf(_paletteName) + 1) % _PALETTE_ORDER.length];
  _paletteName = next;
  RAMP = _PALETTES[next];
  try { localStorage.setItem(_PALETTE_KEY, next); } catch (e) {}
  if (typeof renderChoro === 'function') renderChoro();
};
const METRIC_FMT = {
  count: v => Math.round(v).toLocaleString('ru-RU'),
  total_aed: v => v >= 1e9 ? (v/1e9).toFixed(2)+' '+t('abbr_b') : v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString(),
  median_price_aed: v => v >= 1e6 ? (v/1e6).toFixed(2)+' '+t('abbr_m') : v.toLocaleString(),
  avg_sqm: v => v.toLocaleString('ru-RU',{maximumFractionDigits:1}),
};
function qBreaks(vs,n){const s=vs.slice().sort((a,b)=>a-b),b=[];for(let i=1;i<n;i++)b.push(s[Math.floor(s.length*i/n)]);return b}
function lBreaks(vs,n){const lo=Math.min(...vs),hi=Math.max(...vs),b=[];for(let i=1;i<n;i++)b.push(lo+(hi-lo)*i/n);return b}
function logBreaks(vs,n){const p=vs.filter(v=>v>0);if(!p.length)return Array(n-1).fill(0);const lo=Math.log(Math.min(...p)),hi=Math.log(Math.max(...p)),b=[];for(let i=1;i<n;i++)b.push(Math.exp(lo+(hi-lo)*i/n));return b}
function classify(v,b){for(let i=0;i<b.length;i++)if(v<=b[i])return i;return b.length}

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
      if (n >= 1e4) return Math.round(n/1e3) + ' ' + t('abbr_k');
      return n.toLocaleString('ru-RU');
    }
    case 'pct':
    case 'pct_inv': return (v >= 0 ? '+' : '') + Number(v).toFixed(1) + '%';
    case 'pct_abs': return Number(v).toFixed(1) + '%';
    case 'pct_int': return Math.round(Number(v)) + '%';
    case 'yrs':     return Number(v).toFixed(1) + ' ' + t('unit_years');
    case 'checks':  return v + '/6';
    case 'strat':   return t(v === 'offplan' ? 'inv_strat_offplan' : 'inv_strat_rent');
    case 'phase':   return v;  
    default:        return String(v);
  }
}
function _tableSort(rows, col, dir) {
  const sign = dir === 'asc' ? 1 : -1;
  return rows.slice().sort((a, b) => {
    const va = _tableValue(col, a), vb = _tableValue(col, b);
    const an = (va === null || va === undefined || (typeof va === 'number' && isNaN(va))) ? 1 : 0;
    const bn = (vb === null || vb === undefined || (typeof vb === 'number' && isNaN(vb))) ? 1 : 0;
    if (an !== bn) return an - bn;  
    if (col.type === 'str' || col.type === 'strat') return sign * String(va).localeCompare(String(vb), 'ru');
    return sign * (Number(va) - Number(vb));
  });
}

const PAGE_SIZE = 25;

function _renderTvPages() {
  const dd = document.getElementById('tv-mask-dd');
  const menu = document.getElementById('tv-mask-menu');
  const cur = document.getElementById('tv-mask-current');
  const btnLbl = document.getElementById('tv-mask-btn-label');
  if (!dd || !menu || !cur) return;

  if (btnLbl) btnLbl.textContent = t('mp_label_mask') || 'Показатель';

  const curMask = MASKS[currentMask];
  cur.textContent = curMask ? t(curMask.labelKey) : '—';

  menu.innerHTML = '';
  for (const m of _SEO_MASKS) {
    const mk = MASKS[m];
    if (!mk) continue;
    const isCurrent = (m === currentMask);
    const a = document.createElement('a');
    a.className = 'tv-mask-item' + (isCurrent ? ' active' : '');
    const desc = t(mk.descKey);
    const descAttr = desc ? desc.replace(/"/g, '&quot;') : '';
    a.innerHTML = `<span class="tv-mask-item-dot"></span><span class="tv-mask-item-title"${descAttr ? ` data-tip="${descAttr}"` : ''}>${t(mk.labelKey)}${descAttr ? '<span class="tv-mask-item-hint" aria-hidden="true">?</span>' : ''}</span>`;
    if (isCurrent) {
      a.setAttribute('aria-current', 'page');
    } else {
      const href = _hrefForPage(m, 'table');
      if (href) a.href = href;
      a.addEventListener('click', e => {
        e.preventDefault();
        dd.classList.remove('open');
        applyMask(m, mk.defaultPeriod);
        if (typeof gtag === 'function') {
          gtag('event', 'select_content', {content_type: 'mask', item_id: m});
        }
      });
    }
    menu.appendChild(a);
  }

  const btn = document.getElementById('tv-mask-btn');
  if (btn && !btn._wired) {
    btn._wired = true;
    btn.addEventListener('click', e => {
      e.stopPropagation();
      dd.classList.toggle('open');
    });
    document.addEventListener('click', e => {
      if (!e.target.closest('#tv-mask-dd')) dd.classList.remove('open');
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') dd.classList.remove('open');
    });
  }
}

function _renderTvPeriods() {
  const dd = document.getElementById('tv-period-dd');
  const menu = document.getElementById('tv-period-menu');
  const cur = document.getElementById('tv-period-current');
  const btnLbl = document.getElementById('tv-period-btn-label');
  if (!dd || !menu || !cur) return;

  const mask = MASKS[currentMask];
  if (!mask || mask.periods.length <= 1) {
    dd.style.display = 'none';
    return;
  }
  dd.style.display = '';

  if (btnLbl) btnLbl.textContent = t(mask.periodLabelKey || 'mask_period_label');
  cur.textContent = _periodLabel(mask, currentMaskPeriod);

  menu.innerHTML = '';
  for (const p of mask.periods) {
    const isCurrent = (p === currentMaskPeriod);
    const a = document.createElement('a');
    a.className = 'tv-mask-item' + (isCurrent ? ' active' : '');
    a.innerHTML = `<span class="tv-mask-item-dot"></span><span class="tv-mask-item-title">${_h(_periodLabel(mask, p))}</span>`;
    if (isCurrent) {
      a.setAttribute('aria-current', 'true');
    } else {
      a.href = '#';
      a.addEventListener('click', e => {
        e.preventDefault();
        dd.classList.remove('open');
        const state = _tableState[currentMask] || (_tableState[currentMask] = {});
        state.page = 1;
        applyMask(currentMask, p);
      });
    }
    menu.appendChild(a);
  }

  const btn = document.getElementById('tv-period-btn');
  if (btn && !btn._wired) {
    btn._wired = true;
    btn.addEventListener('click', e => {
      e.stopPropagation();
      dd.classList.toggle('open');
    });
    document.addEventListener('click', e => {
      if (!e.target.closest('#tv-period-dd')) dd.classList.remove('open');
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') dd.classList.remove('open');
    });
  }
}

function _renderTvPager(page, totalPages, total) {
  const el = document.getElementById('tv-pager');
  if (!el) return;
  if (totalPages <= 1) {
    el.innerHTML = `<span class="tv-pager-info">${total.toLocaleString('ru-RU')} ${t('tv_count_label')}</span>`;
    return;
  }

  const btns = [];

  btns.push(`<button class="tv-pager-btn${page<=1?' disabled':''}" data-page="${page-1}">‹</button>`);

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
      
      const scroll = document.querySelector('#table-view .tv-scroll');
      if (scroll) scroll.scrollTop = 0;
    });
  });
}

function _dedupeTableRows(rows, cols) {
  const vcols = cols.filter(c => c.key !== 'name');
  const byKey = new Map();
  for (const r of rows) {
    const vals = vcols.map(c => _tableValue(c, r));
    if (vals.every(v => v === null || v === undefined)) continue;
    const sig = JSON.stringify(vals);
    const prev = byKey.get(sig);
    if (!prev) { byKey.set(sig, r); continue; }
    const f = _FEAT_BY_KEY.get(prev._k);
    if (f && f.properties.source === 'split-remainder') byKey.set(sig, r);
  }
  const keep = new Set(byKey.values());
  return rows.filter(r => keep.has(r) || vcols.every(c => _tableValue(c, r) == null));
}

function renderTable() {
  const mask = MASKS[currentMask];
  if (!mask || !mask.tableColumns) return;

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

      rec._k = k;
      rows.push(rec);
    }
  }
  rows = _dedupeTableRows(rows, mask.tableColumns);
  const sortCol = mask.tableColumns.find(c => _tableColIdent(c) === state.sortKey) || mask.tableColumns[0];
  rows = _tableSort(rows, sortCol, state.sortDir);

  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (state.page > totalPages) state.page = totalPages;
  const start = (state.page - 1) * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);

  const mainCol = mask.tableColumns.find(c => c.defaultSort) || mask.tableColumns[1];
  const mainIdent = mainCol ? _tableColIdent(mainCol) : null;

  const rankCol = `<col style="width:48px">`;
  const cols = rankCol + mask.tableColumns.map(c => `<col${c.width ? ' style="width:' + c.width + '"' : ''}>`).join('');
  const rankTh = `<th class="rank">#</th>`;
  const ths = rankTh + mask.tableColumns.map(c => {
    const ident = _tableColIdent(c);
    const sortedCls = (ident === state.sortKey) ? (' sorted-' + state.sortDir) : '';
    const numCls = (c.type !== 'str' && c.type !== 'strat') ? 'num' : '';
    const mainCls = ident === mainIdent ? ' main' : '';
    const cls = (numCls + mainCls + sortedCls).trim();
    const label = t(c.labelKey);

    return `<th data-col="${ident}"${cls ? ' class="' + cls + '"' : ''} data-tip="${_h(label)}">${_h(label)}</th>`;
  }).join('');

  const renderCell = (c, rec, isDubai) => {
    const v = _tableValue(c, rec);
    const isNum = c.type !== 'str' && c.type !== 'phase' && c.type !== 'strat';
    const txt = _tableFmt(c, v);
    let cls = isNum ? 'num' : '';
    if (_tableColIdent(c) === mainIdent) cls += ' main';
    if (c.type === 'pct' && typeof v === 'number' && !isDubai) cls += ' ' + (v >= 0 ? 'pos' : 'neg');
    if (c.type === 'pct_inv' && typeof v === 'number' && !isDubai) cls += ' ' + (v <= 0 ? 'pos' : 'neg');
    cls = cls.trim();
    
    if (c.type === 'phase') {
      const phaseId = c.rawKey ? c.rawKey(rec) : null;
      if (!phaseId) return `<td class="num">—</td>`;
      const color = LIFECYCLE_PHASE_COLORS[phaseId] || '#cbd5e1';
      const textColor = LIFECYCLE_PHASE_TEXT[phaseId] || '#0f172a';
      const label = t('lifecycle_phase_' + phaseId);
      return `<td class="num"><span style="display:inline-block;padding:2px 10px;border-radius:10px;background:${color};color:${textColor};font-weight:600;font-size:12px;white-space:nowrap">${_h(label)}</span></td>`;
    }

    const titleAttr = ` title="${_h(String(txt))}"`;

    if (c.type === 'strat') {
      if (!v) return `<td>—</td>`;
      const sk = v === 'offplan' ? 'offplan' : 'rent';
      return `<td${titleAttr}><span class="tv-strat ${sk}">${_h(t('tv_strat_' + sk))}</span></td>`;
    }
    if (c.type === 'checks' && typeof v === 'number') {
      const dots = Array.from({length: 6}, (_, i) => `<i${i < v ? ' class="on"' : ''}></i>`).join('');
      return `<td class="num"${titleAttr}><span class="tv-dots">${dots}</span><span class="v">${v}</span></td>`;
    }

    if (c.key === 'name') {
      const cellHtml = _h(String(txt));
      const areaKey = isDubai ? '__dubai__' : (rec && rec._k);
      const hasPolygon = isDubai || (areaKey && _FEAT_BY_KEY.has(areaKey));
      if (areaKey && hasPolygon) {

        const href = _districtHrefForKey(areaKey) || '';
        const hrefAttr = href ? ` href="${_h(href)}"` : '';
        return `<td${cls ? ' class="' + cls + '"' : ''}${titleAttr}><a class="tv-district-link" data-key="${_h(areaKey)}"${hrefAttr}>${cellHtml}</a></td>`;
      }
      return `<td${cls ? ' class="' + cls + ' tv-no-polygon"' : ' class="tv-no-polygon"'} title="${_h(t('tv_no_polygon'))}">${cellHtml}</td>`;
    }
    if (!isNum) {
      return `<td${cls ? ' class="' + cls + '"' : ''}${titleAttr}>${_h(String(txt))}</td>`;
    }

    return `<td${cls ? ' class="' + cls + '"' : ''}${titleAttr}><span class="v">${txt}</span></td>`;
  };

  const rankCell = (i, isDubai) => isDubai
    ? `<td class="rank">Σ</td>`
    : `<td class="rank">${start + i + 1}</td>`;

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

  tbl.className = 'mask-' + currentMask;
  tbl.innerHTML = `<colgroup>${cols}</colgroup><thead><tr>${ths}</tr></thead><tbody>${dubaiHtml}${bodyHtml}</tbody>`;

  _renderTvPager(state.page, totalPages, total);

  tbl.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.col;
      if (state.sortKey === k) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else {
        const clicked = mask.tableColumns.find(c => _tableColIdent(c) === k);
        state.sortKey = k; state.sortDir = (clicked && clicked.type === 'str') ? 'asc' : 'desc';
      }
      state.page = 1;
      renderTable();
    });
  });

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

function _openDistrictFromTable(areaKey) {
  if (!areaKey) return;

  if (window.matchMedia && window.matchMedia('(max-width:900px)').matches) {
    window.openDistrictByKey(areaKey);
    return;
  }
  
  if (areaKey === '__dubai__') {
    if (typeof map !== 'undefined' && map.fitBounds && typeof GEOJSON !== 'undefined' && typeof L !== 'undefined') {
      map.fitBounds(L.geoJSON(GEOJSON).getBounds(), {padding:[20,20]});
    }
    if (typeof _setSelected === 'function') _setSelected(null);
    return;
  }

  const feat = (typeof _featureForAreaKey === 'function') ? _featureForAreaKey(areaKey) : null;
  if (feat && typeof _onSearchSelect === 'function') {
    _onSearchSelect(feat);
  } else {
    window.openDistrictByKey(areaKey);
  }
}

function _periodLabel(mask, p) {
  
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

function _buildMaskRow(id, mask) {
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
  const desc = t(mask.descKey);
  const descAttr = desc ? ` data-tip="${desc.replace(/"/g, '&quot;')}"` : '';
  row.innerHTML = `
    <div class="mask-row-head">
      <div class="mask-row-radio"></div>
      <div class="mask-row-title"${descAttr}>${t(mask.labelKey)}<span class="mask-row-hint" aria-hidden="true">?</span></div>
    </div>
    ${periodHTML}
  `;
  row.addEventListener('click', e => {
    if (e.target.closest('.period-slider-wrap')) return;
    const changed = id !== currentMask;
    applyMask(id, (id === currentMask) ? currentMaskPeriod : mask.defaultPeriod);
    renderMaskList();
    if (changed && typeof gtag === 'function') {
      gtag('event', 'select_content', {content_type: 'mask', item_id: id});
    }
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
  return row;
}

function renderMaskList() {
  const list = document.getElementById('mp-mask-list');
  if (!list) return;
  list.innerHTML = '';
  
  for (const id of PRIMARY_MASKS) {
    if (MASKS[id]) list.appendChild(_buildMaskRow(id, MASKS[id]));
  }

  const expanded = _maskMoreExpanded;
  if (expanded) {
    for (const id of SECONDARY_MASKS) {
      if (MASKS[id]) list.appendChild(_buildMaskRow(id, MASKS[id]));
    }
  }

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'mask-more-toggle' + (expanded ? ' expanded' : '');
  toggle.innerHTML = `<span class="mask-more-label">${t(expanded ? 'mask_less' : 'mask_more')}</span><span class="mask-more-caret" aria-hidden="true">▼</span>`;
  toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  toggle.addEventListener('click', e => {
    e.stopPropagation();
    _maskMoreExpanded = !expanded;
    renderMaskList();
  });
  list.appendChild(toggle);

}

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

  // Instant tooltip for truncated column headers (native title has 500ms delay).
  const tblRoot = document.getElementById('tv-table');
  if (tblRoot) {
    let tip = document.getElementById('tv-th-tooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'tv-th-tooltip';
      document.body.appendChild(tip);
    }
    const show = (th) => {
      const text = th.dataset.tip;
      if (!text) return;
      tip.textContent = text;
      const r = th.getBoundingClientRect();
      tip.style.display = 'block';
      const w = tip.offsetWidth;
      let left = r.left + r.width/2 - w/2;
      left = Math.max(6, Math.min(window.innerWidth - w - 6, left));
      tip.style.left = left + 'px';
      tip.style.top = (r.bottom + 4) + 'px';
    };
    const hide = () => { tip.style.display = 'none'; };
    tblRoot.addEventListener('mouseover', e => {
      const th = e.target.closest('th[data-tip]');
      if (th) show(th);
    });
    tblRoot.addEventListener('mouseout', e => {
      if (e.target.closest('th[data-tip]')) hide();
    });
    document.querySelector('#table-view .tv-scroll')?.addEventListener('scroll', hide);
  }
})();
function _refreshViewSwitchLabel() {
  const btn = document.getElementById('view-switch');
  if (!btn) return;
  btn.innerHTML = currentView === 'map' ? `▦ ${t('view_table')}` : `⌖ ${t('view_map')}`;
}
_refreshViewSwitchLabel();

let minLevel = 0;

// Single entry point for entering/leaving buildings mode (level 99). Any
// code path that shows the buildings layer must go through this — it's the
// only one that also clears the district choropleth (minLevel filter),
// otherwise district polygons stay rendered underneath the building shapes.
function _switchLevel(lvl) {
  if (lvl === minLevel) return;
  const prevLevel = minLevel;
  minLevel = lvl;
  document.querySelectorAll('#mp-level-list .ls-btn').forEach(x => {
    const isActive = parseInt(x.dataset.minLevel, 10) === minLevel;
    x.classList.toggle('active', isActive);
    if (isActive) {
      const cur = document.getElementById('mp-level-current');
      if (cur) cur.innerHTML = x.innerHTML;
    }
  });
  if (lvl === 99 && !map.hasLayer(buildingLayer)) {
    buildingLayer.addTo(map);
    _ensureBuildingsData();
    if (typeof renderPoiList === 'function') renderPoiList();
  } else if (prevLevel === 99 && lvl !== 99 && map.hasLayer(buildingLayer)) {
    map.removeLayer(buildingLayer);
    if (typeof renderPoiList === 'function') renderPoiList();
    _writeLayersToUrl(_currentActiveLayerKeys());
  }
  if (typeof renderChoro === 'function') renderChoro();
}

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

function _segDist2(px, py, a, b) {
  let x = a[0], y = a[1], dx = b[0] - x, dy = b[1] - y;
  if (dx || dy) {
    const t = ((px - x) * dx + (py - y) * dy) / (dx * dx + dy * dy);
    if (t > 1) { x = b[0]; y = b[1]; } else if (t > 0) { x += dx * t; y += dy * t; }
  }
  dx = px - x; dy = py - y;
  return dx * dx + dy * dy;
}

// Pole of inaccessibility (Mapbox polylabel): [x, y, distance-to-edge]
function _polylabel(rings, precision) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of rings[0]) { if (x < minX) minX = x; if (y < minY) minY = y; if (x > maxX) maxX = x; if (y > maxY) maxY = y; }
  const w = maxX - minX, h = maxY - minY, size = Math.min(w, h);
  if (!size) return [minX, minY, 0];
  const dist = (x, y) => {
    let inside = false, d = Infinity;
    for (const ring of rings) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i], b = ring[j];
      if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
      d = Math.min(d, _segDist2(x, y, a, b));
    }
    return (inside ? 1 : -1) * Math.sqrt(d);
  };
  const cell = (x, y, half) => { const d = dist(x, y); return {x, y, half, d, max: d + half * Math.SQRT2}; };
  const heap = [];
  const push = c => {
    heap.push(c);
    for (let i = heap.length - 1; i > 0;) { const p = (i - 1) >> 1; if (heap[p].max >= heap[i].max) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; }
  };
  const pop = () => {
    const top = heap[0], last = heap.pop();
    if (heap.length) {
      heap[0] = last;
      for (let i = 0;;) {
        const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < heap.length && heap[l].max > heap[m].max) m = l;
        if (r < heap.length && heap[r].max > heap[m].max) m = r;
        if (m === i) break;
        [heap[m], heap[i]] = [heap[i], heap[m]]; i = m;
      }
    }
    return top;
  };
  const half0 = size / 2;
  for (let x = minX; x < maxX; x += size) for (let y = minY; y < maxY; y += size) push(cell(x + half0, y + half0, half0));
  let best = cell(minX + w / 2, minY + h / 2, 0);
  while (heap.length) {
    const c = pop();
    if (c.d > best.d) best = c;
    if (c.max - best.d <= precision) continue;
    const hh = c.half / 2;
    push(cell(c.x - hh, c.y - hh, hh)); push(cell(c.x + hh, c.y - hh, hh));
    push(cell(c.x - hh, c.y + hh, hh)); push(cell(c.x + hh, c.y + hh, hh));
  }
  return [best.x, best.y, best.d];
}

// Label anchor for a district: polylabel of its largest part, cached; r = inner radius in degrees
function _labelPoint(f) {
  if (f._lp) return f._lp;
  const g = f.geometry;
  let rings = g.coordinates;
  if (g.type === 'MultiPolygon') {
    rings = g.coordinates.reduce((a, b) => _bbox({coordinates: b}).area > _bbox({coordinates: a}).area ? b : a);
  }
  const bb = _bbox({coordinates: rings[0]});
  const span = Math.max(Math.sqrt(bb.area), 1e-6);
  const [x, y, r] = _polylabel(rings, span / 100);
  return f._lp = {ll: L.latLng(y, x), r: Math.max(r, 0)};
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
  
  GEOJSON.features.sort((a, b) => b._bboxArea - a._bboxArea);
  console.log('location levels:', counts.map((c,i)=>`L${i}=${c}`).join(' '));
})();

(function tagProjectsToDistricts() {
  if (typeof PROJECTS === 'undefined') return;

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

let choro;

function _overlayColorFor(label) {
  const s = String(label);
  const sign = s[0] === '+' ? 'pos' : (s[0] === '-' ? 'neg' : 'neu');
  return sign === 'pos' ? '#0a7f00' : sign === 'neg' ? '#b91c1c' : '#1f2933';
}

let overlayLayer = null;
let _overlayBoxes = [];
function _refreshOverlay(mask) {
  if (overlayLayer) { map.removeLayer(overlayLayer); overlayLayer = null; }
  _overlayBoxes = [];
  if (!mask || typeof mask.overlay !== 'function') return;
  const data = mask.data[currentMaskPeriod] || {};
  const zoom = map.getZoom();

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

  const sorted = items.map(i => i.num).slice().sort((a, b) => a - b);
  const lo = sorted[0];
  const hi = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.90))];
  const range = (hi - lo) || 1;
  const zoomFactor = 1 + Math.max(0, zoom - 10) * 0.20;

  overlayLayer = L.layerGroup();
  for (const item of items) {
    const f = item.f;
    let norm = Math.max(0, Math.min(1, (item.num - lo) / range));  
    if (mask.invertRamp) norm = 1 - norm;          
    const fontSize = Math.round((4 + norm * 4) * zoomFactor * 10) / 10;
    const color = mask.overlayColor ? mask.overlayColor(String(item.label)) : _overlayColorFor(item.label);
    const lp = _labelPoint(f).ll;
    const c = map.project(lp, zoom);
    const w = String(item.label).length * fontSize * 0.62 + 6, h = fontSize * 1.3;
    _overlayBoxes.push({f, x: c.x - w / 2, y: c.y - h / 2, w, h});
    const icon = L.divIcon({
      className: 'choro-overlay',
      html: `<span class="choro-overlay-text" style="font-size:${fontSize}px;color:${color}">${item.label}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
    const marker = L.marker(lp, { icon, interactive: true, keyboard: false, bubblingMouseEvents: false });

    marker.on('click', function(e) {
      L.DomEvent.stopPropagation(e);
      _openFeaturePopup(f, marker.getLatLng());
    });

    marker.addTo(overlayLayer);
  }
  overlayLayer.addTo(map);
}

map.createPane('districtNames');
map.getPane('districtNames').style.zIndex = 450;
map.getPane('districtNames').style.pointerEvents = 'none';

let namesLayer = null;

function _splitName(s) {
  if (s.length <= 14 || s.indexOf(' ') < 0) return [s];
  let cut = -1;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === ' ' && (cut < 0 || Math.abs(i - s.length / 2) < Math.abs(cut - s.length / 2))) cut = i;
  }
  return [s.slice(0, cut), s.slice(cut + 1)];
}

// District names on the map: biggest districts first, a name is skipped when it doesn't
// fit inside its polygon or would collide with an already placed name / value label
function _refreshNames() {
  if (namesLayer) { map.removeLayer(namesLayer); namesLayer = null; }
  const z = map.getZoom();
  const fs = z <= 10 ? 10 : z <= 12 ? 11 : 12;
  const lineH = fs * 1.25, pad = 4;
  const pxPerDeg = 256 * Math.pow(2, z) / 360;
  const above = new Set(_overlayBoxes.map(b => b.f));
  const placed = _overlayBoxes.slice();
  const hits = (b) => placed.some(o => b.x < o.x + o.w + pad && o.x < b.x + b.w + pad && b.y < o.y + o.h + pad && o.y < b.y + b.h + pad);
  namesLayer = L.layerGroup();
  for (const f of GEOJSON.features) {
    if (f._level !== undefined && f._level < minLevel) continue;
    const p = f.properties;
    const name = (currentLang === 'ar' && p.name_ar) ? p.name_ar : p.name;
    if (!name) continue;
    const lines = _splitName(name);
    const w = Math.max(...lines.map(l => l.length)) * fs * 0.56 + 4, h = lines.length * lineH;
    const lp = _labelPoint(f);
    const r = lp.r * pxPerDeg;
    if (2 * r < h || 3 * r < w) continue;
    const c = map.project(lp.ll, z);
    const isAbove = above.has(f);
    const box = {x: c.x - w / 2, y: isAbove ? c.y - h - 6 : c.y - h / 2, w, h};
    if (hits(box)) continue;
    placed.push(box);
    const icon = L.divIcon({
      className: 'dn-icon',
      html: `<span class="dn-label${isAbove ? ' above' : ''}" style="font-size:${fs}px">${lines.map(_h).join('<br>')}</span>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
    L.marker(lp.ll, {icon, pane: 'districtNames', interactive: false, keyboard: false}).addTo(namesLayer);
  }
  namesLayer.addTo(map);
}

map.on('zoomend', () => {
  _refreshOverlay(MASKS[currentMask]);
  _refreshNames();
});

function _featurePopupHtml(f) {
  const p = f.properties;
  const m = MASKS[currentMask] || MASKS.sales;
  const newDev = p._new_dev_count || 0;
  const newDevRow = newDev ? `<div class="stat"><span class="k">${t("new_buildings")}</span><span class="v">${newDev|0}</span></div>` : '';
  const detailsBtn = p.real_area_key
    ? `<div class="pp-actions"><a href="${_h(_safeUrl(_districtHrefForKey(p.real_area_key, p.name, p.legacy_area_key, p.master_project_key)))}" class="pp-btn">${t("pp_open")}</a></div>`
    : '';
  let bodyRows;
  if (typeof m.popupRows === 'function') {
    const rendered = m.popupRows(p, t);
    bodyRows = rendered
      ? `${rendered}${newDevRow}${detailsBtn}`
      : `${newDevRow}<div class="pp-empty">${t("no_dld_data")}</div>`;
  } else {
    const volumeRow = m.showVolume ? `<div class="stat"><span class="k">${t("pp_volume")}</span><span class="v">${(p.real_total_aed||0)>=1e9?((p.real_total_aed/1e9).toFixed(2)+' '+t('abbr_b')):((p.real_total_aed/1e6).toFixed(1)+' '+t('abbr_m'))}</span></div>` : '';
    bodyRows = p.real_count ? `
      <div class="stat"><span class="k">${t(m.popupCountKey || "pp_trans_ytd")}${p.real_match_kind==='parent'?' <span class="src-tag" style="background:#fff5e6;color:#7a4c00">parent: '+_h(p.real_parent_name||'')+'</span>':''}</span><span class="v">${p.real_count.toLocaleString('ru-RU')}</span></div>
      ${volumeRow}
      ${m.annualRent
        ? `<div class="stat"><span class="k">${t("pp_rent_ppsqm")}</span><span class="v">${(p.real_med_price||0).toLocaleString('ru-RU')} ${t('unit_aed_year')}</span></div>`
        : `<div class="stat"><span class="k">${t("pp_median")}</span><span class="v">${(p.real_med_price||0) >= 1e6 ? ((p.real_med_price/1e6).toFixed(2) + ' ' + t('abbr_m')) : (Math.round((p.real_med_price||0)/1e3) + ' ' + t('abbr_k'))}</span></div>
      <div class="stat"><span class="k">${t("pp_median_psqm")}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')}</span></div>`}
      ${newDevRow}
      ${detailsBtn}
    ` : `
      ${newDevRow}
      <div class="pp-empty">${t("no_dld_data")}</div>
    `;
  }
  const per = m.periods && m.periods.length > 1 && currentMaskPeriod !== 'all' ? ' · ' + _periodLabel(m, currentMaskPeriod) : '';
  const fill = _featureFill(f);
  return `
    <div class="pp-eyebrow">${fill ? `<i style="background:${fill}"></i>` : ''}${_h(t(m.labelKey) + per)}</div>
    <h3>${p.name ? _h(p.name) : '—'}</h3>
    ${p.name_ar ? `<div class="pp-sub">${_h(p.name_ar)}</div>` : ''}
    <div class="pp-rows">${bodyRows}</div>
  `;
}

function _featureFill(f) {
  let c = null;
  if (choro) choro.eachLayer(l => { if (l.feature === f) c = l.options.fillColor; });
  return typeof c === 'string' && c[0] === '#' ? c : null;
}

function _openFeaturePopup(f, latlng) {
  _syncPopupPad();
  L.popup().setLatLng(latlng).setContent(_featurePopupHtml(f)).openOn(map);
  if (typeof gtag === 'function') {
    gtag('event', 'select_content', {content_type: 'district', item_id: f.properties.key || f.properties.name});
  }
}

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

let _hoveredFeat = null;
let _selectedFeat = null;
let _hoverRaf = 0;
const _STYLE_HOVER    = {stroke: true, weight: 2.5, color: '#0f172a', opacity: 1};
const _STYLE_SELECTED = {stroke: true, weight: 3,   color: '#1d4ed8', opacity: 1};
const _STYLE_EDGE     = {stroke: true, weight: 0.6, color: '#0f172a', opacity: 0.15, fillOpacity: 0.65};

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

function _compactNum(v) {
  return v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e4 ? Math.round(v / 1e3) + 'K' : Math.round(v).toLocaleString('ru-RU');
}

// Segmented colour bar; ticks sit on class boundaries (n+1 labels, '' = none)
function _legendBar(colors, ticks, tips) {
  const n = colors.length;
  const cells = colors.map((c, i) => `<span style="background:${c}" title="${_h(tips[i])}"></span>`).join('');
  const marks = ticks.map((l, i) => l === '' ? ''
    : `<span class="${i === 0 ? 'lo' : i === n ? 'hi' : ''}" style="left:${i * 100 / n}%">${_h(l)}</span>`).join('');
  return `<div class="lg-bar">${cells}</div><div class="lg-ticks">${marks}</div>`;
}

// Hide inner ticks that would collide with a neighbour; end ticks always stay
function _declutterTicks(host) {
  const box = host.querySelector('.lg-ticks');
  if (!box || !box.offsetWidth) return;
  const spans = [...box.children];
  spans.forEach(s => { s.style.visibility = ''; });
  const last = spans[spans.length - 1];
  const hiLeft = last.classList.contains('hi') ? last.getBoundingClientRect().left : Infinity;
  let prevRight = -Infinity;
  for (const s of spans) {
    const r = s.getBoundingClientRect();
    const isEnd = s.classList.contains('lo') || s.classList.contains('hi');
    if (!isEnd && (r.left < prevRight + 6 || r.right > hiLeft - 6)) { s.style.visibility = 'hidden'; continue; }
    prevRight = r.right;
  }
}

function renderChoro(){
  const mask = MASKS[currentMask] || MASKS.sales;
  const metricKey = mask.metricKey || 'real_count';
  const scale     = mask.scaleMode || 'log';
  const allowZero = !!mask.allowZero;
  const isCategorical = scale === 'categorical';
  const isDiverging = scale === 'diverging';
  const ramp = isDiverging ? mask.palette : RAMP;
  const isMissing = isCategorical
    ? (f) => !f.properties.real_phase
    : (v) => v === null || v === undefined || isNaN(v) || (!allowZero && v === 0);
  
  let breaks = null;
  if (isDiverging) breaks = mask.breaks;
  else if (!isCategorical) {
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
        return {..._STYLE_EDGE, fillColor:LIFECYCLE_PHASE_COLORS[phase] || '#cbd5e1'};
      }
      const v = f.properties[metricKey], z = isMissing(v);
      if (z) return {weight:0.8,color:'#64748b',fillColor:'url(#nodata-hatch)',fillOpacity:1,dashArray:'4,3'};
      let idx = classify(v, breaks);
      if (mask.invertRamp) idx = ramp.length - 1 - idx;
      const st = {..._STYLE_EDGE, fillColor:ramp[idx]};
      return mask.styleExtra ? Object.assign(st, mask.styleExtra(f.properties)) : st;
    },
    onEachFeature: (f, layer) => {
      layer.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        _openSmallestPopup(e.latlng);
      });

      f._layer = layer;
    },
  }).addTo(map);
  choro.bringToBack();

  const title = t(mask.legendKey || 'ch_count');
  const noDataRow = `<div class="row lg-nodata"><span class="sw sw-hatch"></span>${t('legend_no_data')}</div>`;
  let html;
  if (isCategorical) {
    html = `<div class="lg-head"><span class="lg-title">${title}</span></div>`;
    for (const id of LIFECYCLE_PHASE_ORDER) {
      html += `<div class="row"><span class="sw" style="background:${LIFECYCLE_PHASE_COLORS[id]}"></span>${t('lifecycle_phase_' + id)}</div>`;
    }
    html += noDataRow;
  } else if (isDiverging) {
    const fmt = mask.legendFmt || METRIC_FMT.count;
    const tips = ramp.map((_, i) => i === 0 ? `< ${fmt(breaks[0])}` : i === ramp.length - 1 ? `> ${fmt(breaks[i - 1])}` : `${fmt(breaks[i - 1])} … ${fmt(breaks[i])}`);
    const ticks = ['', ...breaks.map(fmt), ''];
    html = `<div class="lg-head"><span class="lg-title">${title}</span></div>` + _legendBar(ramp, ticks, tips) + noDataRow;
  } else {
    const fmt = mask.legendFmt || METRIC_FMT.count;
    const vs = GEOJSON.features
      .map(f => f.properties[metricKey])
      .filter(v => !isMissing(v));
    const lo = vs.length ? Math.min(...vs) : 0;
    const hi = vs.length ? Math.max(...vs) : 0;
    const all = [lo, ...breaks, hi];
    const colors = RAMP.map((_, i) => RAMP[mask.invertRamp ? (RAMP.length - 1 - i) : i]);
    const tips = colors.map((_, i) => `${fmt(all[i])} – ${fmt(all[i + 1])}`);
    const paletteName = _paletteName.charAt(0).toUpperCase() + _paletteName.slice(1);
    html = `<div class="lg-head"><span class="lg-title">${title}</span><button type="button" class="lg-palette" onclick="togglePalette()" title="Сменить палитру (A/B-тест)">🎨 ${paletteName}</button></div>`
      + _legendBar(colors, all.map(mask.legendFmt ? fmt : _compactNum), tips) + noDataRow;
  }
  document.getElementById('legend').innerHTML = html;
  _declutterTicks(document.getElementById('legend'));
  if (typeof _updateBldLegend === 'function') _updateBldLegend();

  _refreshOverlay(mask);
  _refreshNames();
}

const metroLayer = L.layerGroup();

if (typeof TRAM_LINE !== 'undefined') METRO_LINES.features.push(TRAM_LINE);
if (typeof ETIHAD_LINE !== 'undefined') METRO_LINES.features.push(ETIHAD_LINE);
if (typeof GOLD_LINE !== 'undefined') METRO_LINES.features.push(GOLD_LINE);
for (const f of METRO_LINES.features) {
  L.geoJSON(f, {style: {color: f.properties.color, weight: 4, opacity: 0.9, dashArray: f.properties.status==='construction' ? '8,6' : null}}).addTo(metroLayer);
}
function getGroupLabel(g) { return ({red:t('metro_line_red'), green:t('metro_line_green'), blue:t('metro_line_blue'), tram:t('metro_line_tram'), gold:t('metro_line_gold'), etihad:'Etihad Rail'})[g] || g; }
const GROUP_PIN = {red:'metro-red', green:'metro-green', blue:'metro-blue', tram:'metro-tram', gold:'metro-gold', etihad:'metro-etihad'};
if (typeof TRAM_STATIONS !== 'undefined') {
  for (const s of TRAM_STATIONS) METRO_STATIONS.push(s);
}
if (typeof ETIHAD_STATIONS !== 'undefined') {
  for (const s of ETIHAD_STATIONS) METRO_STATIONS.push(s);
}
if (typeof GOLD_STATIONS !== 'undefined') {
  for (const s of GOLD_STATIONS) METRO_STATIONS.push(s);
}
// Gold Line shares physical stations with Red/Green/Etihad at 4 interchange
// points (Al Ghubaiba, BurJuman, Business Bay, JGE). To avoid duplicate pins
// stacked on the same coords, we DON'T add those four to GOLD_STATIONS.
// Instead, we patch the existing METRO_STATIONS entry — adding 'gold' to its
// groups field — so its popup correctly lists both lines and renders as
// interchange.
if (typeof GOLD_INTERCHANGES !== 'undefined') {
  for (const name of GOLD_INTERCHANGES) {
    const s = METRO_STATIONS.find(x => x.name === name);
    if (!s) continue;
    const cur = s.groups || [s.group];
    if (!cur.includes('gold')) s.groups = cur.concat('gold');
  }
}
for (const s of METRO_STATIONS) {
  const groups = s.groups || [s.group];
  const labelLines = groups.map(g => getGroupLabel(g)).join(' / ');
  const isInterchange = groups.length > 1;
  
  const primary = groups[0];
  const pinLetter = (primary === 'tram') ? 'T' : (primary === 'etihad') ? 'E' : 'M';
  const icon = L.divIcon({className:'', html:`<div class="pin ${GROUP_PIN[primary]}">${pinLetter}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => `
    <h3>🚇 ${_h(s.name || t('station_default'))} <span class="src-tag src-osm">OSM</span></h3>
    <div class="muted" style="color:#888;margin-bottom:4px">${_h(labelLines)}${isInterchange?(' · '+t('metro_interchange')):''}</div>
    ${s.line ? `<div class="stat"><span class="k">${t("metro_line")}</span><span class="v">${_h(s.line)}</span></div>` : ''}
  `);
  m.addTo(metroLayer);
}

const schoolLayer = L.layerGroup();
const _rcls = v => (v || '').replace(/\s+/g, '');
for (const s of SCHOOLS) {
  const icon = L.divIcon({className:'', html:`<div class="pin school">🏫</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => {
    const hasName = s.name && s.name !== '(unnamed school)';

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

const uniLayer = L.layerGroup();
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

const mosqueLayer = L.layerGroup();
for (const mo of MOSQUES) {
  const icon = L.divIcon({className:'', html:`<div class="pin mosque">🕌</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([mo.lat, mo.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  
  if (mo.denomination && String(mo.denomination).toLowerCase() !== 'sunni') {
    realRows.push(`<div class="stat"><span class="k">${t("mo_denom")}</span><span class="v">${_h(mo.denomination)}</span></div>`);
  }
  if (mo.addr_street) realRows.push(`<div class="stat"><span class="k">${t("mo_street")}</span><span class="v">${_h(mo.addr_street)}</span></div>`);
  if (mo.addr_city) realRows.push(`<div class="stat"><span class="k">${t("mo_city")}</span><span class="v">${_h(mo.addr_city)}</span></div>`);
  if (mo.wheelchair) realRows.push(`<div class="stat"><span class="k">${t("mo_wheel")}</span><span class="v">${mo.wheelchair==='yes'?t('yes_t'):_h(mo.wheelchair)}</span></div>`);
  if (mo.image) realRows.push(`<div class="stat"><span class="k">${t("mo_image")}</span><span class="v"><a href="${_h(_safeUrl(mo.image))}" target="_blank" rel="noopener noreferrer">${t("view_t")}</a></span></div>`);

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

    const comp = [];
    if (d.total_units > 0)     comp.push(`${d.total_units.toLocaleString('ru-RU')} ${t('pj_units_n')}`);
    if (d.total_villas > 0)    comp.push(`${d.total_villas.toLocaleString('ru-RU')} ${t('pj_villas_n')}`);
    if (d.total_buildings > 0) comp.push(`${d.total_buildings.toLocaleString('ru-RU')} ${t('pj_buildings_n')}`);
    if (d.total_lands > 0)     comp.push(`${d.total_lands.toLocaleString('ru-RU')} ${t('pj_lands_n')}`);
    if (comp.length) {
      rows.push(`<div class="stat"><span class="k">${t('pj_composition_total')}</span><span class="v" style="text-align:right;max-width:200px;font-size:11.5px">${comp.join(', ')}</span></div>`);
    }

    if (d.top_developers && d.top_developers.length) {
      const devLines = d.top_developers.slice(0, 5).map(([name, count]) =>
        `<div style="display:flex;justify-content:space-between;gap:8px;font-size:11.5px"><span dir="rtl" style="flex:1;text-align:right">${_h(name)}</span><span style="color:#888">${count|0}</span></div>`
      ).join('');
      rows.push(`<div class="stat"><span class="k">${t('pj_top_devs')}</span><span class="v" style="text-align:right;max-width:220px">${devLines}</span></div>`);
    }

    const geoNote = d.geocode_kind === 'area'
      ? `<div class="muted" style="margin-top:6px;font-size:11px;color:#888">${t('pj_geocode_area')}</div>`
      : '';

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

const buildingLayer = L.layerGroup();
const _bldShapes = new Map(); // slug → Leaflet shape, for ?bld= deep-link
// Viridis 5-step (same direction as district choropleth: low=dark purple, high=yellow)
const _BLD_RAMP = RAMP_VIRIDIS;

// BUILDINGS is fetched lazily — only when the buildings layer is actually used.
let _buildingsLoadPromise = null;
function _ensureBuildingsData() {
  if (typeof BUILDINGS !== 'undefined') return Promise.resolve();
  if (_buildingsLoadPromise) return _buildingsLoadPromise;
  _buildingsLoadPromise = new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = '/buildings/data.js?v=' + (window.__BUILDINGS_VER__ || '');
    s.onload = () => { _initBuildingShapes(); resolve(); };
    s.onerror = () => { _buildingsLoadPromise = null; resolve(); }; // let the next call retry
    document.head.appendChild(s);
  });
  return _buildingsLoadPromise;
}

function _initBuildingShapes() {
  if (typeof BUILDINGS === 'undefined') return;
  const _bldColor = (d) => _BLD_RAMP[d >= 500 ? 4 : d >= 100 ? 3 : d >= 50 ? 2 : d >= 20 ? 1 : 0];
  const _bldRadius = (d) => {
    const r = 2 + Math.log10(Math.max(1, d)) * 3;
    return Math.min(12, Math.max(3, r));
  };
  const _bldPopup = (b) => {
    const statCell = (label, val, color) =>
      `<div style="min-width:70px">
        <div style="font-size:9.5px;text-transform:uppercase;letter-spacing:.04em;color:#9ca3af;margin-bottom:1px">${label}</div>
        <div style="font-size:15px;font-weight:700;color:${color}">${val}</div>
      </div>`;
    const metaCell = (label, val) =>
      `<div style="min-width:70px">
        <div style="font-size:9.5px;text-transform:uppercase;letter-spacing:.04em;color:#9ca3af;margin-bottom:1px">${label}</div>
        <div style="font-size:12px;font-weight:500;color:#374151;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:110px">${_h(val)}</div>
      </div>`;
    const salesCell = statCell(t('bld_deals'), b.d.toLocaleString(), '#b91c1c');
    const rentCell  = b.rn != null ? statCell(t('bld_rents'), b.rn.toLocaleString(), '#1d4ed8') : '';
    const yrCell    = b.yr  ? metaCell(t('bld_built'), b.yr) : '';
    const devCell   = b.dev ? metaCell(t('bld_developer'), b.dev) : '';
    const pctCell   = b.pct != null ? metaCell(t('bld_rera_pct'), b.pct + '%') : '';
    return `
      <div style="font-weight:600;font-size:14px;margin-bottom:2px">${_BLD_ICON_SVG} ${_h(b.n)} <span class="src-tag src-osm">OSM</span></div>
      <div style="font-size:11px;color:#9ca3af;margin-bottom:10px">${_h(b.a)}</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:${yrCell||devCell||pctCell?'8px':'0'}">
        ${salesCell}${rentCell}
      </div>
      ${(yrCell||devCell||pctCell) ? `<div style="display:flex;gap:16px;flex-wrap:wrap;border-top:1px solid #f3f4f6;padding-top:8px">${yrCell}${devCell}${pctCell}</div>` : ''}
      ${b.s ? `<div style="margin-top:10px"><a href="${b.pg ? `/${currentLang}/buildings/${b.s}/` : `/search/#${b.s}`}" class="pp-btn">${t('bld_details')}</a></div>` : ''}
    `;
  };
  for (const b of BUILDINGS) {
    const fill = _bldColor(b.d);
    const vis = b.v || 'building';
    let shape;
    if (vis === 'building' && b.r && b.r.length) {
      shape = L.polygon(b.r, {
        color: '#222', weight: 0.6,
        fillColor: fill, fillOpacity: 0.78,
      });
    } else if (vis === 'compound' && b.r && b.r.length) {
      shape = L.polygon(b.r, {
        color: fill, weight: 1.5,
        fillColor: fill, fillOpacity: 0.15,
        dashArray: '4 3',
      });
    } else if (vis === 'synthetic' && b.r && b.r.length) {
      // stand-in square, no real OSM footprint
      shape = L.polygon(b.r, {
        color: '#222', weight: 0.6,
        fillColor: fill, fillOpacity: 0.6,
        dashArray: '2 2',
      });
    } else {
      shape = L.circleMarker([b.lat, b.lon], {
        radius: _bldRadius(b.d),
        color: '#222', weight: 0.6,
        fillColor: fill, fillOpacity: vis === 'approx' ? 0.5 : 0.78,
      });
    }
    shape.bindPopup(() => _bldPopup(b) + (vis === 'approx'
      ? '<div class="muted" style="font-size:11px;color:#888;margin-top:6px">≈ approximate location (community-level)</div>'
      : vis === 'compound'
      ? '<div class="muted" style="font-size:11px;color:#888;margin-top:6px">compound polygon (multi-tower)</div>'
      : vis === 'synthetic'
      ? '<div class="muted" style="font-size:11px;color:#888;margin-top:6px">⌐ no OSM footprint yet — outline is a fixed-size stand-in, not the real shape</div>'
      : ''));
    shape.addTo(buildingLayer);
    if (b.s) _bldShapes.set(b.s, {shape, b});
  }
  _updateBldLegend();
  if (typeof renderPoiList === 'function') renderPoiList();
}

// Building layer legend — appended to #legend whenever buildings layer is active.
// Called by renderChoro (after it sets innerHTML) and on layer toggle.
function _updateBldLegend() {
  const host = document.getElementById('legend');
  if (!host) return;
  const old = host.querySelector('#bld-legend-section');
  if (old) old.remove();
  if (!map.hasLayer(buildingLayer)) return;
  const labels = ['< 20', '20–49', '50–99', '100–499', '500+'];
  const sec = document.createElement('div');
  sec.id = 'bld-legend-section';
  sec.innerHTML =
    `<div class="lg-title" style="display:block;border-top:1px solid #e5e7eb;margin-top:8px;padding-top:8px;margin-bottom:4px">${t('buildings')} — ${t('bld_deals')}</div>` +
    labels.map((lbl, i) =>
      `<div class="row"><span class="sw" style="background:${_BLD_RAMP[i]}"></span>${lbl}</div>`
    ).join('') +
    `<div style="margin-top:6px;font-size:10.5px;line-height:1.35;color:#9ca3af">${_h(t('bld_coverage_note'))}</div>`;
  host.appendChild(sec);
}
buildingLayer.on('add remove', _updateBldLegend);

if (minLevel === 99) { buildingLayer.addTo(map); _ensureBuildingsData(); }

applyMask(currentMask, currentMaskPeriod, { pushUrl: false });
if (currentView === 'table') setView('table', { pushUrl: false, force: true });

function poiBuiltinDefs() {
  return [
    {key:'metro',     label:t('metro_all'),     count:METRO_STATIONS.length, layer:metroLayer},
    {key:'schools',   label:t('schools'),       count:SCHOOLS.length,        layer:schoolLayer},
    {key:'unis',      label:t('universities'),  count:UNIVERSITIES.length,   layer:uniLayer},
    {key:'medical',   label:t('medical'),       count:MEDICAL.length,        layer:medicalLayer},
    {key:'mosques',   label:t('mosques'),       count:MOSQUES.length,        layer:mosqueLayer},
    {key:'proj',      label:t('construction'),  count:PROJECTS.length,       layer:projectLayer},
    {key:'malls',     label:t('malls'),         count:MALLS.length,          layer:mallLayer},
    {key:'buildings', label:t('buildings'),     count:(typeof BUILDINGS!=='undefined'?BUILDINGS.length:null), layer:buildingLayer},
  ];
}

let _POI_DEFS = [];
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
  } catch (e) {  }
}
function _applyLayersFromUrl() {
  const want = _readLayersFromUrl();
  _POI_DEFS.forEach(d => {
    const should = want.has(d.key) || (d.key === 'buildings' && minLevel === 99);
    const has = map.hasLayer(d.layer);
    if (should && !has) d.layer.addTo(map);
    if (!should && has) map.removeLayer(d.layer);
    if (should && d.key === 'buildings') _ensureBuildingsData();
  });
  
  const el = document.getElementById('mp-poi-list');
  if (el) el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    const def = _POI_DEFS[i];
    if (inp && def) inp.checked = map.hasLayer(def.layer);
  });
}
function _currentActiveLayerKeys() {
  const out = new Set();
  _POI_DEFS.forEach(d => { if (map.hasLayer(d.layer) && !(d.key === 'buildings' && minLevel === 99)) out.add(d.key); });
  return out;
}

function renderPoiList() {
  const el = document.getElementById('mp-poi-list');
  if (!el) return;
  _POI_DEFS = poiBuiltinDefs();
  el.innerHTML = _POI_DEFS.map((d,i) => {
    const checked = map.hasLayer(d.layer) ? 'checked' : '';
    return `<label data-i="${i}"><input type="checkbox" ${checked}><span class="poi-label">${d.label}</span><span class="poi-count">${d.count ?? ''}</span></label>`;
  }).join('');
  el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    inp.addEventListener('change', () => {
      const d = _POI_DEFS[i];
      if (!inp.checked && d.key === 'buildings' && minLevel === 99) { _switchLevel(0); return; }
      if (inp.checked) d.layer.addTo(map);
      else map.removeLayer(d.layer);
      if (inp.checked && d.key === 'buildings') _ensureBuildingsData();
      _writeLayersToUrl(_currentActiveLayerKeys());
    });
  });
}
renderPoiList();

_applyLayersFromUrl();

// Deep-link: ?bld=<slug> → switch to buildings level, fly to building, open popup
(function() {
  const bld = new URLSearchParams(window.location.search).get('bld');
  if (!bld) return;
  _ensureBuildingsData().then(() => _onSearchSelectBuilding(bld));
})();

// Deep-link: ?at=lat,lon[,zoom] → centre on a point (district-page POI links) and ring it
const _atParam = (new URLSearchParams(window.location.search).get('at') || '').split(',').map(Number);
if (_atParam.length >= 2 && _atParam.slice(0, 2).every(Number.isFinite)) {
  map.setView([_atParam[0], _atParam[1]], _atParam[2] || 16);
  if ((_atParam[2] || 16) >= 15) L.circleMarker([_atParam[0], _atParam[1]], {radius: 18, color: '#2563eb', weight: 3, fill: false, interactive: false}).addTo(map);
} else if (!new URLSearchParams(window.location.search).get('bld')) {
  map.fitBounds(L.geoJSON(GEOJSON).getBounds(), {padding:[20,20]});
}

