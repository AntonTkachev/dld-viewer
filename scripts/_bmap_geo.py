"""Geometry helpers for the building matcher: point-in-polygon, bbox area, area polygons/centroids."""
import collections
import json
import math
from pathlib import Path

GEOJSON = Path(__file__).resolve().parent.parent / 'data' / 'curated_polygons.geojson'

# Geo-sanity: matches more than this far from the DLD area's centroid get
# rejected — catches cases like `Muraba Residences Palm Jumeirah` fuzzy-
# matching to `Mr. C Residences Jumeirah` (different building, different
# coast). 5 km comfortably covers even the biggest DLD areas. Only used as
# a fallback when geo_ok() has no real polygon for the area.
GEO_SANITY_KM = 5.0


def bbox_area_m2(rings: list) -> float:
    """Bounding-box area in m² for a list of rings [[lat,lon],...]."""
    lats = [p[0] for ring in rings for p in ring]
    lons = [p[1] for ring in rings for p in ring]
    if not lats:
        return 0.0
    mid = sum(lats) / len(lats)
    dlat = (max(lats) - min(lats)) * 111_000
    dlon = (max(lons) - min(lons)) * 111_000 * math.cos(math.radians(mid))
    return dlat * dlon


def synthetic_square_ring(lat: float, lon: float, half_m: float = 16.5) -> list:
    """~33x33m square ring centered on a geocoded point — stand-in for a
    missing OSM footprint."""
    d_lat = half_m / 111_320
    d_lon = half_m / (111_320 * math.cos(math.radians(lat)))
    return [[
        [lat - d_lat, lon - d_lon],
        [lat - d_lat, lon + d_lon],
        [lat + d_lat, lon + d_lon],
        [lat + d_lat, lon - d_lon],
    ]]


def pip(lat: float, lon: float, ring: list) -> bool:
    """Ray-casting point-in-polygon. ring = [[lat, lon], ...]"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def find_osm_footprint(osm_footprints: list, lat: float, lon: float):
    """Return the smallest OSM building polygon that contains (lat, lon), or None."""
    candidates = []
    for b in osm_footprints:
        rings = b.get('rings')
        if not rings:
            continue
        outer = rings[0]
        lats = [p[0] for p in outer]
        lons = [p[1] for p in outer]
        if not (min(lats) <= lat <= max(lats) and min(lons) <= lon <= max(lons)):
            continue
        if pip(lat, lon, outer):
            candidates.append(b)
    if not candidates:
        return None
    return min(candidates, key=lambda b: bbox_area_m2(b['rings']))


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def load_area_polygons() -> dict:
    """DLD area_name_en -> list of rings [[(lat,lon),...],...], same
    parent/alias grouping as load_area_centroids but keeping real geometry
    for point-in-polygon geo-sanity instead of a flat-radius check."""
    if not GEOJSON.exists():
        return {}
    rings_per_area = collections.defaultdict(list)
    dld_aliases = {}
    with GEOJSON.open(encoding='utf-8') as f:
        gj = json.load(f)
    for feat in gj.get('features', []):
        props = feat.get('properties', {})
        sub_name = props.get('name') or ''
        parent = props.get('parent_area_name_en') or ''
        area = parent or sub_name or props.get('NAME_EN') or ''
        if not area:
            continue
        filt = props.get('filter') or {}
        if filt.get('area_name_en'):
            dld_aliases[filt['area_name_en']] = area
        geom = feat.get('geometry') or {}
        polys = []
        if geom.get('type') == 'Polygon':
            polys = [geom['coordinates']]
        elif geom.get('type') == 'MultiPolygon':
            polys = geom['coordinates']
        for poly in polys:
            ring = [(p[1], p[0]) for p in poly[0]]
            rings_per_area[area].append(ring)
            if parent and sub_name:
                rings_per_area[sub_name].append(ring)
    out = dict(rings_per_area)
    for dld_name, display_name in dld_aliases.items():
        if dld_name not in out and display_name in out:
            out[dld_name] = out[display_name]
    return out


def geo_ok(area_polys: dict, centroids: dict, area: str, lat: float, lon: float,
           radius_km: float = GEO_SANITY_KM) -> bool:
    """Real point-in-polygon against the DLD area's curated community
    polygon(s); falls back to flat-radius-from-centroid only when we have
    no polygon coverage for that area at all."""
    rings = area_polys.get(area)
    if rings:
        return any(pip(lat, lon, ring) for ring in rings)
    c = centroids.get(area)
    if not c:
        return True
    return haversine_km(c[0], c[1], lat, lon) <= radius_km


def load_area_centroids() -> dict:
    """DLD area_name_en → (lat, lon). curated_polygons.geojson stores sub-
    polygons keyed by `name` (Dubai Marina, JBR, Bluewaters Island, …)
    each with a `parent_area_name_en` (Marsa Dubai). DLD's area_name_en is
    the parent, so we aggregate all sub-polygon vertices under that parent."""
    if not GEOJSON.exists():
        return {}
    pts_per_area = collections.defaultdict(list)
    sub_pts = collections.defaultdict(list)  # sub-community name → pts (for finer centroid)
    dld_aliases = {}  # DLD area_name_en → display name for centroid lookup
    with GEOJSON.open(encoding='utf-8') as f:
        gj = json.load(f)
    for feat in gj.get('features', []):
        props = feat.get('properties', {})
        sub_name = props.get('name') or ''
        parent = props.get('parent_area_name_en') or ''
        area = parent or sub_name or props.get('NAME_EN') or ''
        if not area:
            continue
        filt = props.get('filter') or {}
        if filt.get('area_name_en'):
            dld_aliases[filt['area_name_en']] = area
        geom = feat.get('geometry') or {}
        rings = []
        if geom.get('type') == 'Polygon':
            rings = geom['coordinates']
        elif geom.get('type') == 'MultiPolygon':
            for poly in geom['coordinates']:
                rings.extend(poly)
        for ring in rings:
            for p in ring:
                pts_per_area[area].append((p[1], p[0]))
                if parent and sub_name:
                    sub_pts[sub_name].append((p[1], p[0]))
    out = {}
    for area, pts in pts_per_area.items():
        if not pts:
            continue
        lat = sum(p[0] for p in pts) / len(pts)
        lon = sum(p[1] for p in pts) / len(pts)
        out[area] = (lat, lon)
    for sub_name, pts in sub_pts.items():
        if sub_name not in out and pts:
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
            out[sub_name] = (lat, lon)
    for dld_name, display_name in dld_aliases.items():
        if dld_name not in out and display_name in out:
            out[dld_name] = out[display_name]
    return out
