// Map viewer: table view and mask picker.
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
    slider.addEventListener('change', () => {
      const p = mask.periods[parseInt(slider.value, 10)];
      if (p && typeof gtag === 'function') {
        gtag('event', 'select_content', {content_type: 'period', item_id: id + ':' + p});
      }
    });
  }
  row.querySelectorAll('.period-tick').forEach(tick => {
    tick.addEventListener('click', e => {
      e.stopPropagation();
      const i = parseInt(tick.dataset.idx, 10);
      const p = mask.periods[i];
      if (p) { applyMask(id, p); renderMaskList(); }
      if (p && typeof gtag === 'function') {
        gtag('event', 'select_content', {content_type: 'period', item_id: id + ':' + p});
      }
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
