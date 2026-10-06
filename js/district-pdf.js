(function () {
'use strict';

const SQM_TO_SQFT = 10.7639;
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ROOM_LABEL = { studio:'Studio', '1br':'1 BR', '2br':'2 BR', '3br':'3 BR', '4br+':'4+ BR', villa:'Villa', other:'Other' };
const YIELD_ROOMS = ['studio','1br','2br','3br','4br+'];
const RESIDENTIAL_RENT_SUBS = new Set(['Flat','Villa','Studio','Penthouse']);

let CTX = null;

function fmtAEDFull(v) { return v ? Math.round(v).toLocaleString('en-US') : '—'; }
function fmtK(v) {
  if (v >= 1e6) return (v/1e6).toFixed(1) + 'M';
  if (v >= 1e3) return Math.round(v/1e3) + 'K';
  return v;
}
function fmtDate(d) {
  if (!d) return '—';
  const s = String(d);
  if (s.length >= 10) {
    const mo = parseInt(s.slice(5,7)) - 1;
    return `${parseInt(s.slice(8,10))} ${MONTHS[mo]} ${s.slice(0,4)}`;
  }
  return s;
}
function fmtPct(v) { return v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%'; }

let _pdfLibsPromise = null;
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error('Failed to load ' + src));
    document.head.appendChild(s);
  });
}
function loadPdfLibs() {
  if (!_pdfLibsPromise) {
    _pdfLibsPromise = loadScript('https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js')
      .then(() => loadScript('https://cdn.jsdelivr.net/npm/jspdf-autotable@3.8.3/dist/jspdf.plugin.autotable.min.js'));
  }
  return _pdfLibsPromise;
}
function imageToDataUrl(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth; c.height = img.naturalHeight;
      c.getContext('2d').drawImage(img, 0, 0);
      try { resolve(c.toDataURL('image/png')); } catch (e) { reject(e); }
    };
    img.onerror = () => reject(new Error('Failed to load ' + url));
    img.src = url;
  });
}
function pdfFilename() {
  const slug = (CTX.title || 'district').replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '');
  const date = new Date().toISOString().slice(0, 10);
  return `${slug}_DLD_Report_${date}.pdf`;
}

function mergeTiers(json) {
  if (!json) return null;
  if (json.sales || json.sales_premium) return Object.assign({}, json.sales || {}, json.sales_premium || {});
  if (json.rent  || json.rent_premium)  return Object.assign({}, json.rent  || {}, json.rent_premium  || {});
  return null;
}
async function ensureBothSides() {
  if (CTX.sale && CTX.rent) return;
  const path = (CTX.dataUrl || '').split('?')[0];
  if (!path) return;
  const otherPath = CTX.mode === 'sale' ? path.replace('/sales/', '/rents/') : path.replace('/rents/', '/sales/');
  if (otherPath === path) return;
  try {
    const res = await fetch(otherPath);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const merged = mergeTiers(await res.json());
    if (CTX.mode === 'sale') CTX.rent = merged; else CTX.sale = merged;
  } catch (e) {
    /* no counterpart page for this district — degrade to one-sided report */
  }
}

