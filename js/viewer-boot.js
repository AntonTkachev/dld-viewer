// Map viewer: boot — UI wiring, initial mask/view, URL layers, deep links. Loads last.
setTimeout(() => {

  // Defensive guard for externalized data bundles. Each landing pulls
  // GEOJSON / AGGREGATES / RENT_AGGREGATES / *_PERIODS / LIFECYCLE from
  // separate <script src=…> tags now. If any of those fail to load
  // (CDN blip, stale cache, broken rebuild), the existing
  // `typeof X !== 'undefined' ? X : {}` fallbacks in the viewer-*.js files
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
    const ppBtn = e.target.closest('.leaflet-popup .pp-btn');
    if (ppBtn && typeof gtag === 'function') {
      const href = ppBtn.getAttribute('href') || '';
      const isBld = /\/buildings\/|\/search\/#/.test(href);
      gtag('event', 'select_content', {content_type: isBld ? 'building_page' : 'district_page', item_id: href});
    }
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
    let _searchGaTimer = null;
    searchInp.addEventListener('input', e => {
      _renderSearchResults(e.target.value);
      clearTimeout(_searchGaTimer);
      const q = e.target.value.trim();
      if (q.length < 2) return;
      // fire once typing pauses, so each keystroke isn't an event
      _searchGaTimer = setTimeout(() => {
        if (typeof gtag !== 'function') return;
        const empty = !document.querySelector('#search-results .sr-item');
        gtag('event', 'select_content', {content_type: empty ? 'search_empty' : 'search', item_id: q.toLowerCase()});
      }, 1500);
    });
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

if (minLevel === 99) { buildingLayer.addTo(map); _ensureBuildingsData(); }

applyMask(currentMask, currentMaskPeriod, { pushUrl: false });
if (currentView === 'table') setView('table', { pushUrl: false, force: true });

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
  // Phones open on the urban core: the whole emirate is too small to tap
  if (window.matchMedia('(max-width:640px)').matches) map.fitBounds([[25.0, 55.06], [25.30, 55.42]], {paddingTopLeft: [8, 125], paddingBottomRight: [8, 105]});
  else map.fitBounds(L.geoJSON(GEOJSON).getBounds(), {padding:[20,20]});
}
