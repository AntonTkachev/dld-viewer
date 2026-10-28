// Map viewer: POI layers (metro, schools, medical, mosques, projects, malls) and the layer picker.
const metroLayer = L.layerGroup();

if (typeof TRAM_LINE !== 'undefined') METRO_LINES.features.push(TRAM_LINE);
if (typeof ETIHAD_LINE !== 'undefined') METRO_LINES.features.push(ETIHAD_LINE);
if (typeof GOLD_LINE !== 'undefined') METRO_LINES.features.push(GOLD_LINE);
for (const f of METRO_LINES.features) {
  L.geoJSON(f, {style: {color: f.properties.color, weight: 4, opacity: 0.9, dashArray: f.properties.status==='construction' ? '8,6' : null}}).addTo(metroLayer);
}
function getGroupLabel(g) { return ({red:t('metro_line_red'), green:t('metro_line_green'), blue:t('metro_line_blue'), tram:t('metro_line_tram'), gold:t('metro_line_gold'), etihad:'Etihad Rail'})[g] || g; }
const GROUP_PIN = {red:'metro-red', green:'metro-green', blue:'metro-blue', tram:'metro-tram', gold:'metro-gold', etihad:'metro-etihad'};
if (typeof TRAM_STATIONS !== 'undefined') {
  for (const s of TRAM_STATIONS) METRO_STATIONS.push(s);
}
if (typeof ETIHAD_STATIONS !== 'undefined') {
  for (const s of ETIHAD_STATIONS) METRO_STATIONS.push(s);
}
if (typeof GOLD_STATIONS !== 'undefined') {
  for (const s of GOLD_STATIONS) METRO_STATIONS.push(s);
}
// Gold Line shares physical stations with Red/Green/Etihad at 4 interchange
// points (Al Ghubaiba, BurJuman, Business Bay, JGE). To avoid duplicate pins
// stacked on the same coords, we DON'T add those four to GOLD_STATIONS.
// Instead, we patch the existing METRO_STATIONS entry — adding 'gold' to its
// groups field — so its popup correctly lists both lines and renders as
// interchange.
if (typeof GOLD_INTERCHANGES !== 'undefined') {
  for (const name of GOLD_INTERCHANGES) {
    const s = METRO_STATIONS.find(x => x.name === name);
    if (!s) continue;
    const cur = s.groups || [s.group];
    if (!cur.includes('gold')) s.groups = cur.concat('gold');
  }
}
for (const s of METRO_STATIONS) {
  const groups = s.groups || [s.group];
  const labelLines = groups.map(g => getGroupLabel(g)).join(' / ');
  const isInterchange = groups.length > 1;
  
  const primary = groups[0];
  const pinLetter = (primary === 'tram') ? 'T' : (primary === 'etihad') ? 'E' : 'M';
  const icon = L.divIcon({className:'', html:`<div class="pin ${GROUP_PIN[primary]}">${pinLetter}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => `
    <h3>🚇 ${_h(s.name || t('station_default'))} <span class="src-tag src-osm">OSM</span></h3>
    <div class="muted" style="color:#888;margin-bottom:4px">${_h(labelLines)}${isInterchange?(' · '+t('metro_interchange')):''}</div>
    ${s.line ? `<div class="stat"><span class="k">${t("metro_line")}</span><span class="v">${_h(s.line)}</span></div>` : ''}
  `);
  m.addTo(metroLayer);
}

const schoolLayer = L.layerGroup();
const _rcls = v => (v || '').replace(/\s+/g, '');
for (const s of SCHOOLS) {
  const icon = L.divIcon({className:'', html:`<div class="pin school">🏫</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([s.lat, s.lon], {icon});
  m.bindPopup(() => {
    const hasName = s.name && s.name !== '(unnamed school)';

    const nameIsArabic = hasName && /[؀-ۿ]/.test(s.name);
    const titleAttr = nameIsArabic ? ' dir="rtl" style="text-align:right"' : '';
    const displayName = hasName
      ? `<span${titleAttr}>${_h(s.name)}</span>`
      : ('<span style="color:#888">' + _h(t('no_name')) + '</span>');
    const arSubtitle = (s.name_ar && s.name_ar !== s.name)
      ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${_h(s.name_ar)}</div>`
      : '';
    if (!s.in_khda) {
      const osmRows = [];
      if (s.operator)       osmRows.push(`<div class="stat"><span class="k">${t('h_op')}</span><span class="v">${_h(s.operator)}</span></div>`);
      if (s.school_type)    osmRows.push(`<div class="stat"><span class="k">${t('sch_curr')}</span><span class="v">${_h(s.school_type)}</span></div>`);
      if (s.school_gender)  osmRows.push(`<div class="stat"><span class="k">${t('sch_gender')}</span><span class="v">${_h(s.school_gender)}</span></div>`);
      if (s.addr_suburb)    osmRows.push(`<div class="stat"><span class="k">${t('sch_area')}</span><span class="v">${_h(s.addr_suburb)}</span></div>`);
      if (s.website)        osmRows.push(`<div class="stat"><span class="k">${t('h_web')}</span><span class="v"><a href="${_h(_safeUrl(s.website))}" target="_blank" rel="noopener noreferrer">${_h(s.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32))}</a></span></div>`);
      if (s.wikidata)       osmRows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${encodeURIComponent(s.wikidata)}" target="_blank" rel="noopener noreferrer">${_h(s.wikidata)}</a></span></div>`);
      return `
        <h3>🏫 ${displayName} <span class="src-tag src-osm">OSM</span></h3>
        ${arSubtitle}
        ${osmRows.join('')}
        <div class="muted" style="font-size:11px;color:#888;margin-top:6px">${t('sch_not_in_khda')}</div>
      `;
    }
    const srcTag = '<span class="src-tag" style="background:#e6f7e6;color:#0a7f00">KHDA</span>';
    const manualTag = s.manual_coords
      ? ' <span class="src-tag" style="background:#fff5e0;color:#b35900" title="Coordinates set manually — school missing from OSM">~coords</span>'
      : '';
    const rows = [];
    if (s.curriculum)  rows.push(`<div class="stat"><span class="k">${t('sch_curr')}</span><span class="v">${_h(s.curriculum)}</span></div>`);
    if (s.grade_range) rows.push(`<div class="stat"><span class="k">${t('sch_grade_range')}</span><span class="v">${_h(s.grade_range)}</span></div>`);
    if (s.area)        rows.push(`<div class="stat"><span class="k">${t('sch_area')}</span><span class="v">${_h(s.area)}</span></div>`);
    if (s.phone)       rows.push(`<div class="stat"><span class="k">${t('sch_phone')}</span><span class="v"><a href="tel:${encodeURIComponent(s.phone)}">${_h(s.phone)}</a></span></div>`);
    if (s.rating)      rows.push(`<div class="stat"><span class="k">${t('sch_rating')}</span><span class="v"><span class="rating ${_h(_rcls(s.rating))}">${_h(s.rating)}</span></span></div>`);
    if (s.wellbeing)   rows.push(`<div class="stat"><span class="k">${t('sch_wellbeing')}</span><span class="v"><span class="rating ${_h(_rcls(s.wellbeing))}">${_h(s.wellbeing)}</span></span></div>`);
    if (s.inclusion)   rows.push(`<div class="stat"><span class="k">${t('sch_inclusion')}</span><span class="v"><span class="rating ${_h(_rcls(s.inclusion))}">${_h(s.inclusion)}</span></span></div>`);
    const detailsUrl = `https://web.khda.gov.ae/en/Education-Directory/Schools/School-Details?Id=${encodeURIComponent(s.khda_id)}&CenterID=${encodeURIComponent(s.center_id)}`;
    return `
      <h3>🏫 ${displayName} ${srcTag}${manualTag}</h3>
      ${arSubtitle}
      ${rows.join('')}
      <div style="margin-top:6px"><a href="${detailsUrl}" target="_blank" rel="noopener noreferrer" style="font-size:11px">KHDA School Details ↗</a></div>
    `;
  });
  m.addTo(schoolLayer);
}