// Monthly {d,n,vol,med,ppsqm} series (as shipped in sale/rent timeline data) → yearly, n-weighted.
function yearlyFromMonthly(monthly) {
  if (!monthly || !monthly.length) return [];
  const byYear = new Map();
  for (const p of monthly) {
    const y = +String(p.d).slice(0, 4);
    if (!y) continue;
    let e = byYear.get(y);
    if (!e) { e = { y, n: 0, vol: 0, medSum: 0, ppsqmSum: 0 }; byYear.set(y, e); }
    e.n += p.n || 0;
    e.vol += p.vol || 0;
    e.medSum += (p.med || 0) * (p.n || 0);
    e.ppsqmSum += (p.ppsqm || 0) * (p.n || 0);
  }
  return Array.from(byYear.values()).sort((a, b) => a.y - b.y).map(e => ({
    y: e.y, n: e.n, vol: Math.round(e.vol),
    med:   e.n ? Math.round(e.medSum / e.n)   : 0,
    ppsqm: e.n ? Math.round(e.ppsqmSum / e.n) : 0,
  }));
}
function weightedAvg(arr, field, nYears) {
  if (!arr || !arr.length) return null;
  let totalN = 0, sum = 0;
  for (const e of arr.slice(-nYears)) {
    const n = e.n || 0, v = e[field];
    if (v == null || !n) continue;
    totalN += n; sum += v * n;
  }
  return totalN ? sum / totalN : null;
}
function roomKeyFor(entry) {
  if (entry.pt === 'villa') return 'villa';
  const m = { Studio: 'studio', '1BR': '1br', '2BR': '2br', '3BR': '3br', '4BR': '4br+', '5BR+': '4br+', Other: 'other' };
  return m[entry.room] || 'other';
}
function roomYieldStats(roomKey) {
  const saleYearly = yearlyFromMonthly(CTX.sale && CTX.sale.timeline_by_rooms && CTX.sale.timeline_by_rooms[roomKey]);
  const rentYearly  = yearlyFromMonthly(CTX.rent && CTX.rent.timeline_by_rooms && CTX.rent.timeline_by_rooms[roomKey]);
  let ppsqm = weightedAvg(saleYearly, 'ppsqm', 2);
  let avgPrice = weightedAvg(saleYearly, 'med', 2);
  let n = saleYearly.slice(-2).reduce((s, e) => s + e.n, 0);
  if (ppsqm == null) {
    const bu = CTX.sale && CTX.sale.by_rooms_unit && CTX.sale.by_rooms_unit[roomKey];
    if (bu) { ppsqm = bu.ppsqm || null; avgPrice = bu.med || null; n = bu.n || 0; }
  }
  let rentSqm = weightedAvg(rentYearly, 'ppsqm', 2);
  let avgRent = weightedAvg(rentYearly, 'med', 2);
  if (rentSqm == null) {
    const bu = CTX.rent && CTX.rent.by_rooms_unit && CTX.rent.by_rooms_unit[roomKey];
    if (bu) { rentSqm = bu.med_ppsqm || null; avgRent = bu.med || null; }
  }
  if (ppsqm == null && rentSqm == null) return null;
  const hasYield = !!(ppsqm && rentSqm);
  return {
    room: roomKey, ppsqm, rentSqm, avgPrice, avgRent, n,
    yieldPct: hasYield ? (rentSqm / ppsqm) * 100 : null,
  };
}
function allRoomYieldStats() {
  return YIELD_ROOMS.map(roomYieldStats).filter(Boolean);
}
function blendedYieldStats(rows) {
  const yieldRows = rows.filter(r => r.yieldPct != null);
  const totalN = yieldRows.reduce((s, r) => s + r.n, 0);
  if (!totalN) return null;
  const ppsqm = yieldRows.reduce((s, r) => s + r.ppsqm * r.n, 0) / totalN;
  const rentSqm = yieldRows.reduce((s, r) => s + r.rentSqm * r.n, 0) / totalN;
  return { ppsqm, rentSqm, yieldPct: (rentSqm / ppsqm) * 100 };
}

function latestFullYear(arr) {
  const thisYear = new Date().getFullYear();
  const full = arr.filter(e => e.y < thisYear && (e.n || 0) >= 5);
  if (full.length) return full[full.length - 1];
  return arr.slice().reverse().find(e => (e.n || 0) >= 5) || arr[arr.length - 1];
}
function priceChangePct(yearsBack) {
  const sy = yearlyFromMonthly(CTX.sale && CTX.sale.timeline);
  if (!sy.length) return null;
  const latest = latestFullYear(sy);
  if (!latest || !latest.ppsqm) return null;
  const base = sy.find(e => e.y === latest.y - yearsBack);
  if (!base || !base.ppsqm) return null;
  return ((latest.ppsqm / base.ppsqm) - 1) * 100;
}
function rentChangePct(yearsBack) {
  // ppsqm, not absolute median rent — a district's unit mix shifts between
  // years (e.g. a wave of new studios), which swings the absolute median
  // even when like-for-like AED/m² rent is flat or rising. Confirmed on
  // Business Bay: median rent -28% YoY while ppsqm was +12% YoY.
  const ry = yearlyFromMonthly(CTX.rent && CTX.rent.timeline);
  if (!ry.length) return null;
  const latest = latestFullYear(ry);
  if (!latest || !latest.ppsqm) return null;
  const base = ry.find(e => e.y === latest.y - yearsBack);
  if (!base || !base.ppsqm) return null;
  return ((latest.ppsqm / base.ppsqm) - 1) * 100;
}
function renewalRatePct() {
  const r = CTX.rent;
  if (!r) return null;
  const total = (r.new || 0) + (r.renewed || 0);
  return total ? (r.renewed / total) * 100 : null;
}
function offplanSharePct() {
  const op = CTX.sale && CTX.sale.offplan;
  if (!op) return null;
  const total = Object.values(op).reduce((a, b) => a + (b || 0), 0);
  return total ? ((op['Off-Plan'] || 0) / total) * 100 : null;
}

