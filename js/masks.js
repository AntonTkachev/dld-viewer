// Mask definitions (choropleth metrics). Loaded before viewer.js; parsed by scripts/build_app_v1.py.
const LIFECYCLE_PHASE_COLORS = {
  emerging:   '#7B1933',
  rising:     '#fde725',
  active:     '#21918c',
  mature:     '#5ec962',
  lagging:    '#3b528b',
  overheated: '#440154',
};
const LIFECYCLE_PHASE_TEXT = {
  emerging:   '#ffffff',
  rising:     '#0f172a',
  active:     '#ffffff',
  mature:     '#0f172a',
  lagging:    '#ffffff',
  overheated: '#ffffff',
};
const LIFECYCLE_PHASE_ORDER = ['emerging', 'rising', 'active', 'mature', 'lagging', 'overheated'];
function _lifecyclePhase(rec) {
  return (rec && rec.phase) ? rec.phase : null;
}

const _TX_P      = (typeof TX_PERIODS      !== 'undefined') ? TX_PERIODS      : {};
const _RENTS_P   = (typeof RENTS_PERIODS   !== 'undefined') ? RENTS_PERIODS   : {};
const _GROWTH_P  = (typeof GROWTH_PERIODS  !== 'undefined') ? GROWTH_PERIODS  : {};
const _LIFECYCLE = (typeof LIFECYCLE       !== 'undefined') ? LIFECYCLE       : {};
const _PAYBACK_P = (typeof PAYBACK_PERIODS !== 'undefined') ? PAYBACK_PERIODS : {};
const _YSELL_P   = (typeof YEARLY_SELL_PERIODS !== 'undefined') ? YEARLY_SELL_PERIODS : {};
const _YRENT_P   = (typeof YEARLY_RENT_PERIODS !== 'undefined') ? YEARLY_RENT_PERIODS : {};

