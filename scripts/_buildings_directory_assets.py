"""Inline CSS and client-side filter/pager script of the buildings directory page."""

CSS = """
  html, body { background: #f8fafc; min-height: 100%; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 18px 16px 64px; }
  .breadcrumb { font-size: 13px; color: #6b7280; margin-bottom: 10px; }
  .breadcrumb a { color: #1d4ed8; text-decoration: none; }
  .breadcrumb a:hover { text-decoration: underline; }
  .topbar { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .topbar-controls { display: flex; gap: 10px; align-items: center; }
  .faq-link { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: #f1f5f9; border-radius: 8px; font-size: 14px; font-weight: 600; color: #6b7280; text-decoration: none; }
  .blog-link { display: inline-flex; align-items: center; height: 28px; padding: 0 10px; background: #f1f5f9; border-radius: 8px; font-size: 12px; font-weight: 600; color: #6b7280; text-decoration: none; }
  .faq-link:hover, .blog-link:hover { background: #e2e8f0; color: #1d4ed8; }
  h1 { font-size: 24px; margin: 0 0 4px; line-height: 1.25; }
  .lede { font-size: 14px; color: #6b7280; margin: 0 0 20px; }
  .load-err { color: #b91c1c; font-size: 13px; margin: -10px 0 16px; }
  .langswitch-dd { position: relative; }
  .langswitch-dd > summary { list-style: none; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; background: #f1f5f9; border-radius: 8px; font-size: 12px; font-weight: 600; color: #6b7280; user-select: none; }
  .langswitch-dd > summary::-webkit-details-marker { display: none; }
  .langswitch-dd > summary::marker { content: ""; }
  .langswitch-dd > summary .globe { font-size: 14px; }
  .langswitch-dd > summary .lang-current { color: #1d4ed8; }
  .langswitch-dd > summary .caret { font-size: 10px; opacity: .6; }
  .langswitch-dd[open] > summary { background: #e2e8f0; }
  .langswitch-dd .lang-menu { position: absolute; top: calc(100% + 4px); inset-inline-end: 0; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 4px; min-width: 140px; box-shadow: 0 6px 16px rgba(15,23,42,0.08); display: flex; flex-direction: column; z-index: 500; }
  .langswitch-dd .lang-menu a { padding: 7px 10px; border-radius: 6px; font-size: 13px; text-decoration: none; color: #374151; }
  .langswitch-dd .lang-menu a:hover { background: #f3f4f6; }
  .langswitch-dd .lang-menu a.active { background: #1d4ed8; color: #fff; font-weight: 600; }

  .filters {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 16px;
  }
  .fg { display: flex; flex-direction: column; gap: 3px; }
  .fg label { font-size: 10.5px; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
  .fg input, .fg select {
    height: 34px; padding: 0 10px; font-size: 13px; font-family: inherit;
    border: 1px solid #d1d5db; border-radius: 8px; background: #fff;
    color: #111; outline: none; transition: border-color .15s; box-sizing: border-box;
  }
  .fg input:focus, .fg select:focus { border-color: #1d4ed8; }
  .fg-name input { width: 200px; }
  .fg-area input { width: 180px; }
  .yr-row { display: flex; align-items: center; gap: 5px; }
  .yr-num { width: 74px; height: 34px; padding: 0 8px; font-size: 13px; font-family: inherit;
            border: 1px solid #d1d5db; border-radius: 8px; background: #fff;
            color: #111; outline: none; box-sizing: border-box; }
  .yr-num:focus { border-color: #1d4ed8; }
  .yr-sep { color: #94a3b8; font-size: 13px; flex-shrink: 0; }

  .fg-dev { position: relative; }
  .fg-dev input { width: 210px; padding-inline-end: 28px; cursor: default; }
  .fg-dev input.has-selection { color: #111; font-weight: 500; }
  .fg-dev input::placeholder { color: #94a3b8; font-weight: 400; }
  .dev-arrow { position: absolute; inset-inline-end: 8px; bottom: 8px; pointer-events: none; color: #94a3b8; font-size: 11px; }
  .dev-dropdown {
    display: none; position: absolute; top: calc(100% + 4px); inset-inline-start: 0;
    min-width: 260px; z-index: 400;
    background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
    box-shadow: 0 8px 28px rgba(0,0,0,.12); max-height: 320px;
    overflow-y: auto; overflow-x: hidden;
  }
  .dev-dropdown.open { display: block; }
  .dev-search-wrap { padding: 8px 10px 6px; border-bottom: 1px solid #f3f4f6; position: sticky; top: 0; background: #fff; z-index: 1; }
  .dev-search {
    width: 100%; box-sizing: border-box; height: 30px; padding: 0 9px;
    font-size: 12.5px; font-family: inherit; border: 1px solid #e5e7eb;
    border-radius: 6px; background: #f8fafc; outline: none; color: #111;
  }
  .dev-search:focus { border-color: #1d4ed8; background: #fff; }
  .dev-chips { display: flex; flex-wrap: wrap; gap: 4px; padding: 7px 10px 4px; border-bottom: 1px solid #f3f4f6; }
  .dev-chips:empty { display: none; }
  .dev-chip {
    display: inline-flex; align-items: center; gap: 3px;
    padding: 2px 7px; border-radius: 5px;
    font-size: 11.5px; font-weight: 500; white-space: nowrap;
    background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8;
  }
  .dev-chip.zone { background: #ede9fe; border-color: #c4b5fd; color: #6d28d9; }
  .chip-x { cursor: pointer; font-size: 13px; line-height: 1; opacity: .55; border: none; background: none; padding: 0; color: inherit; font-family: inherit; }
  .chip-x:hover { opacity: 1; }
  .dev-grp-label {
    padding: 6px 11px 3px; font-size: 10px; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: .06em;
    position: sticky; top: 44px; background: #fff; z-index: 1;
  }
  .dev-opt {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; cursor: pointer; font-size: 13px; color: #111;
    border-bottom: 1px solid #f9fafb; user-select: none;
  }
  .dev-opt:last-child { border-bottom: none; }
  .dev-opt:hover { background: #f8fafc; }
  .dev-opt.sel { background: #f0fdf4; }
  .dev-opt-check { color: #16a34a; font-size: 12px; flex-shrink: 0; width: 14px; }
  .dev-opt-name { flex: 1; }
  .dev-opt-badge { font-size: 10px; font-weight: 600; padding: 1px 5px; border-radius: 4px; background: #ede9fe; color: #6d28d9; flex-shrink: 0; }
  .dev-empty { padding: 12px; text-align: center; font-size: 13px; color: #94a3b8; }

  .btn-reset {
    height: 34px; padding: 0 14px; font-size: 13px; font-family: inherit;
    border: 1px solid #e5e7eb; border-radius: 8px; background: #f9fafb;
    color: #374151; cursor: pointer; transition: background .12s; flex-shrink: 0;
  }
  .btn-reset:hover { background: #f3f4f6; }

  .results-bar { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; color: #6b7280; margin-bottom: 10px; }
  .sort-wrap { display: flex; gap: 6px; align-items: center; }
  .sort-wrap label { font-size: 12px; color: #6b7280; }
  .sort-wrap select { height: 30px; padding: 0 8px; font-size: 12px; font-family: inherit; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; }

  .tbl-wrap { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    padding: 10px 12px; font-size: 11px; text-transform: uppercase;
    letter-spacing: .04em; color: #6b7280; font-weight: 600;
    border-bottom: 1px solid #e5e7eb; text-align: start;
    white-space: nowrap; background: #f8fafc;
  }
  th.num, td.num { text-align: end; font-variant-numeric: tabular-nums; }
  thead th.sortable { cursor: pointer; user-select: none; }
  thead th.sortable:hover { color: #374151; }
  thead th.sort-active { color: #1d4ed8; }
  .sort-icon { display: inline-block; margin-inline-start: 3px; font-size: 10px; opacity: .5; }
  thead th.sort-active .sort-icon { opacity: 1; }
  tbody tr { border-bottom: 1px solid #f3f4f6; transition: background .1s; cursor: pointer; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: #eff6ff; }
  tbody td { padding: 9px 12px; font-size: 13px; color: #111; vertical-align: middle; }
  tbody td.num { color: #374151; }
  .td-name { font-weight: 500; }
  .td-name .bld-a { color: inherit; text-decoration: none; }
  .td-area { color: #6b7280; font-size: 11.5px; margin-top: 2px; }
  .td-area .area-a { color: inherit; text-decoration: none; border-bottom: 1px dotted #cbd5e1; }
  .td-area .area-a:hover { color: #1d4ed8; }
  .yr-plan, .yr-est, .rn-proj { cursor: help; }
  .yr-plan { color: #92400e; font-size: 12px; white-space: nowrap; }
  .rn-proj { border-bottom: 1px dotted #94a3b8; }
  .proj-note { display: flex; align-items: center; gap: 8px; background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; border-radius: 8px; padding: 6px 10px; font-size: 13px; margin-bottom: 12px; width: fit-content; }
  .proj-note button { border: none; background: none; color: inherit; cursor: pointer; font-size: 15px; line-height: 1; padding: 0; }
  .btn-map { display: inline-flex; align-items: center; font-size: 13px; font-weight: 600; color: #1d4ed8; text-decoration: none; margin-inline-start: 6px; opacity: .75; transition: opacity .12s; }
  .proj-note[hidden] { display: none; }
  .btn-map:hover { opacity: 1; }
  .badge-zone {
    display: inline-block; font-size: 10px; font-weight: 600;
    padding: 1px 5px; border-radius: 4px; margin-inline-start: 5px;
    background: #ede9fe; color: #6d28d9; vertical-align: middle; white-space: nowrap;
  }
  .stbadge { display: inline-block; padding: 2px 7px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space: nowrap; }
  .stbadge-FINISHED { background: #ecfdf5; color: #047857; }
  .stbadge-ACTIVE { background: #dbeafe; color: #1d4ed8; }
  .stbadge-NOT_STARTED { background: #fef3c7; color: #92400e; }
  .stbadge-PENDING { background: #fff7ed; color: #c2410c; }
  .stbadge-CONDITIONAL_ACTIVATING { background: #f1f5f9; color: #475569; }
  .stbadge-FRIEZED { background: #fee2e2; color: #991b1b; }
  .pct { margin-inline-start: 6px; font-size: 11.5px; color: #475569; font-variant-numeric: tabular-nums; }
  .mute { color: #94a3b8; font-style: italic; }

  .pager { display: flex; justify-content: center; align-items: center; gap: 8px; margin-top: 18px; font-size: 13px; }
  .pager button {
    padding: 6px 14px; border: 1px solid #d1d5db; border-radius: 7px;
    background: #fff; color: #374151; cursor: pointer; font-size: 13px;
    font-family: inherit; transition: background .12s;
  }
  .pager button:hover:not(:disabled) { background: #f3f4f6; }
  .pager button:disabled { opacity: .4; cursor: default; }
  .pager .pi { color: #6b7280; }
  .empty { padding: 40px 0; text-align: center; color: #94a3b8; font-size: 14px; }
  .nav-foot { margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 13.5px; display: flex; gap: 18px; flex-wrap: wrap; }
  .nav-foot a { color: #1d4ed8; text-decoration: none; }
  [dir="rtl"] .fg label, [dir="rtl"] thead th, [dir="rtl"] .dev-grp-label { letter-spacing: 0; }

  @media (max-width: 700px) {
    .fg-name input, .fg-area input, .fg-dev input { width: 100%; }
    .yr-num { flex: 1; }
    .filters { flex-direction: column; align-items: stretch; }
    .col-dev, .col-yr, .col-pct { display: none; }
  }
"""

