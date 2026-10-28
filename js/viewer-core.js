// Map viewer: shared helpers, URL/lang routing, Leaflet map, colour ramps. Loads first.
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
