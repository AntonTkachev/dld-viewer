// Map viewer: level switch, polygon geometry, location levels.
let minLevel = 0;

// Single entry point for entering/leaving buildings mode (level 99). Any
// code path that shows the buildings layer must go through this — it's the
// only one that also clears the district choropleth (minLevel filter),
// otherwise district polygons stay rendered underneath the building shapes.
function _switchLevel(lvl) {
  if (lvl === minLevel) return;
  const prevLevel = minLevel;
  minLevel = lvl;
  document.querySelectorAll('#mp-level-list .ls-btn').forEach(x => {
    const isActive = parseInt(x.dataset.minLevel, 10) === minLevel;
    x.classList.toggle('active', isActive);
    if (isActive) {
      const cur = document.getElementById('mp-level-current');
      if (cur) cur.innerHTML = x.innerHTML;
    }
  });
  if (lvl === 99 && !map.hasLayer(buildingLayer)) {
    buildingLayer.addTo(map);
    _ensureBuildingsData();
    if (typeof renderPoiList === 'function') renderPoiList();
  } else if (prevLevel === 99 && lvl !== 99 && map.hasLayer(buildingLayer)) {
    map.removeLayer(buildingLayer);
    if (typeof renderPoiList === 'function') renderPoiList();
    _writeLayersToUrl(_currentActiveLayerKeys());
  }
  if (typeof renderChoro === 'function') renderChoro();
}

function _bbox(geom){
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  (function walk(o){
    if (typeof o[0] === 'number' && o.length === 2){
      if(o[0]<minX)minX=o[0]; if(o[0]>maxX)maxX=o[0];
      if(o[1]<minY)minY=o[1]; if(o[1]>maxY)maxY=o[1];
      return;
    }
    for (const x of o) walk(x);
  })(geom.coordinates);
  return {area:(maxX-minX)*(maxY-minY), cx:(minX+maxX)/2, cy:(minY+maxY)/2};
}

function _segDist2(px, py, a, b) {
  let x = a[0], y = a[1], dx = b[0] - x, dy = b[1] - y;
  if (dx || dy) {
    const t = ((px - x) * dx + (py - y) * dy) / (dx * dx + dy * dy);
    if (t > 1) { x = b[0]; y = b[1]; } else if (t > 0) { x += dx * t; y += dy * t; }
  }
  dx = px - x; dy = py - y;
  return dx * dx + dy * dy;
}

// Pole of inaccessibility (Mapbox polylabel): [x, y, distance-to-edge]
function _polylabel(rings, precision) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of rings[0]) { if (x < minX) minX = x; if (y < minY) minY = y; if (x > maxX) maxX = x; if (y > maxY) maxY = y; }
  const w = maxX - minX, h = maxY - minY, size = Math.min(w, h);
  if (!size) return [minX, minY, 0];
  const dist = (x, y) => {
    let inside = false, d = Infinity;
    for (const ring of rings) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i], b = ring[j];
      if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
      d = Math.min(d, _segDist2(x, y, a, b));
    }
    return (inside ? 1 : -1) * Math.sqrt(d);
  };
  const cell = (x, y, half) => { const d = dist(x, y); return {x, y, half, d, max: d + half * Math.SQRT2}; };
  const heap = [];
  const push = c => {
    heap.push(c);
    for (let i = heap.length - 1; i > 0;) { const p = (i - 1) >> 1; if (heap[p].max >= heap[i].max) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; }
  };
  const pop = () => {
    const top = heap[0], last = heap.pop();
    if (heap.length) {
      heap[0] = last;
      for (let i = 0;;) {
        const l = 2 * i + 1, r = l + 1; let m = i;
        if (l < heap.length && heap[l].max > heap[m].max) m = l;
        if (r < heap.length && heap[r].max > heap[m].max) m = r;
        if (m === i) break;
        [heap[m], heap[i]] = [heap[i], heap[m]]; i = m;
      }
    }
    return top;
  };
  const half0 = size / 2;
  for (let x = minX; x < maxX; x += size) for (let y = minY; y < maxY; y += size) push(cell(x + half0, y + half0, half0));
  let best = cell(minX + w / 2, minY + h / 2, 0);
  while (heap.length) {
    const c = pop();
    if (c.d > best.d) best = c;
    if (c.max - best.d <= precision) continue;
    const hh = c.half / 2;
    push(cell(c.x - hh, c.y - hh, hh)); push(cell(c.x + hh, c.y - hh, hh));
    push(cell(c.x - hh, c.y + hh, hh)); push(cell(c.x + hh, c.y + hh, hh));
  }
  return [best.x, best.y, best.d];
}

