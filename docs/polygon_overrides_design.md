# Curated polygon overrides — design

Goal: replace the OSM-stitched `data/dld_communities_osm.geojson` (442 polygons with
duplicates and nominatim-fallbacks) with a clean curated set keyed to DLD data.

## Pipeline

```
  data/dld_communities.kml  (DM Communities — 224 admin polygons, datasetId=461494)
            │
            ▼
  data/dld_communities.geojson  ←  scripts/dld_communities_to_geojson.py
            │
            │     ▲
            │     │  data/polygon_overrides.json   (hand-curated)
            │     │
            ▼     │  data/dld_communities_osm.geojson    (legacy OSM polygons — used as
   ┌─────────────┴──────────────┐                  geometry source for sub-zones)
   │ build_curated_polygons.py  │
   └────────────┬───────────────┘
                ▼
  data/curated_polygons.geojson  (the new ground truth)
                │
                ├──→  build_transactions_map.py  (sales per-polygon aggregates)
                ├──→  build_rents_map.py
                ├──→  build_growth_map.py
                └──→  build_payback_map.py
```

## Schema of `data/polygon_overrides.json`

```jsonc
{
  "version": 1,

  // List of admin communities (area_name_en) that DLD lumps but where we want
  // distinct sub-polygons on the map. For each, list the sub-polygons we'd
  // like and their corresponding DLD master_project_en filters.
  "splits": [
    {
      // The DLD area_name_en this split applies to.
      "area_name_en": "Marsa Dubai",

      // True → keep the DM parent polygon with a "remainder" filter (the few
      //        transactions that don't match any child master_project).
      // False → drop the DM parent entirely. Leftover transactions disappear
      //         from the map (typically <5%).
      "keep_remainder": true,

      // Display name when keep_remainder=true.
      "remainder_name": "Marsa Dubai (other)",

      "sub_polygons": [
        {
          // Display name on map (will be lowercase'd for the polygon key).
          "name": "Dubai Marina",

          // Optional translations (ar/ru/hi/zh). EN comes from `name`.
          "name_ar": "مرسى دبي",

          // Geometry source: name of a feature in `data/dld_communities_osm.geojson`
          // whose polygon we copy. We don't use its data — only its shape.
          "osm_polygon": "Dubai Marina",

          // DLD filter: which master_project_en values fall into this polygon.
          // Aggregation will WHERE area_name_en = <parent> AND master_project_en IN (...)
          "master_projects": ["Dubai Marina"]
        },
        // ... more sub-polygons
      ]
    }
  ],

  // (Reserved for future use — currently we build from DM base which is clean,
  // so no merges needed. If we ever need to "fuse two DM communities into one",
  // this is where it'd go.)
  "merges": []
}
```

## Output schema of `data/curated_polygons.geojson`

```jsonc
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Polygon", "coordinates": [...] },
      "properties": {
        "name": "Dubai Marina",          // English label
        "name_ar": "مرسى دبي",
        "key": "dubai marina",            // lowercased name, aggregate join key
        "source": "split-osm",            // dm-community | split-osm | split-remainder
        "parent_area_name_en": "Marsa Dubai",   // null for non-split polygons
        "filter": {                        // how to compute aggregates for this polygon
          "area_name_en": "Marsa Dubai",
          "master_projects_in": ["Dubai Marina"]   // null/missing = no filter
        }
      }
    }
  ]
}
```

The `properties.filter` block is what the 4 build_*_map.py scripts use to
build the per-period SQL. The filter is the source of truth for what
transactions belong to this polygon. No fuzzy matching, no string fallbacks.

## Aggregation logic per polygon

```sql
SELECT ...
FROM tx.parquet
WHERE 1=1
  AND ({filter.area_name_en       ? "area_name_en = ?" : ""})
  AND ({filter.master_projects_in ? "master_project_en IN (?, ?, ?, ...)" : ""})
  AND ({filter.master_projects_not_in ? "(master_project_en NOT IN (?, ...) OR master_project_en IS NULL)" : ""})
  AND instance_date BETWEEN ? AND ?
```

For "split-remainder" polygons, `master_projects_not_in` lists all the
master_projects consumed by sibling sub-polygons → catches the leftovers.

## Why this approach (vs alternatives)

| Option | Verdict |
|---|---|
| Stick with OSM-stitched `data/dld_communities_osm.geojson` | Status quo — duplicates, holes, nominatim-fallback for DH. Rejected. |
| Pure DM Communities (224 polygons, no splits) | Clean but Marsa Dubai blob. Rejected for not solving the user-visible problem. |
| Custom polygons drawn by hand | Highest quality but weeks of GIS work. Skipped. |
| **DM base + handcrafted splits using OSM geometry** | **Chosen.** ~85% of needed sub-polygons are in OSM with decent quality; rest can be added later. Honest about provenance (`source` field). |
| Reverse-engineer competitor's polygon set | Legally murky. Skipped. |

## Verification

A curated set is valid iff:

1. Sum of per-polygon transaction counts (with filters applied) equals total
   transactions in tx.parquet (modulo any explicitly-discarded polygons).
2. No transaction is counted in more than one polygon.
3. The Marsa Dubai split case: `Dubai Marina + JBR + Dubai Harbour +
   Bluewaters [+ Marsa Dubai (other)] == area_name_en='Marsa Dubai'` total.

The build script asserts (1) and (3); (2) is implied by SQL filter disjointness
which is enforced by the override schema (no `master_project_en` can appear in
multiple `master_projects` lists within the same split).