JS = r"""
const PAGE = __PAGE__;
let ALL = [], FILTERED = [], DEV_LIST = [], page = 0;
let selectedDevs = new Set();
let yrSort = null;

const $ = id => document.getElementById(id);
const fName = $('fName'), fArea = $('fArea'), fYr1 = $('fYr1'), fYr2 = $('fYr2');
const thBuilt = $('thBuilt'), builtIcon = $('builtIcon');
const devTrigger = $('devTrigger'), devDrop = $('devDropdown'), devSearch = $('devSearch');
const devChips = $('devChips'), devList = $('devList'), sortBy = $('sortBy');
const tBody = $('tBody'), pager = $('pager'), pInfo = $('pInfo'), pPrev = $('pPrev'), pNext = $('pNext');
const emptyMsg = $('emptyMsg'), resCount = $('resultCount');

const NUM_FMT = new Intl.NumberFormat(INTL_LOCALE);
const PLURAL = new Intl.PluralRules(INTL_LOCALE);
function fmt(n){ return n != null ? NUM_FMT.format(n) : '—'; }
function esc(s){ return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function lc(s){ return (s || '').toLowerCase(); }
function tpl(s, o){ return s.replace(/\{(\w+)\}/g, (_, k) => o[k]); }
function countLabel(n){ return tpl(COPY.count[PLURAL.select(n)] || COPY.count.other, {n: fmt(n)}); }
const MUTE = '<span class="mute">—</span>';

function yrPass(byr){
  const lo = parseInt(fYr1.value) || null, hi = parseInt(fYr2.value) || null;
  if (!lo && !hi) return true;
  if (byr == null) return true; // unknown year is not excluded
  if (lo && byr < lo) return false;
  if (hi && byr > hi) return false;
  return true;
}

thBuilt.addEventListener('click', () => {
  yrSort = yrSort === 'asc' ? 'desc' : 'asc';
  sortBy.value = yrSort === 'asc' ? 'yr_asc' : 'yr_desc';
  builtIcon.textContent = yrSort === 'asc' ? '↑' : '↓';
  thBuilt.classList.add('sort-active');
  applyFilters();
});
sortBy.addEventListener('change', () => {
  if (!sortBy.value.startsWith('yr')){ yrSort = null; builtIcon.textContent = '↕'; thBuilt.classList.remove('sort-active'); }
  applyFilters();
});

function buildDevList(){
  const brands = new Set(), zones = new Set();
  ALL.forEach(b => { if (b.dev) (b.dz ? zones : brands).add(b.dev); });
  DEV_LIST = [
    ...[...brands].sort().map(n => ({name: n, isZone: false})),
    ...[...zones].sort().map(n => ({name: n, isZone: true})),
  ];
}
function optHtml(d){
  const s = selectedDevs.has(d.name);
  return `<div class="dev-opt${s ? ' sel' : ''}" data-dev="${esc(d.name)}">
    <span class="dev-opt-check">${s ? '✓' : ''}</span>
    <span class="dev-opt-name">${esc(d.name)}</span>
    ${d.isZone ? `<span class="dev-opt-badge">${esc(COPY.zone_badge)}</span>` : ''}
  </div>`;
}
function renderDevList(){
  const q = lc(devSearch.value);
  const items = q ? DEV_LIST.filter(d => lc(d.name).includes(q)) : DEV_LIST;
  if (!items.length){ devList.innerHTML = `<div class="dev-empty">${esc(COPY.no_matches)}</div>`; return; }
  const brands = items.filter(d => !d.isZone), zones = items.filter(d => d.isZone);
  let h = '';
  if (brands.length){ if (!q) h += `<div class="dev-grp-label">${esc(COPY.grp_brand)}</div>`; brands.forEach(d => h += optHtml(d)); }
  if (zones.length){ if (!q) h += `<div class="dev-grp-label">${esc(COPY.grp_zone)}</div>`; zones.forEach(d => h += optHtml(d)); }
  devList.innerHTML = h;
}
function renderChips(){
  devChips.innerHTML = [...selectedDevs].map(name => {
    const d = DEV_LIST.find(x => x.name === name);
    return `<span class="dev-chip${d && d.isZone ? ' zone' : ''}">${esc(name)}<button class="chip-x" data-dev="${esc(name)}">×</button></span>`;
  }).join('');
}
function updateTriggerText(){
  if (!selectedDevs.size){ devTrigger.value = ''; devTrigger.classList.remove('has-selection'); return; }
  const names = [...selectedDevs];
  devTrigger.value = names.length === 1 ? names[0] : names.slice(0, 2).join(', ') + (names.length > 2 ? ` +${names.length - 2}` : '');
  devTrigger.classList.add('has-selection');
}
function toggleDev(name){
  selectedDevs.has(name) ? selectedDevs.delete(name) : selectedDevs.add(name);
  renderChips(); renderDevList(); updateTriggerText(); applyFilters();
}
devTrigger.addEventListener('mousedown', e => {
  e.preventDefault();
  const wasOpen = devDrop.classList.contains('open');
  devDrop.classList.toggle('open', !wasOpen);
  if (!wasOpen){ devSearch.value = ''; renderDevList(); devSearch.focus(); }
});
devSearch.addEventListener('input', renderDevList);
devList.addEventListener('mousedown', e => { e.preventDefault(); const o = e.target.closest('.dev-opt'); if (o) toggleDev(o.dataset.dev); });
devChips.addEventListener('mousedown', e => { e.preventDefault(); const x = e.target.closest('.chip-x'); if (x) toggleDev(x.dataset.dev); });
document.addEventListener('mousedown', e => { if (!e.target.closest('.fg-dev')) devDrop.classList.remove('open'); });

function areaName(b){ return b.ad || b.a || ''; }
function bname(b){ return (LANG === 'ar' && b.na) || b.n; }
function areaLabel(b){ const a = areaName(b), m = AREAS[a]; return (LANG === 'ar' && m && m[1]) || a; }
function areaHay(b){ return lc(b.a + '|' + areaName(b) + '|' + areaLabel(b)); }

function applyFilters(){
  const name = lc(fName.value.trim()), area = lc(fArea.value.trim());
  FILTERED = ALL.filter(b =>
    (!PROJ_SLUGS || PROJ_SLUGS.has(b.s)) &&
    (!name || lc(b.n).includes(name) || (b.na && b.na.includes(name)) || (b.pj && lc(b.pj).includes(name))) &&
    (!area || areaHay(b).includes(area)) &&
    yrPass(b.yr) &&
    (!selectedDevs.size || selectedDevs.has(b.dev))
  );
  const s = sortBy.value;
  FILTERED.sort((a, b) =>
    s === 'tx' ? b.tx - a.tx :
    s === 'az' ? bname(a).localeCompare(bname(b)) :
    s === 'yr_asc' ? (a.yr ?? 9999) - (b.yr ?? 9999) :
                     (b.yr ?? -1) - (a.yr ?? -1)
  );
  page = 0; render();
}

function statusHtml(b){
  if (!b.st) return MUTE;
  const pct = b.pct != null && b.st !== 'FINISHED' ? `<span class="pct">${fmt(b.pct)}%</span>` : '';
  return `<span class="stbadge stbadge-${esc(b.st)}">${esc(COPY['st_' + b.st] || b.st)}</span>${pct}`;
}
function yrHtml(b){
  if (b.yr == null) return MUTE;
  if (b.yp) return `<span class="yr-plan" title="${esc(COPY.yr_plan_title)}">${b.yr} · ${esc(COPY.yr_plan)}</span>`;
  if (b.yre) return `<span class="yr-est" title="${esc(COPY.yr_est_title)}">≈${b.yr}</span>`;
  return String(b.yr);
}
function rnHtml(b){
  if (!b.rn) return MUTE;
  return b.rs ? `<span class="rn-proj" title="${esc(tpl(COPY.rn_proj_title, {n: b.rs}))}">${fmt(b.rn)}</span>` : fmt(b.rn);
}
function areaHtml(b){
  const m = AREAS[areaName(b)], label = esc(areaLabel(b));
  let h = m && m[0] ? `<a class="area-a" href="/${LANG}/sales/${m[0]}/" title="${esc(COPY.area_title)}">${label}</a>` : label;
  return b.pj ? h + ' · ' + esc(b.pj) : h;
}
function rowHtml(b){
  const s = encodeURIComponent(b.s);
  const dev = b.dev ? esc(b.dev) + (b.dz ? `<span class="badge-zone">${esc(COPY.zone_badge)}</span>` : '') : MUTE;
  const mp = b.m ? `<a class="btn-map" href="/${LANG}/sales/?bld=${s}" title="${esc(COPY.map_title)}">↗</a>` : '';
  const href = b.pg ? `/${LANG}/buildings/${s}/` : `/search/#${s}`;
  return `<tr data-s="${esc(b.s)}" data-h="${href}"><td class="td-name"><a class="bld-a" href="${href}">${esc(bname(b))}</a>${mp}`
    + `<div class="td-area">${areaHtml(b)}</div></td>`
    + `<td class="num col-yr">${yrHtml(b)}</td><td class="col-dev">${dev}</td>`
    + `<td class="col-pct">${statusHtml(b)}</td>`
    + `<td class="num">${fmt(b.tx)}</td><td class="num">${rnHtml(b)}</td></tr>`;
}
function render(){
  const total = FILTERED.length;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  page = Math.min(page, pages - 1);
  const slice = FILTERED.slice(page * PAGE, page * PAGE + PAGE);
  resCount.textContent = countLabel(total);
  if (!slice.length){ tBody.innerHTML = ''; emptyMsg.style.display = ''; pager.style.display = 'none'; return; }
  emptyMsg.style.display = 'none';
  tBody.innerHTML = slice.map(rowHtml).join('');
  if (pages > 1){
    pager.style.display = '';
    pInfo.textContent = tpl(COPY.page, {p: fmt(page + 1), n: fmt(pages)});
    pPrev.disabled = page === 0; pNext.disabled = page >= pages - 1;
  } else pager.style.display = 'none';
}

tBody.addEventListener('click', e => {
  if (e.target.closest('a')) return;
  const tr = e.target.closest('tr[data-h]');
  if (tr) location.href = tr.dataset.h;
});
[fName, fArea, fYr1, fYr2].forEach(el => el.addEventListener('input', applyFilters));
pPrev.addEventListener('click', () => { page--; render(); window.scrollTo(0, 0); });
pNext.addEventListener('click', () => { page++; render(); window.scrollTo(0, 0); });
function clearProject(){
  PROJ_SLUGS = null; $('projNote').hidden = true;
  const u = new URL(location.href); u.searchParams.delete('project'); history.replaceState(null, '', u);
}
$('projClear').addEventListener('click', () => { clearProject(); applyFilters(); });
$('btnReset').addEventListener('click', () => {
  if (PROJ_SLUGS) clearProject();
  fName.value = ''; fArea.value = ''; fYr1.value = ''; fYr2.value = '';
  selectedDevs.clear(); renderChips(); updateTriggerText();
  yrSort = null; builtIcon.textContent = '↕'; thBuilt.classList.remove('sort-active');
  sortBy.value = 'tx'; applyFilters();
});

const params = new URLSearchParams(location.search);
if (params.get('q')) fName.value = params.get('q');
const projParam = params.get('project');
let PROJ_SLUGS = null;
const projReady = !projParam ? Promise.resolve() :
  fetch('/buildings/project-index.json').then(r => r.json()).then(d => {
    PROJ_SLUGS = new Set(d[projParam] || []);
    $('projNoteText').textContent = tpl(COPY.project_filter, {no: projParam});
    $('projNote').hidden = false;
  }).catch(() => {});

Promise.all([fetch('/buildings/search-index.json').then(r => { if (!r.ok) throw 0; return r.json(); }), projReady])
  .then(([data]) => { ALL = data; buildDevList(); applyFilters(); })
  .catch(() => { $('loadErr').hidden = false; });
"""