// Label anchor for a district: polylabel of its largest part, cached; r = inner radius in degrees
function _labelPoint(f) {
  if (f._lp) return f._lp;
  const g = f.geometry;
  let rings = g.coordinates;
  if (g.type === 'MultiPolygon') {
    rings = g.coordinates.reduce((a, b) => _bbox({coordinates: b}).area > _bbox({coordinates: a}).area ? b : a);
  }
  const bb = _bbox({coordinates: rings[0]});
  const span = Math.max(Math.sqrt(bb.area), 1e-6);
  const [x, y, r] = _polylabel(rings, span / 100);
  return f._lp = {ll: L.latLng(y, x), r: Math.max(r, 0)};
}
function _pip(pt, ring){
  const x=pt[0], y=pt[1]; let inside=false;
  for (let i=0,j=ring.length-1; i<ring.length; j=i++){
    const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
    if ((yi>y)!=(yj>y) && x<(xj-xi)*(y-yi)/(yj-yi+1e-15)+xi) inside=!inside;
  }
  return inside;
}
function _featContains(f, pt){
  const g = f.geometry;
  if (g.type==='Polygon') return _pip(pt, g.coordinates[0]);
  if (g.type==='MultiPolygon') return g.coordinates.some(poly => _pip(pt, poly[0]));
  return false;
}
(function computeLocationLevels(){
  const N = GEOJSON.features.length;
  const bbs = GEOJSON.features.map(f => _bbox(f.geometry));
  
  const containers = Array.from({length:N}, () => []);
  for (let i=0; i<N; i++){
    const bi = bbs[i];
    for (let j=0; j<N; j++){
      if (i===j) continue;
      if (bbs[j].area <= bi.area * 1.5) continue;
      if (_featContains(GEOJSON.features[j], [bi.cx, bi.cy])) containers[i].push(j);
    }
  }
  const level = new Array(N).fill(-1);
  function compute(i, path){
    if (level[i] !== -1) return level[i];
    if (path && path.has(i)) return 0;
    if (containers[i].length === 0) { level[i] = 0; return 0; }
    const next = path ? new Set(path) : new Set();
    next.add(i);
    let mx = 0;
    for (const j of containers[i]) mx = Math.max(mx, compute(j, next));
    level[i] = 1 + mx;
    return level[i];
  }
  const counts = [0,0,0,0,0,0];
  for (let i=0; i<N; i++){
    compute(i);
    GEOJSON.features[i]._level    = level[i];
    GEOJSON.features[i]._bboxArea = bbs[i].area;
    if (level[i] < counts.length) counts[level[i]]++;
  }
  
  GEOJSON.features.sort((a, b) => b._bboxArea - a._bboxArea);
  console.log('location levels:', counts.map((c,i)=>`L${i}=${c}`).join(' '));
})();

(function tagProjectsToDistricts() {
  if (typeof PROJECTS === 'undefined') return;

  for (const p of PROJECTS) {
    if (!Number.isFinite(p.lat) || !Number.isFinite(p.lon)) continue;
    const count = p.in_flight || 0;
    if (!count) continue;
    for (let i = GEOJSON.features.length - 1; i >= 0; i--) {
      const f = GEOJSON.features[i];
      if (_featContains(f, [p.lon, p.lat])) {
        f.properties._new_dev_count = (f.properties._new_dev_count || 0) + count;
        break;
      }
    }
  }
})();
