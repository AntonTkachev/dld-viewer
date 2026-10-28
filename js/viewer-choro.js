// Map viewer: choropleth, value labels, district names, popups, hover, legend.
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
