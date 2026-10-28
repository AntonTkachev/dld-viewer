// District detail panel: event delegation, refresh, mount → window.DetailPanel. Loads last.
(function () {
  const {
    PERIODS, S, _addApartmentsBucket, _chartTheme, _closeChartModal, _stripKnownBadFromRecord,
    destroyCharts, destroyRentCharts, destroyTimelineCharts, openChartModal, openDonutModal,
    openRoomChartModal, openVintagePathsModal, refreshRoomBreakdown, renderBody, renderInsightDonuts,
    renderPeriodChips, renderPeriodChipsRent, renderRentCharts, renderRoomChips, renderSaleCharts,
    renderStatsRent, renderStatsSale, renderTimelineCharts
  } = window._dp;

  function bindDelegates() {
    if (S._bound) return;
    S._bound = true;
    
    document.addEventListener('click', (e) => {
      
      const tabBtn = e.target.closest('[data-dp-tab]');
      if (tabBtn && S.container && S.container.contains(tabBtn)) {
        const which = tabBtn.dataset.dpTab;
        S.container.querySelectorAll('.dp-tab').forEach(b => b.classList.toggle('active', b === tabBtn));
        S.container.querySelectorAll('.dp-tab-pane').forEach(p => {
          p.classList.toggle('active', p.id === 'dp-pane-' + which);
        });
        if (which === 'rent' && S.rent) {
          destroyRentCharts();
          renderRentCharts(S.rent);
        }
        return;
      }
      
      const modalEl = document.getElementById('dp-chart-modal');
      const inPanel = (node) => (S.container && S.container.contains(node)) || (modalEl && modalEl.contains(node));

      const periodBtn = e.target.closest('[data-dp-set-period]');
      if (periodBtn && inPanel(periodBtn)) {

        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
        e.preventDefault();
        const p = periodBtn.dataset.dpSetPeriod;
        if (S.period !== p) {
          S.period = p;
          if (S.periodHref && history.pushState) {
            history.pushState({period: p}, '', S.periodHref(p));
          }
          refreshSale();
          refreshRent();
          if (S.onPeriodChange) S.onPeriodChange(p);
        }
        return;
      }

      const vinBtn = e.target.closest('[data-dp-vin-pick]');
      if (vinBtn && modalEl && modalEl.contains(vinBtn)) {
        S.vinPick = vinBtn.dataset.dpVinPick;
        openVintagePathsModal(modalEl.dataset.source || 'sale');
        return;
      }
      const engineBtn = e.target.closest('[data-dp-engine]');
      if (engineBtn && modalEl && modalEl.contains(engineBtn)) {
        const eng = engineBtn.dataset.dpEngine;
        if (S.modalEngine !== eng) {
          S.modalEngine = eng;
          try { localStorage.setItem('dp-modal-engine', eng); } catch (_) {}
          if (modalEl.dataset.metric) openChartModal(modalEl.dataset.metric, modalEl.dataset.source || 'sale');
        }
        return;
      }

      const roomBtn = e.target.closest('[data-dp-set-room]');
      if (roomBtn && inPanel(roomBtn)) {
        const k = roomBtn.dataset.dpSetRoom;
        if (S.roomFilter !== k) {
          S.roomFilter = k;
          if (S.sale) refreshSale();
          if (S.rent) refreshRent();
        }
        return;
      }
      
      const unitBtn = e.target.closest('[data-dp-rent-unit]');
      if (unitBtn && S.container && S.container.contains(unitBtn)) {
        const next = unitBtn.dataset.dpRentUnit;
        if (S.rentUnit !== next) {
          S.rentUnit = next;
          refreshRent();
        }
        return;
      }
      
      const expandBtn = e.target.closest('[data-dp-expand]');
      if (expandBtn && S.container && S.container.contains(expandBtn)) {
        e.preventDefault();
        openChartModal(expandBtn.dataset.dpExpand, expandBtn.dataset.dpSource || 'sale');
        return;
      }
      
      const expandRoomBtn = e.target.closest('[data-dp-expand-rooms]');
      if (expandRoomBtn && S.container && S.container.contains(expandRoomBtn)) {
        e.preventDefault();
        openRoomChartModal();
        return;
      }
      
      const expandDonutBtn = e.target.closest('[data-dp-expand-donut]');
      if (expandDonutBtn && S.container && S.container.contains(expandDonutBtn)) {
        e.preventDefault();
        openDonutModal(expandDonutBtn.dataset.dpExpandDonut);
        return;
      }
      
      const rbToggle = e.target.closest('[data-dp-toggle-room]');
      if (rbToggle && S.container && S.container.contains(rbToggle)) {
        const k = rbToggle.dataset.dpToggleRoom;
        if (!S.roomBreakdownHidden) S.roomBreakdownHidden = new Set();
        if (S.roomBreakdownHidden.has(k)) S.roomBreakdownHidden.delete(k);
        else S.roomBreakdownHidden.add(k);
        refreshRoomBreakdown();
        return;
      }
      
      if (e.target.id === 'dp-cm-close' || e.target.id === 'dp-chart-modal') {
        _closeChartModal();
        return;
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const el = document.getElementById('dp-chart-modal');
        if (el && el.classList.contains('open')) _closeChartModal();
      }
    });
  }
  function refreshSale() {
    if (!S.sale) return;
    const pc = S.container.querySelector('#dp-period-chips');
    if (pc) pc.innerHTML = renderPeriodChips();
    const rc = S.container.querySelector('#dp-room-chips');
    if (rc) rc.innerHTML = renderRoomChips(S.sale);
    const stEl = S.container.querySelector('#dp-stats-sale');
    if (stEl) stEl.innerHTML = renderStatsSale(S.sale);
    destroyTimelineCharts();
    renderTimelineCharts(S.sale);
    refreshRoomBreakdown();
    try { renderInsightDonuts(S.sale); } catch(e) { console.error('donuts:', e); }

    const modalEl = document.getElementById('dp-chart-modal');
    if (modalEl && modalEl.classList.contains('open') && modalEl.dataset.metric && (modalEl.dataset.source || 'sale') === 'sale') {
      openChartModal(modalEl.dataset.metric, 'sale');
    }
  }
  function refreshRent() {
    if (!S.rent) return;
    const pc = S.container.querySelector('#dp-period-chips-rent');
    if (pc) pc.innerHTML = renderPeriodChipsRent();
    const stEl = S.container.querySelector('#dp-stats-rent');
    if (stEl) stEl.innerHTML = renderStatsRent(S.rent);
    const rc = S.container.querySelector('#dp-room-chips-rent');
    if (rc) rc.innerHTML = renderRoomChips(S.rent);

    if (S.container.querySelector('#ch-rent-count')) {
      destroyRentCharts();
      renderRentCharts(S.rent);
      refreshRoomBreakdown();
    }

    const modalEl = document.getElementById('dp-chart-modal');
    if (modalEl && modalEl.classList.contains('open') && modalEl.dataset.metric && modalEl.dataset.source === 'rent') {
      openChartModal(modalEl.dataset.metric, 'rent');
    }
  }

  function mount({ container, sale, rent, title, isDubai, mode, initialPeriod, periodHref, onPeriodChange }) {
    if (!container) throw new Error('DetailPanel.mount: container required');
    destroyCharts();
    _chartTheme();
    S.container       = container;
    S.sale            = sale  || null;
    S.rent            = rent  || null;
    _stripKnownBadFromRecord(S.sale);
    _stripKnownBadFromRecord(S.rent);
    _addApartmentsBucket(S.sale);
    _addApartmentsBucket(S.rent);
    S.isDubai         = !!isDubai;
    S.mode            = mode || 'both';
    S.period          = (initialPeriod && PERIODS.find(p => p.k === initialPeriod)) ? initialPeriod : 'all';
    S.roomFilter      = [S.rent, S.sale].some(x => x && x.scope === 'home') ? 'homes' : 'all';
    S.roomBreakdownHidden = new Set();
    S.periodHref      = (typeof periodHref === 'function') ? periodHref : null;
    S.onPeriodChange  = (typeof onPeriodChange === 'function') ? onPeriodChange : null;
    S.listLinks       = arguments[0].listLinks || null;
    container.innerHTML = renderBody(S.sale, S.rent, S.mode);
    if (title) {
      const titleEl = document.getElementById('dp-title');
      if (titleEl) titleEl.textContent = title;
    }
    bindDelegates();
    if (S.mode !== 'rent' && S.sale) renderSaleCharts(S.sale);
    if (S.mode === 'rent' && S.rent) renderRentCharts(S.rent);
  }

  window.DetailPanel = { mount };
})();