const uniLayer = L.layerGroup();
for (const u of UNIVERSITIES) {
  const icon = L.divIcon({className:'', html:`<div class="pin university">🎓</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([u.lat, u.lon], {icon});
  m.bindPopup(() => {
    const hasName = u.name && u.name !== '(unnamed)';
    const isAr = hasName && /[؀-ۿ]/.test(u.name);
    const titleAttr = isAr ? ' dir="rtl" style="text-align:right"' : '';
    const displayName = hasName ? `<span${titleAttr}>${_h(u.name)}</span>` : `<span style="color:#888">${t('no_name')}</span>`;
    const arSub = (u.name_ar && u.name_ar !== u.name)
      ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${_h(u.name_ar)}</div>`
      : '';
    const srcTag = u.in_khda
      ? '<span class="src-tag" style="background:#e6f7e6;color:#0a7f00">KHDA</span>'
      : '<span class="src-tag src-osm">OSM</span>';
    const rows = [];
    if (u.in_khda) {
      if (u.khda_area)        rows.push(`<div class="stat"><span class="k">${t('uni_city')}</span><span class="v">${_h(u.khda_area)}</span></div>`);
      if (u.khda_established) rows.push(`<div class="stat"><span class="k">${t('uni_established')}</span><span class="v">${_h(u.khda_established)}</span></div>`);
      if (u.khda_stars)       rows.push(`<div class="stat"><span class="k">${t('uni_khda_stars')}</span><span class="v"><span class="rating Verygood">${'★'.repeat(parseInt(u.khda_stars,10)||0)}${'☆'.repeat(5-(parseInt(u.khda_stars,10)||0))}</span> ${u.khda_rating_year ? `<span style="color:#888;font-size:11px">${_h(u.khda_rating_year)}</span>` : ''}</span></div>`);
    }
    if (u.operator)      rows.push(`<div class="stat"><span class="k">${t('uni_op')}</span><span class="v">${_h(u.operator)}</span></div>`);
    if (u.website)       rows.push(`<div class="stat"><span class="k">${t('uni_web')}</span><span class="v"><a href="${_h(_safeUrl(u.website))}" target="_blank" rel="noopener noreferrer">${_h(u.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32))}</a></span></div>`);
    if (u.wikipedia) {
      const wpUrl = 'https://' + u.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${_h(_safeUrl(wpUrl))}" target="_blank" rel="noopener noreferrer">${_h(u.wikipedia)}</a></span></div>`);
    }
    if (u.wikidata && !u.wikipedia) rows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${encodeURIComponent(u.wikidata)}" target="_blank" rel="noopener noreferrer">${_h(u.wikidata)}</a></span></div>`);
    const detailsLink = u.khda_uni_id
      ? `<div style="margin-top:6px"><a href="https://web.khda.gov.ae/en/Education-Directory/Higher-Education/Higher-Education-Details?CenterID=${encodeURIComponent(u.khda_uni_id)}" target="_blank" rel="noopener noreferrer" style="font-size:11px">KHDA Details ↗</a></div>`
      : '';
    const notInKhdaNote = (!u.in_khda)
      ? `<div class="muted" style="font-size:11px;color:#888;margin-top:6px">${t('uni_not_in_khda')}</div>`
      : '';
    const khdaOnlyNote = (u.source === 'khda')
      ? `<div class="muted" style="font-size:11px;color:#888;margin-top:4px">${t('uni_khda_only_geocoded')}</div>`
      : '';
    return `
      <h3>🎓 ${displayName} ${srcTag}</h3>
      ${arSub}
      ${rows.join('')}
      ${khdaOnlyNote}
      ${notInKhdaNote}
      ${detailsLink}
    `;
  });
  m.addTo(uniLayer);
}

