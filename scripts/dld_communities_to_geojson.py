#!/usr/bin/env python3
"""Convert data/dld_communities.kml → data/dld_communities.geojson.

KML structure (per `dld_communities_pull.sh`, datasetId 461494):
  Document
    Placemark (×224)
      ExtendedData/SchemaData/SimpleData[name=...]   ← attribute table
      Polygon/outerBoundaryIs/LinearRing/coordinates ← "lon,lat,alt ..."

All 224 placemarks are simple Polygons (no MultiGeometry, no inner rings —
verified in-session). If DM ever starts emitting holes / multi-pieces we'll
notice via the assertion below.

Output schema (per feature):
  properties:
    cname_e     CNAME_E       English community name (the join key vs DLD area_name_en)
    cname_a     CNAME_A       Arabic community name
    label_e     LABEL_E       Often same as CNAME_E
    label_a     LABEL_A
    comm_num    COMM_NUM      Stable numeric ID (integer)
    dgis_id     DGIS_ID       DM internal GIS ID, zero-padded string ("0000172")
    ndgis_id    NDGIS_ID      Same as dgis_id with leading zeros stripped
    objectid    OBJECTID      Snapshot-local row number (NOT stable across snapshots)
    source      'dld-dm'      So downstream code can distinguish from osm-* sources
"""
import json
import os
import sys

from lxml import etree

NS = {'k': 'http://www.opengis.net/kml/2.2'}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'data', 'dld_communities.kml')
DST  = os.path.join(ROOT, 'data', 'dld_communities.geojson')

# Map KML SimpleData names to GeoJSON property names (lowercase) +
# whether the field should be cast to int.
FIELDS = [
    ('CNAME_E',     'cname_e',    False),
    ('CNAME_A',     'cname_a',    False),
    ('LABEL_E',     'label_e',    False),
    ('LABEL_A',     'label_a',    False),
    ('COMMUNITY_E', 'community_e', False),
    ('COMMUNITY_A', 'community_a', False),
    ('COMM_NUM',    'comm_num',   True),
    ('DGIS_ID',     'dgis_id',    False),
    ('NDGIS_ID',    'ndgis_id',   True),
    ('OBJECTID',    'objectid',   True),
]


def parse_coords(text):
    """KML coordinates: whitespace-separated 'lon,lat[,alt]' tuples → GeoJSON ring.

    GeoJSON rings drop the altitude. We don't enforce closed-ness; DM's KML
    is well-behaved and the rings are closed already. If they weren't,
    Shapely consumers would auto-close anyway.
    """
    ring = []
    for triple in text.split():
        parts = triple.split(',')
        lon, lat = float(parts[0]), float(parts[1])
        ring.append([lon, lat])
    return ring


def extract_props(pm):
    props = {'source': 'dld-dm'}
    sds = {sd.get('name'): (sd.text or '') for sd in pm.findall('.//k:SimpleData', NS)}
    for kml_key, out_key, is_int in FIELDS:
        v = sds.get(kml_key, '').strip()
        if not v:
            props[out_key] = None
            continue
        if is_int:
            try:
                props[out_key] = int(v)
            except ValueError:
                # Keep the raw string if it doesn't parse — better than dropping.
                props[out_key] = v
        else:
            props[out_key] = v
    return props


def extract_geom(pm):
    polys = pm.findall('.//k:Polygon', NS)
    if not polys:
        return None
    if len(polys) > 1:
        # If this ever fires, the file changed shape and we need to handle
        # MultiPolygon — easy fix but worth flagging.
        raise ValueError('multiple Polygons in one Placemark — expected exactly 1')

    poly = polys[0]
    outer_el = poly.find('.//k:outerBoundaryIs/k:LinearRing/k:coordinates', NS)
    if outer_el is None or not outer_el.text:
        raise ValueError('Polygon missing outer coordinates')
    outer = parse_coords(outer_el.text)

    rings = [outer]
    for inner_el in poly.findall('.//k:innerBoundaryIs/k:LinearRing/k:coordinates', NS):
        if inner_el.text:
            rings.append(parse_coords(inner_el.text))

    return {'type': 'Polygon', 'coordinates': rings}


def main():
    if not os.path.exists(SRC):
        sys.exit(f'missing {SRC} — run scripts/dld_communities_pull.sh first')

    tree = etree.parse(SRC)
    placemarks = tree.findall('.//k:Placemark', NS)
    if not placemarks:
        sys.exit('no Placemark elements found — KML schema changed?')

    features = []
    skipped = 0
    for pm in placemarks:
        try:
            geom = extract_geom(pm)
        except ValueError as e:
            name = pm.findtext('k:name', namespaces=NS) or '?'
            print(f'  skip {name}: {e}', file=sys.stderr)
            skipped += 1
            continue
        if geom is None:
            skipped += 1
            continue
        features.append({
            'type':       'Feature',
            'properties': extract_props(pm),
            'geometry':   geom,
        })

    out = {'type': 'FeatureCollection', 'features': features}
    with open(DST, 'w', encoding='utf-8') as f:
        # Pretty-printed for grep-ability; ~4 MB vs ~2.5 MB compact — acceptable.
        json.dump(out, f, ensure_ascii=False, indent=1)

    size_kb = os.path.getsize(DST) // 1024
    print(f'wrote {DST}  features={len(features)}  skipped={skipped}  size={size_kb} KB',
          file=sys.stderr)


if __name__ == '__main__':
    main()