// Median annual rent for the selected room type; empty for "all apartments" (no meaningful mix)
function _annualRentRow(p, t) {
  const per = (typeof currentMaskPeriod !== 'undefined') ? currentMaskPeriod : null;
  const r = per && _YRENT_P[per] && _YRENT_P[per][p.real_area_key];
  if (!r || !r.med) return '';
  return `<div class="stat"><span class="k">${t('pp_rent_ppsqm')}</span><span class="v">${r.med.toLocaleString('ru-RU')} ${t('unit_aed_year')}</span></div>`;
}
const _INVESTOR_P = (typeof INVESTOR_PERIODS !== 'undefined') ? INVESTOR_PERIODS : {};
const _INCOME_P   = (typeof INCOME_PERIODS   !== 'undefined') ? INCOME_PERIODS   : {};
const _FORMULA_P  = (typeof FORMULA_PERIODS  !== 'undefined') ? FORMULA_PERIODS  : {};
const _OFFPLAN_P  = (typeof OFFPLAN_PERIODS  !== 'undefined') ? OFFPLAN_PERIODS  : {};
const OFFPLAN_BREAKS  = [-10, -3, 3, 10, 25];
const OFFPLAN_PALETTE = ['#1a9850', '#91cf60', '#f1eee4', '#fdd49e', '#fc8d59', '#d73027'];

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
      { key: 'name',      labelKey: 'tv_col_district', type: 'str',    width: '40%', defaultSort: false },
      { key: 'n',         labelKey: 'tv_col_n_sales',  type: 'int',    width: '20%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'med',       labelKey: 'tv_col_median',   type: 'aed_big',width: '20%' },
      { key: 'med_ppsqm', labelKey: 'tv_col_ppsqm',    type: 'int',    width: '20%' },
    ],
  },
  rents: {
    labelKey: 'mask_rents', descKey: 'mask_rents_desc',
    periods: ['1y','3y','5y','10y','all'], defaultPeriod: 'all',
    data: {

      all:   Object.assign({},
              (typeof RENT_AGGREGATES !== 'undefined') ? RENT_AGGREGATES : {},
              _RENTS_P['all'] || {}),
      '1y':  _RENTS_P['1y']  || {},
      '3y':  _RENTS_P['3y']  || {},
      '5y':  _RENTS_P['5y']  || {},
      '10y': _RENTS_P['10y'] || {},
    },
    pluck: r => ({ real_count: r.n || 0, real_total_aed: 0, real_med_price: r.med_annual || r.med || 0, real_med_ppsqm: r.med_ppsqm || 0, real_metric: r.n || 0 }),
    legendKey: 'legend_rents', popupCountKey: 'rent_sc_contracts', showVolume: false, annualRent: true,
    tableColumns: [
      { key: 'name',                       labelKey: 'tv_col_district',      type: 'str',     width: '38%' },
      { key: 'n',                          labelKey: 'tv_col_n_rents',       type: 'int',     width: '17%', defaultSort: true, defaultSortDir: 'desc' },
      { key: r => r.med_annual || r.med,   labelKey: 'tv_col_median_annual', type: 'aed_big', width: '25%' },
      { key: 'med_ppsqm',                  labelKey: 'tv_col_ppsqm_year',    type: 'int',     width: '20%' },
    ],
  },
  growth: {
    labelKey: 'mask_growth', descKey: 'mask_growth_desc',
    periods: ['1y','3y','5y','10y','15y','all'], defaultPeriod: '5y',
    data: {
      '1y':  _GROWTH_P['1y']  || {},
      '3y':  _GROWTH_P['3y']  || {},
      '5y':  _GROWTH_P['5y']  || {},
      '10y': _GROWTH_P['10y'] || {},
      '15y': _GROWTH_P['15y'] || {},
      'all': _GROWTH_P['all'] || {},
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
      { key: 'name',         labelKey: 'tv_col_district',    type: 'str',     width: '40%' },
      { key: 'growth_pct',   labelKey: 'tv_col_growth_pct',  type: 'pct',     width: '20%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'med_now',      labelKey: 'tv_col_med_now',     type: 'int',     width: '20%' },
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
      const color = LIFECYCLE_PHASE_COLORS[phaseId];
      const textColor = LIFECYCLE_PHASE_TEXT[phaseId] || '#0f172a';
      const phaseLabel = t('lifecycle_phase_' + phaseId);
      const pill = `<span style="display:inline-block;padding:2px 8px;border-radius:10px;background:${color};color:${textColor};font-weight:600;font-size:12px">${phaseLabel}</span>`;
      const pricePct = p.real_price_pct;
      const rentPct  = p.real_rent_pct;
      // real_pipeline is a composite index (share × volume boost × delivery
      // penalty) and can exceed 1.0 — cap the human-facing "share" at 100%.
      const pipeShare = (Math.min(p.real_pipeline, 1) * 100).toFixed(0);
      const fmtPct = v => (typeof v === 'number')
        ? ((v >= 0 ? '+' : '') + v.toFixed(1) + '%')
        : '—';
      return `
        <div class="stat"><span class="k">${t('pp_lifecycle_phase')}</span><span class="v">${pill}</span></div>
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
      { key: r => Math.round(Math.min(r.pipeline || 0, 1) * 100),
                           labelKey: 'tv_col_lifecycle_pipeline', type: 'pct_int', width: '16%' },
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
    invertRamp: true,  
    overlay: r => (typeof r.years !== 'number') ? null : r.years.toFixed(1),
    legendFmt: v => v.toFixed(1),
    periodLabelKey: 'mask_room_label',
    popupRows: (p, t) => {
      if (p.real_metric === null || p.real_metric === undefined) return '';
      const yld = p.real_metric ? (100 / p.real_metric).toFixed(1) + '%' : '—';
      return `
      <div class="stat"><span class="k">${t('pp_payback_years')}</span><span class="v" style="font-weight:700">${p.real_metric.toFixed(1)} ${t('unit_years')}</span></div>
      <div class="stat"><span class="k">${t('tv_col_yield')}</span><span class="v" style="font-weight:700">${yld}</span></div>
      <div class="stat"><span class="k">${t('pp_sale_ppsqm')}</span><span class="v">${(p.real_med_price||0).toLocaleString('ru-RU')} ${t('tv_col_ppsqm')}</span></div>
      ${_annualRentRow(p, t)}
      <div class="stat"><span class="k">${t('pp_n_sale')}</span><span class="v">${(p.real_n_sale||0).toLocaleString('ru-RU')}</span></div>
      <div class="stat"><span class="k">${t('pp_n_rent')}</span><span class="v">${(p.real_n_rent||0).toLocaleString('ru-RU')}</span></div>
    `; },
    tableColumns: [
      { key: 'name',       labelKey: 'tv_col_district',    type: 'str',     width: '32%' },
      { key: 'years',      labelKey: 'tv_col_payback_yrs', type: 'yrs',     width: '17%', defaultSort: true, defaultSortDir: 'asc' },
      { key: r => r.years ? Math.round(1000 / r.years) / 10 : null,
        labelKey: 'tv_col_yield',                          type: 'pct_abs', width: '11%' },
      { key: 'sale_ppsqm', labelKey: 'tv_col_sale_ppsqm',  type: 'int',     width: '18%' },
      { key: 'rent_ppsqm', labelKey: 'tv_col_rent_ppsqm',  type: 'int',     width: '18%' },
    ],
  },
  investor: {
    labelKey: 'mask_investor', descKey: 'mask_investor_desc',
    periods: ['all','studio','1br','2br','3br','4br_plus'], defaultPeriod: 'all',
    data: {
      'all':      _INVESTOR_P['all']      || {},
      'studio':   _INVESTOR_P['studio']   || {},
      '1br':      _INVESTOR_P['1br']      || {},
      '2br':      _INVESTOR_P['2br']      || {},
      '3br':      _INVESTOR_P['3br']      || {},
      '4br_plus': _INVESTOR_P['4br_plus'] || {},
    },
    pluck: r => ({
      real_count: (r.strategy === 'offplan' ? r.n_offplan : r.n_sale) || 0,
      real_total_aed: 0,
      real_med_price: r.sale_ppsqm || 0,
      real_med_ppsqm: r.rent_ppsqm || 0,
      real_metric: (typeof r.score === 'number') ? r.score : null,
      real_strategy: r.strategy || null,
      real_yield: (typeof r.yield_pct === 'number') ? r.yield_pct : null,
      real_past1y: (typeof r.past1y_pct === 'number') ? r.past1y_pct : null,
      real_pipeline: (typeof r.pipeline === 'number') ? r.pipeline : null,
      real_offplan_ppsqm: r.offplan_ppsqm || 0,
      real_premium: (typeof r.premium_pct === 'number') ? r.premium_pct : null,
      real_fresh: (typeof r.fresh_share_pct === 'number') ? r.fresh_share_pct : null,
      real_overdue: (typeof r.overdue_share_pct === 'number') ? r.overdue_share_pct : null,
      real_vs_peak: (typeof r.vs_peak_pct === 'number') ? r.vs_peak_pct : null,
      real_n_sale: r.n_sale || 0,
      real_n_rent: r.n_rent || 0,
      real_n_offplan: r.n_offplan || 0,
    }),
    legendKey: 'legend_investor', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    periodLabelKey: 'mask_room_label',
    overlay: r => (typeof r.score === 'number') ? String(r.score) : null,
    legendFmt: v => String(Math.round(v)),
    styleExtra: p => p.real_strategy === 'offplan'
      ? { stroke: true, dashArray: '5,4', weight: 1.3, color: '#7c3aed' } : null,
    popupRows: (p, t) => {
      if (p.real_metric === null || p.real_metric === undefined) return '';
      const stratLabel = p.real_strategy === 'offplan' ? t('inv_strat_offplan') : t('inv_strat_rent');
      const stratColor = p.real_strategy === 'offplan' ? '#7c3aed' : '#0369a1';
      const head = `
      <div class="stat"><span class="k">${t('pp_investor_score')}</span><span class="v" style="font-weight:700">${p.real_metric}</span></div>
      <div class="stat"><span class="k">${t('pp_strategy')}</span><span class="v" style="color:${stratColor};font-weight:600">${stratLabel}</span></div>`;
      const past = (typeof p.real_past1y === 'number')
        ? `<div class="stat"><span class="k">${t('pp_past1y')}</span><span class="v">${p.real_past1y >= 0 ? '+' : ''}${p.real_past1y.toFixed(1)}%</span></div>`
        : '';
      if (p.real_strategy === 'offplan') {
        const prem = (typeof p.real_premium === 'number')
          ? `<div class="stat"><span class="k">${t('pp_premium')}</span><span class="v" style="font-weight:600;color:${p.real_premium <= 5 ? '#15803d' : (p.real_premium > 40 ? '#b45309' : '#0f172a')}">${p.real_premium >= 0 ? '+' : ''}${p.real_premium.toFixed(0)}%</span></div>`
          : '';
        const fresh = (typeof p.real_fresh === 'number')
          ? `<div class="stat"><span class="k">${t('pp_fresh_share')}</span><span class="v">${p.real_fresh}%</span></div>`
          : '';
        const od = (typeof p.real_overdue === 'number')
          ? `<div class="stat"><span class="k">${t('pp_overdue_share')}</span><span class="v"${p.real_overdue > 25 ? ' style="color:#b45309;font-weight:600"' : ''}>${p.real_overdue > 25 ? '⚠ ' : ''}${p.real_overdue.toFixed(0)}%</span></div>`
          : '';
        return head + `
      <div class="stat"><span class="k">${t('pp_offplan_ppsqm')}</span><span class="v">${(p.real_offplan_ppsqm||0).toLocaleString('ru-RU')} ${t('tv_col_ppsqm')}</span></div>
      ${prem}${fresh}${od}${past}
      <div class="stat"><span class="k">${t('pp_n_sale_1y')}</span><span class="v">${(p.real_n_offplan||0).toLocaleString('ru-RU')}</span></div>
    `;
      }
      const pipe = (typeof p.real_pipeline === 'number' && p.real_pipeline >= 0.5)
        ? `<div class="stat"><span class="k">${t('pp_supply_share')}</span><span class="v" style="color:#b45309;font-weight:600">⚠ ${Math.round(Math.min(p.real_pipeline, 1) * 100)}%</span></div>`
        : '';
      const peak = (typeof p.real_vs_peak === 'number')
        ? `<div class="stat"><span class="k">${t('pp_vs_peak')}</span><span class="v"${p.real_vs_peak >= 95 ? ' style="color:#b45309"' : ''}>${p.real_vs_peak}%</span></div>`
        : '';
      return head + `
      <div class="stat"><span class="k">${t('pp_yield')}</span><span class="v" style="font-weight:700">${(p.real_yield || 0).toFixed(1)}%</span></div>
      ${past}${peak}
      <div class="stat"><span class="k">${t('pp_sale_ppsqm')}</span><span class="v">${(p.real_med_price||0).toLocaleString('ru-RU')} ${t('tv_col_ppsqm')}</span></div>
      ${_annualRentRow(p, t)}
      ${pipe}
      <div class="stat"><span class="k">${t('pp_n_sale_1y')}</span><span class="v">${(p.real_n_sale||0).toLocaleString('ru-RU')}</span></div>
    `;
    },
    tableColumns: [
      { key: 'name',       labelKey: 'tv_col_district',       type: 'str',     width: '33%' },
      { key: 'score',      labelKey: 'tv_col_investor_score', type: 'int',     width: '14%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'strategy',   labelKey: 'tv_col_strategy',       type: 'strat',   width: '19%' },
      { key: 'yield_pct',  labelKey: 'tv_col_yield',          type: 'pct_abs', width: '16%' },
      { key: 'past1y_pct', labelKey: 'tv_col_past1y',         type: 'pct',     width: '18%' },
    ],
  },
  formula: {
    labelKey: 'mask_formula', descKey: 'mask_formula_desc',
    periods: ['all','studio','1br','2br','3br','4br_plus'], defaultPeriod: 'all',
    data: {
      'all':      _FORMULA_P['all']      || {},
      'studio':   _FORMULA_P['studio']   || {},
      '1br':      _FORMULA_P['1br']      || {},
      '2br':      _FORMULA_P['2br']      || {},
      '3br':      _FORMULA_P['3br']      || {},
      '4br_plus': _FORMULA_P['4br_plus'] || {},
    },
    pluck: r => ({
      real_count: r.n_sale || 0,
      real_total_aed: 0,
      real_med_price: r.sale_ppsqm || 0,
      real_med_ppsqm: r.rent_ppsqm || 0,
      real_metric: (typeof r.cash_yield_pct === 'number') ? r.cash_yield_pct : null,
      real_yield: (typeof r.yield_pct === 'number') ? r.yield_pct : null,
      real_net_yield: (typeof r.net_yield_pct === 'number') ? r.net_yield_pct : null,
      real_past1y: (typeof r.past1y_pct === 'number') ? r.past1y_pct : null,
      real_vs_peak: (typeof r.vs_peak_pct === 'number') ? r.vs_peak_pct : null,
      real_renewal: (typeof r.renewal_pct === 'number') ? r.renewal_pct : null,
      real_n_checks: (typeof r.n_checks === 'number') ? r.n_checks : null,
      real_checks: [r.c_self, r.c_deposit, r.c_cool, r.c_peak, r.c_sticky, r.c_liquid]
        .map(b => b ? '1' : '0').join(''),
      real_n_sale: r.n_sale || 0,
      real_n_rent: r.n_rent || 0,
    }),
    legendKey: 'legend_formula', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    periodLabelKey: 'mask_room_label',
    overlay: r => (typeof r.cash_yield_pct === 'number')
      ? r.cash_yield_pct.toFixed(0) + '%' : null,
    legendFmt: v => (v >= 0 ? '' : '−') + Math.abs(v).toFixed(0) + '%',
    popupRows: (p, t) => {
      if (p.real_metric === null || p.real_metric === undefined) return '';
      const mark = ok => ok
        ? '<span style="color:#15803d;font-weight:700">✓</span>'
        : '<span style="color:#b45309;font-weight:700">✗</span>';
      const c = p.real_checks || '000000';
      const fmt = (v, suf) => (v === null || v === undefined) ? '—' : v + suf;
      const row = (i, label, val) =>
        `<div class="stat"><span class="k">${mark(c[i] === '1')} ${label}</span><span class="v">${val}</span></div>`;
      return `
      <div class="stat"><span class="k">${t('pp_cash_yield')}</span><span class="v" style="font-weight:700;font-size:15px">${p.real_metric >= 0 ? '+' : ''}${p.real_metric.toFixed(1)}%/${t('unit_year_short')}</span></div>
      ${row(0, t('fx_self'),    fmt(p.real_yield && p.real_yield.toFixed(1), '%'))}
      ${row(1, t('fx_deposit'), fmt(p.real_net_yield && p.real_net_yield.toFixed(1), '%'))}
      ${row(2, t('fx_cool'),    (typeof p.real_past1y === 'number') ? ((p.real_past1y >= 0 ? '+' : '') + p.real_past1y.toFixed(1) + '%') : '—')}
      ${row(3, t('fx_peak'),    fmt(p.real_vs_peak, '%'))}
      ${row(4, t('fx_sticky'),  fmt(p.real_renewal, '%'))}
      ${row(5, t('fx_liquid'),  (p.real_n_sale || 0).toLocaleString('ru-RU'))}
      <div class="stat" style="opacity:.65;font-size:11px"><span class="k">${t('fx_assumptions')}</span><span class="v">${p.real_n_checks}/6</span></div>
    `;
    },
    tableColumns: [
      { key: 'name',           labelKey: 'tv_col_district',   type: 'str',     width: '33%' },
      { key: 'cash_yield_pct', labelKey: 'tv_col_cash_yield', type: 'pct',     width: '17%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'n_checks',       labelKey: 'tv_col_checks',     type: 'checks',  width: '18%' },
      { key: 'yield_pct',      labelKey: 'tv_col_yield',      type: 'pct_abs', width: '15%' },
      { key: 'past1y_pct',     labelKey: 'tv_col_past1y',     type: 'pct',     width: '17%' },
    ],
  },
  income: {
    labelKey: 'mask_income', descKey: 'mask_income_desc',
    periods: ['all','studio','1br','2br','3br','4br_plus'], defaultPeriod: 'all',
    data: {
      'all':      _INCOME_P['all']      || {},
      'studio':   _INCOME_P['studio']   || {},
      '1br':      _INCOME_P['1br']      || {},
      '2br':      _INCOME_P['2br']      || {},
      '3br':      _INCOME_P['3br']      || {},
      '4br_plus': _INCOME_P['4br_plus'] || {},
    },
    pluck: r => ({
      real_count: r.n_rent || 0,
      real_total_aed: 0,
      real_med_price: r.sale_ppsqm || 0,
      real_med_ppsqm: r.rent_ppsqm || 0,
      real_metric: (typeof r.score === 'number') ? r.score : null,
      real_yield: (typeof r.yield_pct === 'number') ? r.yield_pct : null,
      real_rent_trend: (typeof r.rent_trend_pct === 'number') ? r.rent_trend_pct : null,
      real_renewal: (typeof r.renewal_pct === 'number') ? r.renewal_pct : null,
      real_n_sale: r.n_sale || 0,
      real_n_rent: r.n_rent || 0,
    }),
    legendKey: 'legend_income', popupCountKey: 'rent_sc_contracts', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    periodLabelKey: 'mask_room_label',
    overlay: r => (typeof r.score === 'number') ? String(r.score) : null,
    legendFmt: v => String(Math.round(v)),
    popupRows: (p, t) => {
      if (p.real_metric === null || p.real_metric === undefined) return '';
      const trend = (typeof p.real_rent_trend === 'number')
        ? `<div class="stat"><span class="k">${t('pp_rent_trend')}</span><span class="v">${p.real_rent_trend >= 0 ? '+' : ''}${p.real_rent_trend.toFixed(1)}%</span></div>`
        : '';
      const renew = (typeof p.real_renewal === 'number')
        ? `<div class="stat"><span class="k">${t('pp_renewal')}</span><span class="v">${p.real_renewal}%</span></div>`
        : '';
      return `
      <div class="stat"><span class="k">${t('pp_investor_score')}</span><span class="v" style="font-weight:700">${p.real_metric}</span></div>
      <div class="stat"><span class="k">${t('pp_yield')}</span><span class="v" style="font-weight:700">${(p.real_yield || 0).toFixed(1)}%</span></div>
      ${trend}${renew}
      <div class="stat"><span class="k">${t('pp_sale_ppsqm')}</span><span class="v">${(p.real_med_price||0).toLocaleString('ru-RU')} ${t('tv_col_ppsqm')}</span></div>
      ${_annualRentRow(p, t)}
      <div class="stat"><span class="k">${t('pp_n_rent_1y')}</span><span class="v">${(p.real_n_rent||0).toLocaleString('ru-RU')}</span></div>
    `;
    },
    tableColumns: [
      { key: 'name',           labelKey: 'tv_col_district',       type: 'str',     width: '34%' },
      { key: 'score',          labelKey: 'tv_col_investor_score', type: 'int',     width: '14%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'yield_pct',      labelKey: 'tv_col_yield',          type: 'pct_abs', width: '16%' },
      { key: 'rent_trend_pct', labelKey: 'tv_col_rent_trend',     type: 'pct',     width: '18%' },
      { key: 'renewal_pct',    labelKey: 'tv_col_renewal',        type: 'pct_abs', width: '18%' },
    ],
  },
  offplan: {
    labelKey: 'mask_offplan', descKey: 'mask_offplan_desc',
    periods: ['all','studio','1br','2br','3br'], defaultPeriod: 'all',
    data: {
      'all':    _OFFPLAN_P['all']    || {},
      'studio': _OFFPLAN_P['studio'] || {},
      '1br':    _OFFPLAN_P['1br']    || {},
      '2br':    _OFFPLAN_P['2br']    || {},
      '3br':    _OFFPLAN_P['3br']    || {},
    },
    pluck: r => ({
      real_count: r.n_12m || 0,
      real_total_aed: 0,
      real_med_price: r.op_ppsqm || 0,
      real_med_ppsqm: r.rd_ppsqm || 0,
      real_metric: (typeof r.gap_pct === 'number') ? r.gap_pct : null,
      real_n_op: r.n_op || 0,
      real_n_rd: r.n_rd || 0,
      real_op_share: (typeof r.op_share_pct === 'number') ? r.op_share_pct : null,
      real_op_win: r.win || null,
      real_op_why: r.why || null,
      real_h_n: (typeof r.h_n === 'number') ? r.h_n : null,
      real_h_med: (typeof r.h_med_pct === 'number') ? r.h_med_pct : null,
      real_h_paid: (typeof r.h_paid_pct === 'number') ? r.h_paid_pct : null,
    }),
    legendKey: 'legend_offplan', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'diverging', allowZero: true,
    breaks: OFFPLAN_BREAKS, palette: OFFPLAN_PALETTE,
    periodLabelKey: 'mask_room_label',
    overlay: r => (typeof r.gap_pct !== 'number') ? null
                  : (r.gap_pct > 0 ? '+' : r.gap_pct < 0 ? '−' : '') + Math.abs(r.gap_pct).toFixed(0) + '%',
    overlayColor: label => label[0] === '+' ? '#b45309' : label[0] === '−' ? '#15803d' : '#1f2933',
    legendFmt: v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) + '%',
    popupRows: (p, t) => {
      const pct = v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + '%';
      const num = v => (v || 0).toLocaleString('ru-RU');
      const row = (k, v, st) => `<div class="stat"><span class="k">${k}</span><span class="v"${st ? ' style="' + st + '"' : ''}>${v}</span></div>`;
      const note = s => `<div class="muted" style="font-size:11px;color:#888;padding:2px 0">${s}</div>`;
      let html = '';
      if (typeof p.real_metric === 'number') {
        const c = p.real_metric <= -3 ? '#15803d' : p.real_metric > 10 ? '#b45309' : '#0f172a';
        html += row(t('pp_op_gap'), pct(p.real_metric), `font-weight:700;color:${c}`)
          + row(t('pp_offplan_ppsqm'), `${num(p.real_med_price)} ${t('tv_col_ppsqm')}`)
          + row(t('pp_rd_fresh_ppsqm'), `${num(p.real_med_ppsqm)} ${t('tv_col_ppsqm')}`)
          + row(t('pp_op_matched'), `${num(p.real_n_op)} / ${num(p.real_n_rd)}`)
          + (p.real_op_win === 2 ? note(t('pp_op_win2')) : '');
      } else if (p.real_op_why) {
        html += note(t('pp_op_why_' + p.real_op_why));
      }
      if (typeof p.real_op_share === 'number') html += row(t('pp_op_share'), p.real_op_share + '%');
      if (typeof p.real_h_n === 'number') {
        const per = (typeof currentMaskPeriod !== 'undefined') ? currentMaskPeriod : 'all';
        const dub = (_OFFPLAN_P[per] || {}).__dubai__;
        html += `<div style="margin-top:6px;font-weight:600;font-size:12px">${t('pp_op_hist')}</div>`
          + row(t('pp_op_hist_paid'), `${p.real_h_paid}% <span style="color:#888;font-weight:400">(${t('pp_op_hist_of').replace('{n}', p.real_h_n)})</span>`, 'font-weight:600')
          + row(t('pp_op_hist_med'), pct(p.real_h_med))
          + (dub && typeof dub.h_paid_pct === 'number' ? row(t('pp_op_hist_city'), dub.h_paid_pct + '%', 'color:#888') : '')
          + note(t('pp_op_hist_note'));
      }
      return html;
    },
    tableColumns: [
      { key: 'name',         labelKey: 'tv_col_district',  type: 'str',     width: '37%' },
      { key: 'gap_pct',      labelKey: 'tv_col_op_gap',    type: 'pct_inv', width: '21%', defaultSort: true, defaultSortDir: 'asc' },
      { key: 'op_ppsqm',     labelKey: 'tv_col_op_ppsqm',  type: 'int',     width: '21%' },
      { key: 'rd_ppsqm',     labelKey: 'tv_col_rd_ppsqm',  type: 'int',     width: '21%' },
    ],
  },
  yearly_sell: {
    labelKey: 'mask_yearly_sell', descKey: 'mask_yearly_sell_desc',
    periods: ['studio','1br','2br','3br','4br_plus','villa'], defaultPeriod: '1br',
    data: {
      'studio':   _YSELL_P['studio']   || {},
      '1br':      _YSELL_P['1br']      || {},
      '2br':      _YSELL_P['2br']      || {},
      '3br':      _YSELL_P['3br']      || {},
      '4br_plus': _YSELL_P['4br_plus'] || {},
      'villa':    _YSELL_P['villa']    || {},
    },
    pluck: r => ({
      real_count: r.n || 0,
      real_total_aed: 0,
      real_med_price: r.med || 0,
      real_med_ppsqm: r.med_ppsqm || 0,
      real_metric: r.med || null,
    }),
    legendKey: 'legend_yearly_sell', popupCountKey: 'pp_trans_ytd', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    periodLabelKey: 'mask_room_label',
    overlay: r => (typeof r.med !== 'number' || !r.med) ? null
                  : (r.med >= 1e6 ? (r.med/1e6).toFixed(1) + 'M' : Math.round(r.med/1e3) + 'K'),
    legendFmt: v => v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : Math.round(v/1e3) + 'K',
    popupRows: (p, t) => (p.real_metric === null || p.real_metric === undefined) ? '' : `
      <div class="stat"><span class="k">${t('pp_median')}</span><span class="v" style="font-weight:700">${(p.real_med_price/1e6).toFixed(2)} ${t('abbr_m')}</span></div>
      <div class="stat"><span class="k">${t('pp_sale_ppsqm')}</span><span class="v">${(p.real_med_ppsqm||0).toLocaleString('ru-RU')} ${t('tv_col_ppsqm')}</span></div>
      <div class="stat"><span class="k">${t('pp_n_sale_1y')}</span><span class="v">${(p.real_count||0).toLocaleString('ru-RU')}</span></div>
    `,
    tableColumns: [
      { key: 'name',      labelKey: 'tv_col_district',  type: 'str',     width: '34%' },
      { key: 'med',       labelKey: 'tv_col_median',    type: 'aed_big', width: '22%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'med_ppsqm', labelKey: 'tv_col_ppsqm',     type: 'int',     width: '22%' },
      { key: 'n',         labelKey: 'tv_col_n_sale_1y', type: 'int',     width: '22%' },
    ],
  },
  yearly_rent: {
    labelKey: 'mask_yearly_rent', descKey: 'mask_yearly_rent_desc',
    periods: ['studio','1br','2br','3br','4br_plus','villa'], defaultPeriod: '1br',
    data: {
      'studio':   _YRENT_P['studio']   || {},
      '1br':      _YRENT_P['1br']      || {},
      '2br':      _YRENT_P['2br']      || {},
      '3br':      _YRENT_P['3br']      || {},
      '4br_plus': _YRENT_P['4br_plus'] || {},
      'villa':    _YRENT_P['villa']    || {},
    },
    pluck: r => ({
      real_count: r.n || 0,
      real_total_aed: 0,
      real_med_price: r.med || 0,
      real_med_ppsqm: r.med_ppsqm || 0,
      real_metric: r.med || null,
    }),
    legendKey: 'legend_yearly_rent', popupCountKey: 'pp_n_rent_1y', showVolume: false,
    metricKey: 'real_metric', scaleMode: 'quantile', allowZero: true,
    periodLabelKey: 'mask_room_label',
    overlay: r => (typeof r.med !== 'number' || !r.med) ? null
                  : (r.med >= 1e6 ? (r.med/1e6).toFixed(1) + 'M' : Math.round(r.med/1e3) + 'K'),
    legendFmt: v => v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : Math.round(v/1e3) + 'K',
    popupRows: (p, t) => (p.real_metric === null || p.real_metric === undefined) ? '' : `
      <div class="stat"><span class="k">${t('pp_median_annual')}</span><span class="v" style="font-weight:700">${(p.real_med_price||0).toLocaleString('ru-RU')} AED</span></div>
      <div class="stat"><span class="k">${t('pp_n_rent_1y')}</span><span class="v">${(p.real_count||0).toLocaleString('ru-RU')}</span></div>
    `,
    tableColumns: [
      { key: 'name',      labelKey: 'tv_col_district',      type: 'str',     width: '34%' },
      { key: 'med',       labelKey: 'tv_col_median_annual', type: 'aed_big', width: '22%', defaultSort: true, defaultSortDir: 'desc' },
      { key: 'med_ppsqm', labelKey: 'tv_col_ppsqm_year',    type: 'int',     width: '22%' },
      { key: 'n',         labelKey: 'tv_col_n_rent_1y',     type: 'int',     width: '22%' },
    ],
  },
};

const PRIMARY_MASKS   = ['yearly_sell', 'yearly_rent', 'growth', 'payback', 'investor', 'income', 'formula', 'offplan'];
const SECONDARY_MASKS = ['sales', 'rents', 'lifecycle'];
