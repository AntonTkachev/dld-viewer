(function () {
'use strict';

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
  const slug = (DATA.name || currentSlug || 'building').replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '');
  const date = new Date().toISOString().slice(0, 10);
  return `${slug}_DLD_Report_${date}.pdf`;
}

const YIELD_ROOMS = ['studio', '1br', '2br', '3br', '4br+'];
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
function roomYieldStats(roomKey) {
  const saleArr = DATA.sr[roomKey], rentArr = DATA.rr[roomKey];
  if (!saleArr?.length && !rentArr?.length) return null;
  const ppsqm   = weightedAvg(saleArr, 'ppsqm', 2);
  const rentSqm = weightedAvg(rentArr, 'rent_sqm', 2);
  const avgPrice = weightedAvg(saleArr, 'price', 2);
  const avgRent  = weightedAvg(rentArr, 'rent', 2);
  const hasYield = !!(ppsqm && rentSqm);
  const n = (saleArr || []).slice(-2).reduce((s, e) => s + (e.n || 0), 0);
  return {
    room: roomKey, ppsqm, rentSqm, avgPrice, avgRent, n,
    yieldPct:   hasYield ? (rentSqm / ppsqm) * 100 : null,
    paybackYrs: hasYield ? ppsqm / rentSqm          : null,
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
  return { ppsqm, rentSqm, yieldPct: (rentSqm / ppsqm) * 100, paybackYrs: ppsqm / rentSqm };
}

function latestFullYear(arr) {
  const thisYear = new Date().getFullYear();
  const full = arr.filter(e => e.y < thisYear && (e.n || 0) >= 5);
  if (full.length) return full[full.length - 1];
  return arr.slice().reverse().find(e => (e.n || 0) >= 5) || arr[arr.length - 1];
}
function priceChangePct(yearsBack) {
  const sy = DATA.sy || [];
  if (!sy.length) return null;
  const latest = latestFullYear(sy);
  if (!latest || !latest.ppsqm) return null;
  const base = sy.find(e => e.y === latest.y - yearsBack);
  if (!base || !base.ppsqm) return null;
  return ((latest.ppsqm / base.ppsqm) - 1) * 100;
}

function rentChangePct(yearsBack) {
  const ry = DATA.ry || [];
  if (!ry.length) return null;
  const latest = latestFullYear(ry);
  if (!latest || !latest.rent) return null;
  const base = ry.find(e => e.y === latest.y - yearsBack);
  if (!base || !base.rent) return null;
  return ((latest.rent / base.rent) - 1) * 100;
}
function renewalRatePct(rnts) {
  if (!rnts || !rnts.length) return null;
  const renewed = rnts.filter(t => !t.new).length;
  return (renewed / rnts.length) * 100;
}
function fmtPct(v) { return v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%'; }

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
  doc.text(`${DATA.name} — Market Analysis Report`, marginX + 13, y + 5);
  doc.setFontSize(9); doc.setTextColor(120);
  const genDate = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  doc.text(`Generated ${genDate} · ${[DATA.area, DATA.proj && DATA.proj !== DATA.name ? DATA.proj : ''].filter(Boolean).join(' · ')}`, marginX + 13, y + 10);
  y += 18;
  doc.setDrawColor(226, 232, 240);
  doc.line(marginX, y, pageW - marginX, y);
  y += 8;

  const txs = filteredTxs();
  const rnts = filteredRents();
  const roomRows = allRoomYieldStats();
  const headline = room !== 'all' ? roomYieldStats(room) : blendedYieldStats(roomRows);

  const noRentalHistory = !DATA.rn;
  let kpis;
  if (noRentalHistory) {
    const opCount = txs.filter(t => t.op).length;
    const opSharePct = txs.length ? (opCount / txs.length) * 100 : null;
    const avgSalePrice = weightedAvg(DATA.sy, 'price', 2);
    kpis = [
      { k: 'Avg sale price', v: avgSalePrice ? fmtAEDFull(avgSalePrice) + ' AED' : '—' },
      { k: 'Off-plan share', v: opSharePct == null ? '—' : opSharePct.toFixed(0) + '%' },
      { k: 'Transactions' + (period !== 'all' || room !== 'all' ? ' (filtered)' : ''), v: txs.length.toLocaleString() },
      { k: '3Y price change', v: fmtPct(priceChangePct(3)) },
    ];
  } else {
    kpis = [
      { k: 'Gross rental yield', v: headline ? fmtPct(headline.yieldPct) : '—', color: [22, 163, 74] },
      { k: 'Rent growth (YoY)', v: fmtPct(rentChangePct(1)) },
      { k: 'Tenant renewal rate', v: (() => { const r = renewalRatePct(rnts); return r == null ? '—' : r.toFixed(0) + '%'; })() },
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
    ? 'No Ejari rental contracts registered yet for this building — consistent with an off-plan / pre-handover project. Yield and payback will appear here once units are tenanted.'
    : 'Gross yield before service charges, maintenance & financing costs. Based on DLD sales + Ejari rent registry, last 2 reported years.', marginX, y);
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

  const priceTrendImg = await renderAnnualTrendImage(DATA.sy, {
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
  const rentTrendImg = await renderAnnualTrendImage(DATA.ry, {
    countLabel: 'Contracts', valueField: 'rent', valueLabel: 'Median AED/yr', color: '#16a34a',
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

  if (txs.length) {
    if (y > 260) { doc.addPage(); y = 16; }
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text('Recent sales transactions (DLD)', marginX, y);
    y += 5;
    const benchmarkPpsqm = {};
    roomRows.forEach(r => { if (r.ppsqm) benchmarkPpsqm[r.room] = r.ppsqm; });
    const BELOW_MARKET_THRESHOLD = -15;

    const BELOW_MARKET_FLOOR = -40;
    const salesSlice = txs.slice(0, 10);
    const showType = salesSlice.some(t => t.op);
    const txRows = salesSlice.map(t => {
      const sqftArea = t.sqm ? Math.round(t.sqm * SQM_TO_SQFT) : null;
      const ppsqft = t.sqm && t.p ? Math.round(t.p / (t.sqm * SQM_TO_SQFT)) : null;
      const benchmark = benchmarkPpsqm[t.r];
      const diffPct = (benchmark && ppsqft) ? ((ppsqft / (benchmark / SQM_TO_SQFT)) - 1) * 100 : null;
      const cells = [fmtDate(t.d)];
      if (showType) cells.push(t.op ? 'Off-plan' : 'Ready');
      cells.push(
        BEDS_LABEL[t.r] || '—',
        sqftArea ? sqftArea.toLocaleString() : '—',
        t.p ? fmtAEDFull(t.p) : '—',
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
    salesHead.push('Beds', 'Area (sqft)', 'Price (AED)', 'AED/sqft');
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

  if (rnts.length) {
    if (y > 260) { doc.addPage(); y = 16; }
    doc.setFontSize(11); doc.setTextColor(15, 23, 42);
    doc.text('Recent rental contracts (Ejari)', marginX, y);
    y += 3;
    doc.autoTable({
      startY: y,
      margin: { left: marginX, right: marginX },
      head: [['Date', 'Type', 'Beds', 'Area (sqft)', 'Annual rent (AED)']],
      body: rnts.slice(0, 10).map(t => {
        const sqftArea = t.sqm ? Math.round(t.sqm * SQM_TO_SQFT) : null;
        return [
          fmtDate(t.d),
          t.new ? 'New' : 'Renew',
          BEDS_LABEL[t.r] || '—',
          sqftArea ? sqftArea.toLocaleString() : '—',
          t.amt ? fmtAEDFull(t.amt) : '—',
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
    doc.textWithLink(`dxbcompass.com/search/#${currentSlug}`, marginX, pageH - 5,
      { url: `https://dxbcompass.com/search/#${currentSlug}` });
    doc.setTextColor(150);
    doc.text(`Page ${p} of ${pageCount}`, pageW - marginX, pageH - 9, { align: 'right' });
  }

  doc.save(pdfFilename());
}
const btnPdf = document.getElementById('btn-pdf');
if (btnPdf) btnPdf.addEventListener('click', async () => {
  if (!DATA) return;
  const original = btnPdf.textContent;
  btnPdf.disabled = true;
  btnPdf.textContent = 'Generating PDF…';
  try {
    await loadPdfLibs();
    await buildPdfReport();
  } catch (err) {
    console.error('PDF export failed:', err);
    alert('Could not generate the PDF report. Please try again.');
  } finally {
    btnPdf.disabled = false;
    btnPdf.textContent = original;
  }
});
})();