const medicalLayer = L.layerGroup();
const MEDICAL_META = {
  hospital: {emoji: '🏥', pin: 'hospital', size: 24},
  clinic:   {emoji: '🩺', pin: 'clinic',   size: 20},
  doctors:  {emoji: '👨‍⚕️', pin: 'clinic',  size: 20},
};
for (const m of MEDICAL) {
  const meta = MEDICAL_META[m.kind] || MEDICAL_META.clinic;
  const icon = L.divIcon({
    className: '',
    html: `<div class="pin ${meta.pin}">${meta.emoji}</div>`,
    iconSize: [meta.size, meta.size],
    iconAnchor: [meta.size / 2, meta.size / 2],
  });
  const mk = L.marker([m.lat, m.lon], {icon});
  mk.bindPopup(() => {
    const rows = [];
    rows.push(`<div class="stat"><span class="k">${t('med_kind')}</span><span class="v">${t('med_kind_' + m.kind)}</span></div>`);
    if (m.emergency) {
      const yes = m.emergency === 'yes';
      rows.push(`<div class="stat"><span class="k">${t('h_emerg')}</span><span class="v" style="color:${yes ? '#0a7f00' : '#666'}">${yes ? t('yes_t') : t('no_t')}</span></div>`);
    }
    if (m.healthcare_speciality) {
      const specs = String(m.healthcare_speciality).split(';').map(s => s.trim()).filter(Boolean);
      rows.push(`<div class="stat"><span class="k">${t('h_specs_real')}</span><span class="v" style="text-align:right;max-width:200px;white-space:normal;font-size:11px">${specs.map(s => `<span class="lang-chip">${_h(s)}</span>`).join('')}</span></div>`);
    }
    if (m.operator) rows.push(`<div class="stat"><span class="k">${t('h_op')}</span><span class="v">${_h(m.operator)}</span></div>`);
    if (m.phone)    rows.push(`<div class="stat"><span class="k">${t('h_phone')}</span><span class="v"><a href="tel:${encodeURIComponent(m.phone)}">${_h(m.phone)}</a></span></div>`);
    if (m.website)  rows.push(`<div class="stat"><span class="k">${t('h_web')}</span><span class="v"><a href="${_h(_safeUrl(m.website))}" target="_blank" rel="noopener noreferrer">${_h(m.website.replace(/^https?:\/\//, '').replace(/\/$/, '').slice(0, 32))}</a></span></div>`);
    if (m.wikipedia) {
      const wpUrl = 'https://' + m.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g, '_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${_h(_safeUrl(wpUrl))}" target="_blank" rel="noopener noreferrer">${_h(m.wikipedia)}</a></span></div>`);
    }
    if (m.opening_hours) rows.push(`<div class="stat"><span class="k">${t('ml_hours')}</span><span class="v" style="font-size:11.5px">${_h(m.opening_hours)}</span></div>`);
    if (m.addr_city)     rows.push(`<div class="stat"><span class="k">${t('h_city')}</span><span class="v">${_h(m.addr_city)}</span></div>`);
    return `
      <h3>${meta.emoji} ${m.name ? _h(m.name) : ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>
      ${m.name_ar ? `<div class="muted" dir="rtl" style="color:#888;margin-bottom:4px;text-align:right">${_h(m.name_ar)}</div>` : ''}
      ${rows.join('')}
    `;
  });
  mk.addTo(medicalLayer);
}

