// Map viewer: lazily loaded buildings layer.
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
    shape.on('popupopen', () => {
      if (typeof gtag === 'function') {
        gtag('event', 'select_content', {content_type: 'building', item_id: b.s || b.n});
      }
    });
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