async function renderAnnualTrendImage(yearlyData, { countLabel, valueField, valueLabel, color }) {
  const rows = (yearlyData || []).slice(-5);
  if (!rows.length) return null;
  const canvas = document.createElement('canvas');
  canvas.width = 1400; canvas.height = 460;
  canvas.style.position = 'fixed'; canvas.style.left = '-9999px'; canvas.style.top = '0';
  document.body.appendChild(canvas);
  const chart = new Chart(canvas, {
    data: {
      labels: rows.map(e => String(e.y)),
      datasets: [
        { type: 'bar', label: countLabel, data: rows.map(e => e.n || 0), backgroundColor: color + '2e', yAxisID: 'yVol', order: 3 },
        { type: 'line', label: valueLabel, data: rows.map(e => e[valueField] || null), borderColor: color, backgroundColor: 'transparent', yAxisID: 'yPrice', borderWidth: 3, pointRadius: 5, tension: .25, order: 1 },
      ],
    },
    options: {
      responsive: false, animation: false,
      plugins: { legend: { display: true, position: 'bottom', labels: { font: { size: 15 }, boxWidth: 14 } } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 15 } } },
        yPrice: { position: 'left', ticks: { font: { size: 13 }, callback: v => fmtK(v) }, title: { display: true, text: valueLabel, font: { size: 13 } } },
        yVol: { position: 'right', grid: { drawOnChartArea: false }, ticks: { font: { size: 13 } } },
      },
    },
  });
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const dataUrl = canvas.toDataURL('image/png');
  chart.destroy();
  canvas.remove();
  return dataUrl;
}