const mosqueLayer = L.layerGroup();
for (const mo of MOSQUES) {
  const icon = L.divIcon({className:'', html:`<div class="pin mosque">🕌</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([mo.lat, mo.lon], {icon});
  m.bindPopup(() => {
  const realRows = [];
  
  if (mo.denomination && String(mo.denomination).toLowerCase() !== 'sunni') {
    realRows.push(`<div class="stat"><span class="k">${t("mo_denom")}</span><span class="v">${_h(mo.denomination)}</span></div>`);
  }
  if (mo.addr_street) realRows.push(`<div class="stat"><span class="k">${t("mo_street")}</span><span class="v">${_h(mo.addr_street)}</span></div>`);
  if (mo.addr_city) realRows.push(`<div class="stat"><span class="k">${t("mo_city")}</span><span class="v">${_h(mo.addr_city)}</span></div>`);
  if (mo.wheelchair) realRows.push(`<div class="stat"><span class="k">${t("mo_wheel")}</span><span class="v">${mo.wheelchair==='yes'?t('yes_t'):_h(mo.wheelchair)}</span></div>`);
  if (mo.image) realRows.push(`<div class="stat"><span class="k">${t("mo_image")}</span><span class="v"><a href="${_h(_safeUrl(mo.image))}" target="_blank" rel="noopener noreferrer">${t("view_t")}</a></span></div>`);

  const synth = `
    <div class="stat"><span class="k">${t("mo_cap")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.capacity.toLocaleString('ru-RU')}</span></div>
    <div class="stat"><span class="k">${t("mo_khutbah")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.khutbah_langs.map(l=>`<span class="lang-chip">${_h(l)}</span>`).join('')}</span></div>
    <div class="stat"><span class="k">${t("mo_women")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.women_section?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_park")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.parking?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_classes")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.classes?t('yes_t'):t('no_t')}</span></div>
    <div class="stat"><span class="k">${t("mo_iftar")} <span class="src-tag src-fake">~</span></span><span class="v">${mo.iftar?t('yes_t'):t('no_t')}</span></div>
  `;
  return `
    <h3>🕌 ${mo.name ? _h(mo.name) : ('<span style="color:#888">' + t('no_name') + '</span>')} <span class="src-tag src-osm">OSM</span></h3>
    ${mo.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px">${_h(mo.name_ar)}</div>` : ''}
    ${realRows.join('')}
    <div style="border-top:1px solid #eee;margin:6px 0 4px"></div>
    ${synth}
    <div class="muted" style="margin-top:6px;font-size:11px;color:#a30808">${t("mo_warn")}</div>
  `;
});
  m.addTo(mosqueLayer);
}

const projectLayer = L.layerGroup();
const STATUS_META = {
  ACTIVE:                 {color: '#3aaf2f', key: 'pj_status_active'},
  NOT_STARTED:            {color: '#94a3b8', key: 'pj_status_not_started'},
  PENDING:                {color: '#f0a020', key: 'pj_status_pending'},
  CONDITIONAL_ACTIVATING: {color: '#7a4c00', key: 'pj_status_cond_activating'},
  FINISHED:               {color: '#1d4ed8', key: 'pj_status_finished'},
  CANCELLED:              {color: '#cc4040', key: 'pj_status_cancelled'},
  FRIEZED:                {color: '#7a4c00', key: 'pj_status_frozen'},
};
for (const d of PROJECTS) {
  
  const n = d.in_flight;
  const size = n >= 100 ? 44 : n >= 30 ? 38 : 32;
  const icon = L.divIcon({
    className: '',
    html: `<div class="pin construction-cluster" style="width:${size}px;height:${size}px"><span class="pin-count">${n}</span><span class="pin-emoji">🏗️</span></div>`,
    iconSize: [size, size], iconAnchor: [size/2, size/2],
  });
  const m = L.marker([d.lat, d.lon], {icon});
  m.bindPopup(() => {
    const rows = [];

    const order = ['ACTIVE','NOT_STARTED','PENDING','CONDITIONAL_ACTIVATING','FINISHED','CANCELLED','FRIEZED'];
    const chips = [];
    if (d.overdue) {
      chips.push(`<span class="pj-status-chip" style="background:#fee2e21f;color:#991b1b">${t('pj_status_overdue') || 'Overdue'} · ${d.overdue}</span>`);
    }
    for (const s of order) {
      const v = d.by_status[s] || 0;
      if (!v) continue;
      const meta = STATUS_META[s] || {color:'#888', key:'pj_status'};
      chips.push(`<span class="pj-status-chip" style="background:${meta.color}1a;color:${meta.color}">${t(meta.key)} · ${v}</span>`);
    }
    rows.push(`<div class="stat"><span class="k">${t('pj_count_by_status')}</span><span class="v" style="text-align:right;max-width:220px;display:flex;flex-wrap:wrap;gap:3px;justify-content:flex-end">${chips.join('')}</span></div>`);

    if (Number.isFinite(d.avg_percent)) {
      rows.push(`<div class="stat"><span class="k">${t('pj_avg_percent')}</span><span class="v" style="color:#3aaf2f">${d.avg_percent}%</span></div>`);
    }

    const comp = [];
    if (d.total_units > 0)     comp.push(`${d.total_units.toLocaleString('ru-RU')} ${t('pj_units_n')}`);
    if (d.total_villas > 0)    comp.push(`${d.total_villas.toLocaleString('ru-RU')} ${t('pj_villas_n')}`);
    if (d.total_buildings > 0) comp.push(`${d.total_buildings.toLocaleString('ru-RU')} ${t('pj_buildings_n')}`);
    if (d.total_lands > 0)     comp.push(`${d.total_lands.toLocaleString('ru-RU')} ${t('pj_lands_n')}`);
    if (comp.length) {
      rows.push(`<div class="stat"><span class="k">${t('pj_composition_total')}</span><span class="v" style="text-align:right;max-width:200px;font-size:11.5px">${comp.join(', ')}</span></div>`);
    }

    if (d.top_developers && d.top_developers.length) {
      const devLines = d.top_developers.slice(0, 5).map(([name, count]) =>
        `<div style="display:flex;justify-content:space-between;gap:8px;font-size:11.5px"><span dir="rtl" style="flex:1;text-align:right">${_h(name)}</span><span style="color:#888">${count|0}</span></div>`
      ).join('');
      rows.push(`<div class="stat"><span class="k">${t('pj_top_devs')}</span><span class="v" style="text-align:right;max-width:220px">${devLines}</span></div>`);
    }

    const geoNote = d.geocode_kind === 'area'
      ? `<div class="muted" style="margin-top:6px;font-size:11px;color:#888">${t('pj_geocode_area')}</div>`
      : '';

    const constructionHref = (typeof _langUrlPrefix === 'function' ? _langUrlPrefix() : '')
      + '/construction/?q=' + encodeURIComponent(d.name);
    const openAll = `<div style="margin-top:8px"><a class="pj-open-all" href="${constructionHref}">${t('pj_open_all')} (${d.total|0}) →</a></div>`;

    return `
      <h3>🏗️ ${_h(d.name)} <span class="src-tag" style="background:#e6f7e6;color:#0a7f00">RERA</span></h3>
      <div class="muted" style="color:#888;margin-bottom:4px;font-size:11.5px">${d.in_flight|0} ${t('pj_in_flight_label')} / ${d.total|0} ${t('pj_total_label')}</div>
      ${rows.join('')}
      ${geoNote}
      ${openAll}
    `;
  });
  m.addTo(projectLayer);
}

const mallLayer = L.layerGroup();
for (const ml of MALLS) {
  const emoji = ml.kind === 'souq' ? '🏛️' : '🛍️';
  const cls   = ml.kind === 'souq' ? 'pin mall souq' : 'pin mall';
  const icon = L.divIcon({className:'', html:`<div class="${cls}">${emoji}</div>`, iconSize:[24,24], iconAnchor:[12,12]});
  const m = L.marker([ml.lat, ml.lon], {icon});
  m.bindPopup(() => {
    const rows = [];
    const kindLabel = t(ml.kind === 'souq' ? 'ml_kind_souq' : 'ml_kind_mall');
    rows.push(`<div class="stat"><span class="k">${t('ml_kind')}</span><span class="v">${kindLabel}</span></div>`);
    if (ml.opening_hours) rows.push(`<div class="stat"><span class="k">${t('ml_hours')}</span><span class="v" style="font-size:11.5px">${_h(ml.opening_hours)}</span></div>`);
    if (ml.operator) rows.push(`<div class="stat"><span class="k">${t('ml_op')}</span><span class="v">${_h(ml.operator)}</span></div>`);
    if (ml.brand) rows.push(`<div class="stat"><span class="k">${t('ml_brand')}</span><span class="v">${_h(ml.brand)}</span></div>`);
    if (ml.phone) rows.push(`<div class="stat"><span class="k">${t('ml_phone')}</span><span class="v"><a href="tel:${encodeURIComponent(ml.phone)}">${_h(ml.phone)}</a></span></div>`);
    if (ml.website) rows.push(`<div class="stat"><span class="k">${t('ml_web')}</span><span class="v"><a href="${_h(_safeUrl(ml.website))}" target="_blank" rel="noopener noreferrer">${_h(ml.website.replace(/^https?:\/\//,'').replace(/\/$/,'').slice(0,32))}</a></span></div>`);
    if (ml.wikipedia) {
      const wpUrl = 'https://' + ml.wikipedia.replace(':', '.wikipedia.org/wiki/').replace(/ /g,'_');
      rows.push(`<div class="stat"><span class="k">Wikipedia</span><span class="v"><a href="${_h(_safeUrl(wpUrl))}" target="_blank" rel="noopener noreferrer">${_h(ml.wikipedia)}</a></span></div>`);
    } else if (ml.wikidata) {
      rows.push(`<div class="stat"><span class="k">Wikidata</span><span class="v"><a href="https://www.wikidata.org/wiki/${encodeURIComponent(ml.wikidata)}" target="_blank" rel="noopener noreferrer">${_h(ml.wikidata)}</a></span></div>`);
    }
    if (ml.building_levels) rows.push(`<div class="stat"><span class="k">${t('ml_levels')}</span><span class="v">${_h(ml.building_levels)}</span></div>`);
    const addr = [ml.addr_street, ml.addr_suburb, ml.addr_city].filter(Boolean).join(', ');
    if (addr) rows.push(`<div class="stat"><span class="k">${t('ml_addr')}</span><span class="v" style="font-size:11.5px;max-width:200px;text-align:right">${_h(addr)}</span></div>`);
    if (ml.wheelchair === 'yes') rows.push(`<div class="stat"><span class="k">${t('ml_access')}</span><span class="v" style="color:#0a7f00">✓ wheelchair</span></div>`);
    if (ml.internet_access === 'yes' || ml.internet_access === 'wlan') rows.push(`<div class="stat"><span class="k">${t('ml_wifi')}</span><span class="v" style="color:#0a7f00">✓</span></div>`);
    if (ml.description) rows.push(`<div class="muted" style="margin-top:6px;font-size:11px;color:#555">${_h(ml.description)}</div>`);
    const srcTag = ml.manual
      ? '<span class="src-tag" style="background:#fff5e0;color:#b35900" title="Hand-added; tagged building=retail / landuse=retail in OSM, not shop=mall">~coords</span>'
      : '<span class="src-tag src-osm">OSM</span>';
    return `
      <h3>${emoji} ${ml.name ? _h(ml.name) : '—'} ${srcTag}</h3>
      ${ml.name_ar ? `<div class="muted" style="color:#888;margin-bottom:4px" dir="rtl">${_h(ml.name_ar)}</div>` : ''}
      ${rows.join('')}
    `;
  });
  m.addTo(mallLayer);
}

function poiBuiltinDefs() {
  return [
    {key:'metro',     label:t('metro_all'),     count:METRO_STATIONS.length, layer:metroLayer},
    {key:'schools',   label:t('schools'),       count:SCHOOLS.length,        layer:schoolLayer},
    {key:'unis',      label:t('universities'),  count:UNIVERSITIES.length,   layer:uniLayer},
    {key:'medical',   label:t('medical'),       count:MEDICAL.length,        layer:medicalLayer},
    {key:'mosques',   label:t('mosques'),       count:MOSQUES.length,        layer:mosqueLayer},
    {key:'proj',      label:t('construction'),  count:PROJECTS.length,       layer:projectLayer},
    {key:'malls',     label:t('malls'),         count:MALLS.length,          layer:mallLayer},
    {key:'buildings', label:t('buildings'),     count:(typeof BUILDINGS!=='undefined'?BUILDINGS.length:null), layer:buildingLayer},
  ];
}

let _POI_DEFS = [];
function _readLayersFromUrl() {
  try {
    const raw = new URLSearchParams(window.location.search).get('layers') || '';
    return new Set(raw.split(',').map(s => s.trim()).filter(Boolean));
  } catch (e) { return new Set(); }
}
function _writeLayersToUrl(activeKeys) {
  if (typeof window === 'undefined' || window.location.protocol === 'file:') return;
  try {
    const url = new URL(window.location.href);
    if (activeKeys && activeKeys.size) {
      url.searchParams.set('layers', Array.from(activeKeys).join(','));
    } else {
      url.searchParams.delete('layers');
    }
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  } catch (e) {  }
}
function _applyLayersFromUrl() {
  const want = _readLayersFromUrl();
  _POI_DEFS.forEach(d => {
    const should = want.has(d.key) || (d.key === 'buildings' && minLevel === 99);
    const has = map.hasLayer(d.layer);
    if (should && !has) d.layer.addTo(map);
    if (!should && has) map.removeLayer(d.layer);
    if (should && d.key === 'buildings') _ensureBuildingsData();
  });
  
  const el = document.getElementById('mp-poi-list');
  if (el) el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    const def = _POI_DEFS[i];
    if (inp && def) inp.checked = map.hasLayer(def.layer);
  });
}
function _currentActiveLayerKeys() {
  const out = new Set();
  _POI_DEFS.forEach(d => { if (map.hasLayer(d.layer) && !(d.key === 'buildings' && minLevel === 99)) out.add(d.key); });
  return out;
}

function renderPoiList() {
  const el = document.getElementById('mp-poi-list');
  if (!el) return;
  _POI_DEFS = poiBuiltinDefs();
  el.innerHTML = _POI_DEFS.map((d,i) => {
    const checked = map.hasLayer(d.layer) ? 'checked' : '';
    return `<label data-i="${i}"><input type="checkbox" ${checked}><span class="poi-label">${d.label}</span><span class="poi-count">${d.count ?? ''}</span></label>`;
  }).join('');
  el.querySelectorAll('label').forEach((lab, i) => {
    const inp = lab.querySelector('input');
    inp.addEventListener('change', () => {
      const d = _POI_DEFS[i];
      if (!inp.checked && d.key === 'buildings' && minLevel === 99) { _switchLevel(0); return; }
      if (inp.checked) d.layer.addTo(map);
      else map.removeLayer(d.layer);
      if (inp.checked && d.key === 'buildings') _ensureBuildingsData();
      _writeLayersToUrl(_currentActiveLayerKeys());
    });
  });
}