async function buildPdfReport() {
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pageW = doc.internal.pageSize.getWidth();
  const marginX = 14;
  let y = 16;

  try {
    const logo = await imageToDataUrl('/icon-192.png');
    doc.addImage(logo, 'PNG', marginX, y - 6, 10, 10);
  } catch (e) {}
  doc.setFontSize(10); doc.setTextColor(100);
  doc.text('DXBCompass — dxbcompass.com', marginX + 13, y - 1);
  doc.setFontSize(17); doc.setTextColor(15, 23, 42);
  doc.text(`${CTX.title} — Market Analysis Report`, marginX + 13, y + 5);
  doc.setFontSize(9); doc.setTextColor(120);
  const genDate = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  doc.text(`Generated ${genDate} · Dubai, UAE`, marginX + 13, y + 10);
  y += 18;
  doc.setDrawColor(226, 232, 240);
  doc.line(marginX, y, pageW - marginX, y);
  y += 8;

  const roomRows = allRoomYieldStats();
  const headline = blendedYieldStats(roomRows);
  const noRentalHistory = !CTX.rent || !CTX.rent.n;

  let kpis;
  if (noRentalHistory) {
    const avgSalePrice = weightedAvg(yearlyFromMonthly(CTX.sale && CTX.sale.timeline), 'med', 2);
    kpis = [
      { k: 'Avg sale price', v: avgSalePrice ? fmtAEDFull(avgSalePrice) + ' AED' : '—' },
      { k: 'Off-plan share', v: (() => { const p = offplanSharePct(); return p == null ? '—' : p.toFixed(0) + '%'; })() },
      { k: 'Total transactions', v: CTX.sale ? (CTX.sale.n || 0).toLocaleString() : '—' },
      { k: '3Y price change', v: fmtPct(priceChangePct(3)) },
    ];
  } else {
    kpis = [
      { k: 'Gross rental yield', v: headline ? fmtPct(headline.yieldPct) : '—', color: [22, 163, 74] },
      { k: 'Rent growth (YoY)', v: fmtPct(rentChangePct(1)) },
      { k: 'Tenant renewal rate', v: (() => { const r = renewalRatePct(); return r == null ? '—' : r.toFixed(0) + '%'; })() },
      { k: '3Y price change', v: fmtPct(priceChangePct(3)) },
    ].filter(kpi => kpi.v !== '—');
    if (!kpis.length) kpis = [{ k: '3Y price change', v: fmtPct(priceChangePct(3)) }];
  }
  const kpiW = (pageW - marginX * 2) / kpis.length;
  kpis.forEach((kpi, i) => {
    const x = marginX + i * kpiW;
    doc.setFillColor(248, 250, 252);
    doc.setDrawColor(226, 232, 240);
    doc.roundedRect(x, y, kpiW - 4, 19, 2, 2, 'FD');
    doc.setFontSize(8); doc.setTextColor(107, 114, 128);
    doc.text(kpi.k, x + 3, y + 6);
    doc.setFontSize(12.5); doc.setTextColor(...(kpi.color || [15, 23, 42]));
    doc.text(String(kpi.v), x + 3, y + 13.5);
  });
  y += 22;
  doc.setFontSize(7.5); doc.setTextColor(148, 155, 168);
  doc.text(noRentalHistory
    ? 'Limited or no Ejari rental contracts registered yet for this district — consistent with an emerging / predominantly off-plan area. Yield metrics will appear here as units are tenanted.'
    : 'Gross yield before service charges, maintenance & financing costs. Based on DLD sales + Ejari rent registry, last 2 reported years, district-wide.', marginX, y);
  y += 8;

  const yieldRoomRows = roomRows.filter(r => !noRentalHistory || r.avgPrice != null);
  if (yieldRoomRows.length) {
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text(noRentalHistory ? 'Sale prices by unit type' : 'Yield by unit type', marginX, y);
    y += 3;
    doc.autoTable(noRentalHistory ? {
      startY: y,
      margin: { left: marginX, right: marginX },
      head: [['Unit type', 'Avg price (AED)']],
      body: yieldRoomRows.map(r => [ROOM_LABEL[r.room], r.avgPrice ? fmtAEDFull(r.avgPrice) : '—']),
      styles: { fontSize: 9, cellPadding: 2.5 },
      headStyles: { fillColor: [29, 78, 216], textColor: 255 },
      theme: 'grid',
    } : {
      startY: y,
      margin: { left: marginX, right: marginX },
      head: [['Unit type', 'Avg price (AED)', 'Avg rent (AED/yr)', 'Gross yield']],
      body: yieldRoomRows.map(r => [
        ROOM_LABEL[r.room],
        r.avgPrice ? fmtAEDFull(r.avgPrice) : '—',
        r.avgRent  ? fmtAEDFull(r.avgRent)  : '—',
        fmtPct(r.yieldPct),
      ]),
      styles: { fontSize: 9, cellPadding: 2.5 },
      headStyles: { fillColor: [29, 78, 216], textColor: 255 },
      theme: 'grid',
    });
    y = doc.lastAutoTable.finalY + 10;
  }

  const priceTrendImg = await renderAnnualTrendImage(yearlyFromMonthly(CTX.sale && CTX.sale.timeline), {
    countLabel: 'Transactions', valueField: 'ppsqm', valueLabel: 'Median AED/m²', color: '#1d4ed8',
  });
  if (priceTrendImg) {
    const imgW = pageW - marginX * 2;
    const imgH = imgW * (460 / 1400);
    if (y + imgH > 275) { doc.addPage(); y = 16; }
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text('Sale price & volume — last 5 years', marginX, y);
    y += 4;
    doc.addImage(priceTrendImg, 'PNG', marginX, y, imgW, imgH);
    y += imgH + 8;
  }
  const rentTrendImg = await renderAnnualTrendImage(yearlyFromMonthly(CTX.rent && CTX.rent.timeline), {
    countLabel: 'Contracts', valueField: 'med', valueLabel: 'Median AED/yr', color: '#16a34a',
  });
  if (rentTrendImg) {
    const imgW = pageW - marginX * 2;
    const imgH = imgW * (460 / 1400);
    if (y + imgH > 275) { doc.addPage(); y = 16; }
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text('Rent & contract volume — last 5 years', marginX, y);
    y += 4;
    doc.addImage(rentTrendImg, 'PNG', marginX, y, imgW, imgH);
    y += imgH + 8;
  }

  const recentSales = (CTX.sale && CTX.sale.recent || [])
    .filter(t => t.g === 'Sales' && (t.pt === 'flat' || t.pt === 'villa'))
    .slice(0, 10);
  if (recentSales.length) {
    if (y > 260) { doc.addPage(); y = 16; }
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text('Recent sales transactions (DLD)', marginX, y);
    y += 5;
    const benchmarkPpsqm = {};
    roomRows.forEach(r => { if (r.ppsqm) benchmarkPpsqm[r.room] = r.ppsqm; });
    const BELOW_MARKET_THRESHOLD = -15;
    const BELOW_MARKET_FLOOR = -40;
    const showType = recentSales.some(t => t.op === 'Off-Plan');
    const txRows = recentSales.map(t => {
      const sqftArea = t.area ? Math.round(t.area * SQM_TO_SQFT) : null;
      const ppsqft = t.area && t.val ? Math.round(t.val / (t.area * SQM_TO_SQFT)) : null;
      const roomKey = roomKeyFor(t);
      const benchmark = benchmarkPpsqm[roomKey];
      const diffPct = (benchmark && ppsqft) ? ((ppsqft / (benchmark / SQM_TO_SQFT)) - 1) * 100 : null;
      const bedsLabel = (t.pt === 'villa') ? (t.room || 'Villa') + ' Villa' : (t.room || '—');
      const cells = [fmtDate(t.d)];
      if (showType) cells.push(t.op === 'Off-Plan' ? 'Off-plan' : 'Ready');
      cells.push(
        bedsLabel,
        sqftArea ? sqftArea.toLocaleString() : '—',
        t.val ? fmtAEDFull(t.val) : '—',
        ppsqft ? ppsqft.toLocaleString() : '—',
      );
      return { flagged: diffPct != null && diffPct <= BELOW_MARKET_THRESHOLD && diffPct > BELOW_MARKET_FLOOR, cells };
    });
    if (txRows.some(r => r.flagged)) {
      doc.setFontSize(7.5); doc.setTextColor(22, 163, 74);
      doc.text(`Highlighted rows are priced ${Math.abs(BELOW_MARKET_THRESHOLD)}%+ below the comparable unit-type median — possible motivated seller.`, marginX, y);
      y += 5;
    }
    const salesHead = ['Date'];
    if (showType) salesHead.push('Type');
    salesHead.push('Unit', 'Area (sqft)', 'Price (AED)', 'AED/sqft');
    doc.autoTable({
      startY: y,
      margin: { left: marginX, right: marginX },
      head: [salesHead],
      body: txRows.map(r => r.cells),
      styles: { fontSize: 9, cellPadding: 2.5 },
      headStyles: { fillColor: [29, 78, 216], textColor: 255 },
      theme: 'grid',
      didParseCell: (data) => {
        if (data.section !== 'body' || !txRows[data.row.index]?.flagged) return;
        data.cell.styles.fillColor = [220, 252, 231];
      },
    });
    y = doc.lastAutoTable.finalY + 10;
  }

  const recentRents = (CTX.rent && CTX.rent.recent || [])
    .filter(t => RESIDENTIAL_RENT_SUBS.has(t.sub))
    .slice(0, 10);
  if (recentRents.length) {
    if (y > 260) { doc.addPage(); y = 16; }
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text('Recent rental contracts (Ejari)', marginX, y);
    y += 3;
    doc.autoTable({
      startY: y,
      margin: { left: marginX, right: marginX },
      head: [['Date', 'Type', 'Unit', 'Area (sqft)', 'Annual rent (AED)']],
      body: recentRents.map(t => {
        const sqftArea = t.sqm ? Math.round(t.sqm * SQM_TO_SQFT) : null;
        return [
          fmtDate(t.d),
          t.v === 'N' ? 'New' : 'Renew',
          t.sub || '—',
          sqftArea ? sqftArea.toLocaleString() : '—',
          t.val ? fmtAEDFull(t.val) : '—',
        ];
      }),
      styles: { fontSize: 9, cellPadding: 2.5 },
      headStyles: { fillColor: [22, 163, 74], textColor: 255 },
      theme: 'grid',
    });
    y = doc.lastAutoTable.finalY + 10;
  }

  const pageCount = doc.internal.getNumberOfPages();
  for (let p = 1; p <= pageCount; p++) {
    doc.setPage(p);
    const pageH = doc.internal.pageSize.getHeight();
    doc.setDrawColor(226, 232, 240);
    doc.line(marginX, pageH - 14, pageW - marginX, pageH - 14);
    doc.setFontSize(8.5); doc.setTextColor(107, 114, 128);
    doc.text('Full interactive history, charts & filters:', marginX, pageH - 9);
    doc.setTextColor(29, 78, 216);
    const url = CTX.pageUrl || location.href;
    doc.textWithLink(url.replace(/^https?:\/\//, ''), marginX, pageH - 5, { url });
    doc.setTextColor(150);
    doc.text(`Page ${p} of ${pageCount}`, pageW - marginX, pageH - 9, { align: 'right' });
  }

  doc.save(pdfFilename());
}

function wireButton() {
  const btn = document.getElementById('btn-pdf-district');
  if (!btn || btn._dpdfWired) return;
  btn._dpdfWired = true;
  btn.addEventListener('click', async () => {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Generating PDF…';
    try {
      await ensureBothSides();
      await loadPdfLibs();
      await buildPdfReport();
    } catch (err) {
      console.error('PDF export failed:', err);
      alert('Could not generate the PDF report. Please try again.');
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  });
}
function init(ctx) {
  CTX = ctx;
  wireButton();
}

window.DistrictPdf = { init };
})();
