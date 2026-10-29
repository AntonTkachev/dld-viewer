# DLD viewer — operating notes

## What's in `data/`

| File | Source | Rows | Size | Дедуп-ключ |
|---|---|---:|---:|---|
| `tx.parquet` | DLD transactions (Dubai Pulse datasetId `470061`) | ~1.72M | 60 MB | `transaction_id` |
| `rents.parquet` | DLD rent contracts (datasetId `468586`) | ~10.1M | 287 MB | `(contract_id, line_number)` |

ZSTD-9 compressed, Parquet. Read with DuckDB / Polars / pyarrow. All columns are `VARCHAR` — cast on read if you need numeric/date types (`CAST(actual_worth AS DOUBLE)`, `CAST(instance_date AS DATE)`, etc.).

## How to refresh (weekly or as needed)

```bash
./scripts/dld_check_new.sh      # prints "Up to date." or "NEWER than local"
./scripts/dld_refresh.sh        # if newer exists: downloads + rebuilds parquet
```

`dld_refresh.sh` is idempotent. The download script has `.done` markers, so re-runs skip what's already there.

## Critical facts about the data — learned the hard way, don't repeat the investigation

1. **Each DLD snapshot is a complete cumulative superset of all earlier snapshots.** Verified: every (contract_id, contract_start_date) and (transaction_id, instance_date) in older snapshots is 100% present in the latest. **Therefore only the latest snapshot matters.** Older ones can be deleted with zero data loss. `dld_to_parquet.sh` always uses only the lexicographically newest `*.csv.gz`.

2. **Raw CSVs have massive duplicate-row redundancy** — same logical record repeated 3–7× with different `load_timestamp` (DLD's internal audit field). Rows are byte-identical except for that column. `SELECT DISTINCT * EXCLUDE load_timestamp` collapses everything cleanly.
   - TX raw: 12M rows → 1.72M unique transactions (~7× factor)
   - Rents raw: 33M rows → 10.1M unique line-items (~3.3× factor)
   - **NEVER count raw CSV rows as "transactions" or "contracts"** — always count post-dedup.

3. **DLD CSVs are malformed** — stray unterminated quotes inside Arabic strings. DuckDB needs `strict_mode=false, ignore_errors=true` to read them. ~0–20 broken rows per file get skipped; acceptable rounding.

4. **`line_number` in rents** = position of one property inside a multi-property master contract (e.g. a single Ejari covering a 480-unit labor camp will have 480 rows, one per unit). Not a duplicate. The dedup key `(contract_id, line_number)` is the line-item grain.

5. **Forward-dated contracts are normal in rents** — `contract_start_date` can be many months in the future (lease registered now, starts later). Max in current data: `2026-12-31` (and a few "future" beyond). Filter explicitly if you need only contracts already in force.

6. **API keeps a rolling window of ~5 most recent snapshots.** When DLD publishes a new one, the oldest disappears from the API. So "snapshot we have locally is missing from API" is normal, not an error.

7. **DLD publish cadence is irregular.** Observed: bursts of 1–5 days, then long quiet stretches (17+ days seen). Treat weekly checks as the floor — if `dld_check_new.sh` keeps showing "Up to date", that's fine, it's DLD being slow.

8. **Snapshot freshness lag:** the snapshot timestamp in the folder name (e.g. `..._2026-05-29_02-08-58_2`) is when DLD generated it. The `instance_date` inside lags by ~5–8 days from that. Plan accordingly.

9. **Sub-master rollup — DLD splits some communities across multiple `master_project_en`.** Same physical community, different label per sub-project or phase. Verified: each transaction sits under exactly one master, no duplication — pure taxonomy partition, safe to sum. Survey of fragmented areas (sub-masters in same `area_name_en`):

   | Parent community | Sub-master pattern | tx hidden |
   |---|---|---:|
   | Dubai Hills Estate | `DUBAI HILLS - MAPLE/SIDRA/GOLF/...` + generic `DUBAI HILLS` (19 variants) | +11.8K |
   | Emirates Living | `Lakes - Maeen/Ghadeer/Hattan/Deema/Forat` (10 variants) | +4K |
   | Jumeirah Golf Estates | `Jumeirah Golf Estates - Phase B` | +230 |
   | International City Phase 3 | `International City Phase 2` (same Warsan Fourth area) | +142 |
   | Liwan | `Liwan1`, `Liwan2` (no hyphen) | +11.8K |

   **Current handling: hardcoded `ROLLUP_SQL` CASE** in `scripts/_aggregates_common.py` (shared by sale + rent; Python mirror `rollup_master` in `merge_curated_polygons_into_viewer.py` — `tests/test_rollup_sql.py` guards drift). Pattern is hand-curated, not auto-detected. Surveying for new fragmentation: query areas where `master_project_en` values share first 1-2 words (DuckDB `REGEXP_REPLACE` to extract family root).

   What NOT to roll up: `Arabian Ranches - 1 / II / 3` (legit separate geographies), `DAMAC Hills` vs `DAMAC Hills 2` (different `area_name_en` sectors), `Marsa Dubai` containing `Dubai Marina / JBR / Dubai Harbour` (legitimately distinct communities). Geographic separation > naming similarity.

   **Better long-term:** swap the CASE-list for a community taxonomy table joined at view-time, source of truth for sub→parent mapping. Or pull community polygons from DLD's GIS shapefile (not OSM) and key by spatial join. Currently a thinking-required problem; CASE is a stopgap.

10. **Ejari has no building field, and tags a project on only ~16% of rent contracts** (`project_name_en` + `project_number` always filled together or both empty; the rest carry only area/master). So building-level rent is really project-level and most buildings legitimately have `rn=0` (e.g. Seven City JLT: 3.5K sales, zero project-tagged contracts). Join rents on `project_number`, never on `project_name_en` — names repeat across areas (two different `BOTANICA` projects, JVC and Marina, were summed by the old name join).

11. **`building_name_en` is not unique.** A building = `(building_name_en, area_name_en)`, split further by `project_number` when two projects each have 5+ sales (Capria East/West both have "CAPRIA 4"). Slugs in `buildings/`: busiest building keeps the bare slug, others get `-<public-area>` suffix — see `build_building_pages.py`; regression test `scripts/test_building_pages.py`.

## File / data layout

```
data/
  tx.parquet            ← deduplicated transactions
  rents.parquet         ← deduplicated rent contracts
  raw/
    dld_transactions/
      transactions_<date>_*/<filename>.csv.gz   ← raw snapshot (golden source backup)
      download.log
    dld_rent_contracts/
      rent_contracts_<date>_*/<filename>.csv.gz
      download.log
    dld_buildings/
      building_summary_information.csv.gz
scripts/
  dld_download.sh       ← polite (1.5 MB/s) resumable downloader
  dld_to_parquet.sh     ← dedup latest snapshot → parquet (DuckDB)
  dld_check_new.sh      ← compare API listing vs local — flag if newer exists
  dld_refresh.sh        ← orchestrates download → parquet
  khda_scrape.py        ← fetch KHDA K-12 + Higher-Ed directories
                          → data/khda_schools.csv + khda_universities.csv
  osm_schools_pull.py   ← Overpass amenity=school|university|college (Dubai bbox)
                          → data/osm_schools.json + osm_universities.json
  khda_merge_into_viewer.py ← join OSM + KHDA, write SCHOOLS into index.html;
                              chains to khda_uni_merge_into_viewer.py for UNIVERSITIES
  khda_uni_merge_into_viewer.py ← Higher-Ed-specific merge logic; called by the line above
  khda_refresh.sh       ← weekly orchestrator: scrape → pull → merge → build_pages
```

Raw downloads live in `data/raw/` (gitignored — large, ~2.4 GB, and regeneratable via `dld_refresh.sh` / `dld_buildings_pull.sh`). `.gitignore` also blocks `transactions-*.csv` / `rents-*.csv` in repo root (legacy DLD-portal exports — superseded by Parquet).

## Don't trust the DLD-portal CSV files

`rents-YYYY-MM-DD.csv` and `transactions-YYYY-MM-DD.csv` (UPPERCASE columns) come from the manual DLD portal export. They are **silently truncated** (~12K rows for rents; transactions are larger but use community-name `AREA_EN` instead of admin sector). The Parquet files in `data/` are the source of truth.

## KHDA schools (Education Directory)

- Source: <https://web.khda.gov.ae/en/Education-Directory/Schools> — server-rendered ASP.NET page; **no CSV/JSON export**.
- Dubai Pulse dataset `468962` (<https://data.dubai/en/l/468962>) looks like a schools dataset but is a search-only service — listing API returns `metadata: []` (no downloadable files).
- All ~233 school cards are embedded in the initial HTML. `scripts/khda_scrape.py` GETs the page and parses each card's `lblArea` / `lblTelephone` / `lblCurriculums` / `lblgradeRange` + the DSIB overall + Wellbeing + Inclusion rating badges into `data/khda_schools.csv`.
- The OSM seed comes from `scripts/osm_schools_pull.py` (Overpass `amenity=school` over the Dubai bbox). It drops mapper noise: bare nodes with no other tags, and `barrier`-tagged entries (fences mistakenly tagged as schools). About 60/416 elements get filtered this way; the remainder (~355) becomes `data/osm_schools.json`.
- `scripts/khda_merge_into_viewer.py` joins KHDA onto that OSM seed in five stages, first-wins:
  1. **Exact normalized** — strip case/punctuation/suffix words (`L.L.C`, `Branch`, `Dubai`, …).
  2. **Token-set Jaccard ≥ 0.6** with subset bonus.
  3. **SequenceMatcher ≥ 0.74** for typos (e.g. *Engllish* vs *English*); guarded by "at least one distinctive token in common" to avoid generic `School/School` matches.
  4. **Proximity tiebreaker** — when stage 2 reported ambiguity (e.g. KHDA has two *Al Mawakeb* branches), prefer the candidate whose `area` substring appears in OSM `addr_suburb` / `name`.
  5. **Polygon proximity** — last-ditch: find the GEOJSON polygon containing the OSM marker, then accept a weak (SeqMatch ≥ 0.55) match if exactly one KHDA candidate is tagged with that polygon's name.
- Also pre-filtered out before matching: OSM `amenity=school` entries whose name contains *university* / *driving institute* / *musical arts* / *accommodation* — KHDA covers K-12 only.
- Refresh end-to-end (always re-fetches everything — total payload is small enough that diff-check isn't worth it):
  ```bash
  scripts/khda_refresh.sh
  ```
  Wire it into cron for a weekly run, e.g. Sundays 04:30:
  ```
  30 4 * * 0  cd /Users/anton/IdeaProjects/dld_viewer && scripts/khda_refresh.sh >> data/.khda_refresh.log 2>&1
  ```
- Current state: 107/274 named OSM schools matched, ~126 KHDA-only have no OSM coordinates. The remaining 167 unmatched OSM-named schools are a mix of (a) arabic-only-name madrasas (KHDA names are English only), (b) genuinely missing from KHDA (kindergartens, special-needs centres), (c) small private schools KHDA listed under a different legal-entity name we can't fuzzy-match safely.

## Data sources — full catalog

Every dataset behind the site, with portal URL, dataset id (when applicable), pull script, and output file. This is the contract between raw upstream and our processed `data/` folder. If you add a new source, append a row here AND ship a `scripts/*_pull.*` script alongside it — that's how this codebase stays bootstrappable from a fresh clone.

### Dubai Pulse / data.dubai (DLD + DM)

All five datasets below share one public API:
- Listing API: `https://data.dubai/o/dda/data-services/dataset-download?datasetId=<id>&page=1&pageSize=200&sortDir=desc`
- Returns JSON with `data.metadata[].file_folder` + `files[].file_url` (presigned S3, 600s TTL — `dld_download.sh` re-fetches per round for multi-GB jobs).
- API is open: no auth, no rate-limit headers, no user-agent gating. The portal pages themselves require login for the download button but the listing API does not.

| Dataset | id | Portal | Pull script | Output | Size | Refresh |
|---|---:|---|---|---|---:|---|
| Transactions (sales / mortgages / gifts) | 470061 | <https://data.dubai/en/l/470061> | `scripts/dld_tx_pull.sh` → `scripts/dld_to_parquet.sh data/raw/dld_transactions data/tx.parquet` | `data/tx.parquet` (also raw CSVs in `data/raw/dld_transactions/`) | 60 MB | weekly (irregular cadence — see fact #7) |
| Rent contracts (Ejari) | 468586 | <https://data.dubai/en/l/468586> | `scripts/dld_rents_pull.sh` → `scripts/dld_to_parquet.sh data/raw/dld_rent_contracts data/rents.parquet` | `data/rents.parquet` | 287 MB | weekly |
| Real Estate Projects (RERA register) | 467654 | <https://data.dubai/en/l/467654> | `scripts/dld_projects_pull.py` | `data/dld_projects.csv.gz` | 451 KB | weekly |
| Communities (DM GIS NET admin polygons) | 461494 | <https://data.dubai/en/l/461494> | `scripts/dld_communities_pull.sh` → `scripts/dld_communities_to_geojson.py` | `data/dld_communities.kml` + `data/dld_communities.geojson` | 2.3 MB / 3.4 MB | rarely (boundaries are stable) |
| Building Summary Information (DM Building Control completion certificates) | 459523 | <https://data.dubai/en/l/459523> | `scripts/dld_buildings_pull.sh` → `scripts/dld_buildings_to_signal.py` | `data/dld_buildings_signal.json` (slim 1.8 MB digest; raw 207 MB CSV stays in `data/raw/dld_buildings/`) | 1.8 MB | monthly |

**Cross-checking RERA against DM Buildings + Ejari:** `scripts/_rera_enrich.py` derives a cleaned `__derived_status` per RERA project. Rule: if ≥50% of a project's buildings are status="New" in DM Building Control → silently reclassify ACTIVE → FINISHED. Fallback: Ejari rentals ≥5/12mo or ≥30 total. Mechanism stays server-side (data.json doesn't expose the join), so the construction page and map badges show a cleaner pipeline than RERA alone.

Related Dubai Pulse datasets we've **looked at but don't pull yet** (potential pipelines):
- 725256 Completed Buildings, 725270 Completed Buildings by Urban/Rural — statistical aggregates, not project-level, lower ROI than 459523.

### KHDA (Knowledge & Human Development Authority)

KHDA publishes **no API or CSV** — only server-rendered ASP.NET pages with every card embedded inline.

| Source | URL | Pull script | Output |
|---|---|---|---|
| K-12 schools directory | <https://web.khda.gov.ae/en/Education-Directory/Schools> | `scripts/khda_scrape.py` | `data/khda_schools.csv` |
| Higher Education directory | <https://web.khda.gov.ae/en/Education-Directory/Higher-Education-Institutions-Directory> | `scripts/khda_scrape.py` (same script handles both) | `data/khda_universities.csv` |

Orchestrator: `scripts/khda_refresh.sh` — scrape → OSM merge → `build_pages` chain.

### OpenStreetMap (Overpass API)

POI seeds for the map's layers (schools / universities / medical / mosques / metro / malls). Overpass endpoint: <https://overpass-api.de/api/interpreter> (we use the standard public instance; the queries are tiny, no rate limit issues).

| Layer | Overpass tag(s) | Pull script | Output |
|---|---|---|---|
| Schools | `amenity=school` (Dubai bbox) | `scripts/osm_schools_pull.py` | `data/osm_schools.json` |
| Universities & colleges | `amenity=university\|college` (Dubai bbox, same script as schools) | `scripts/osm_schools_pull.py` | `data/osm_universities.json` |
| Medical | `amenity=hospital\|clinic\|doctors` (Dubai bbox) | `scripts/osm_medical_pull.py` | `data/osm_medical.json` |
| Malls + souqs | `shop=mall` + `amenity=marketplace` (souq-tagged) | `scripts/osm_malls_pull.py` | `data/osm_malls.json` |
| Sub-communities (Springs/Meadows phases etc.) | named `landuse=residential` / `place=residential` polygons | `scripts/osm_subcommunities_pull.py` | `data/osm_subcommunities.json` |
| Metro stations + lines | `railway=station` (Dubai Metro) | `scripts/osm_metro_pull.py` | `data/osm_metro_stations.json` + `data/osm_metro_lines.json` |
| Mosques | `amenity=place_of_worship religion=muslim` | `scripts/osm_mosques_pull.py` | `data/osm_mosques.json` |

### Building geocoding (manual, one-off-ish — not in any orchestrator)

Puts DLD buildings (`area_name_en`, `building_name_en`) on the map. Only needed when rebuilding the buildings layer from scratch; `refresh_all.sh` runs `build_buildings_map.py --relink`, which reuses `data/buildings_geo.json` and only relinks slug/rn/yr/dev from `buildings/search-index.json`.

| Step | Script | Output | Notes |
|---|---|---|---|
| 1 | `scripts/osm_buildings_pull.py` | `data/osm_buildings.json` (gitignored) | named OSM buildings + footprints, Overpass |
| 2 | `scripts/wikidata_buildings_pull.py` | `data/wikidata_buildings.json` | QLever SPARQL mirror of Wikidata |
| 3 | `scripts/nominatim_buildings_pull.py` | `data/nominatim_buildings.json` | per-building geocode from `buildings/search-index.json`, 1 req/s, resumable (`--status`) |
| 4 | `scripts/merge_building_coords.py` | `data/building_coords.json` | priority Wikidata > OSM > Nominatim, fuzzy one-to-one name match |
| 5 | `scripts/google_buildings_pull.py --key AIza…` | `data/google_buildings.json` | paid Google Geocoding fallback, resumable cache; work list `data/google_buildings_todo.json` is a hand-made 2026-07 snapshot of still-unmatched buildings — regenerate before a new run |
| 6 | `scripts/osm_all_footprints_pull.py [--resume]` | `data/osm_all_footprints.json` (gitignored, ~50–100 MB) | all ~366K footprints for point-in-polygon; if present, `build_buildings_map.py` uses it instead of `osm_buildings.json` + `data/osm_unnamed_footprints.json` |
| 7 | `scripts/build_buildings_map.py` (no flag) | `data/buildings_geo.json` (gitignored) + `buildings/data.js` | full match: staged name matcher (`_bmap_match.py`) + PIP + geo-sanity vs curated polygons; manual fixes in `data/building_osm_overrides.json`; golden test `scripts/test_buildings_match.py` |

### Manually curated (no pull script — checked into the repo)

| File | Purpose | Edit notes |
|---|---|---|
| `data/polygon_overrides.json` | Hand-curated split rules for the 16 master-projects that need to be visually broken out from their DLD admin parent (Marina out of Marsa Dubai, Sports City out of Al Hebiah Fourth, etc.) | See `docs/polygon_overrides_design.md` for the schema |
| `data/dm_to_dld_aliases.json` | DM admin spelling ↔ DLD spelling mappings + display-name overrides (Burj Khalifa → Downtown Dubai, NAKHLAT JUMEIRA → Palm Jumeirah) | 34 entries, all manually verified |
| `data/rera_arabic_aliases.json` | Arabic → English mappings for the top 44 RERA developers + 3 project classifications. Project name English mapping is done via tx.parquet join, not aliases | See `_skipped` section for known gaps |

**Caveat — adding/changing a `display_name` retires the old slug.** Once an alias gets a `display_name`, `build_district_pages.py` only ever emits pages under the new slug — the raw admin-name slug stops being generated. If Google had already indexed that old slug (found 2026-09-27: `al-barsha-south-fourth` → `jumeirah-village-circle`, plus similar cases from `polygon_overrides.json` renames), the old URL 404s forever unless something redirects it. `scripts/build_renamed_area_redirects.py` back-fills a canonical+meta-refresh stub at every old (lang, mode, subpath) combo that has a live target — it's wired into `refresh_all.sh` (phase 8a) so this self-heals on the next full rebuild after an alias edit. It only knows the `dm_to_dld_aliases.json` pairs automatically; a rename done purely inside `polygon_overrides.json` (no old-name field to diff against) needs a manual entry added to `LEGACY_SLUG_PAIRS` in that script. Also check `data/seo_whitelist.json` for the old slug when renaming — a stale whitelist entry makes the retired page's *redirect stub* itself show up in `sitemap.xml`, which is wrong (caught and fixed for `al-rega` / `dubai-south-residential-district` during that same investigation).

### Derived (no pull script — generated from other sources)

| File | Source(s) | Generator |
|---|---|---|
| `data/curated_polygons.geojson` | `dld_communities.geojson` + `polygon_overrides.json` + `osm_subcommunities.json` + `dm_to_dld_aliases.json` | `scripts/build_curated_polygons.py` |
| `polygons/curated.js` | `data/curated_polygons.geojson` + AGGREGATES + ROLLUP rules | `scripts/merge_curated_polygons_into_viewer.py` |
| `periods/all.js` | `{transactions,rents,growth,payback,yearly_sell,yearly_rent}/data/*.json` | `scripts/inline_periods.py` |
| `/{lang}/buildings/index.html` (directory, 5 langs) + `/buildings/index.html` (redirect stub → `/en/buildings/`) | `buildings/search-index.json` | `scripts/build_buildings_directory.py` (phase 8b2) — don't hand-edit the HTML |
| `/{lang}/buildings/<slug>/index.html` (per-building pages, 5 langs; pg/ni flags in search-index decide generate/noindex) + redirect stubs for retired slugs (`data/building_slug_history.json`, append-only) | `buildings/<slug>/data.json` | `scripts/build_building_seo_pages.py` (phase 8b3) |

## Where runtime data bundles live

Originally all data was inlined into `template.html` as `const X = {...};` blocks. Each of the 35 SEO landings then carried a full copy of the same data — every mask navigation re-downloaded the same ~3 MB of inline JSON.

Externalized so far (one cache-busted file per bundle, browser caches once across all landing navigations):

| What | Where | Format | Generator |
|---|---|---|---|
| Curated polygon set | `polygons/curated.js` | `const GEOJSON = {...};` | `scripts/merge_curated_polygons_into_viewer.py` |
| 6 mask period datasets (TX, RENTS, GROWTH, PAYBACK, YEARLY_SELL, YEARLY_RENT) | `periods/all.js` | 6× `const X_PERIODS = {...};` | `scripts/inline_periods.py` |

Template references each via `<script src="/<dir>/<file>.js?v=<sha8>"></script>`. The `?v=…` flips on content change; the file URL is essentially immutable so browser+CDN caches it forever.

These live in dedicated top-level dirs (`/polygons/`, `/periods/`) — NOT in `/data/` — so the Jekyll exclude rule for `data/` can stay a simple blanket deny. No allow-by-omission with per-extension globs.

LIFECYCLE is still inline in `template.html` inside the `<script data-inlined="periods">` wrapper (sits next to where the 6 period consts used to be). It's managed by a different generator (`lifecycle_merge_into_viewer.py`) — externalize candidate, not done yet.

**Caveat — `osm_subcommunities_merge_into_viewer.py` standalone:** that script mutates `polygons/curated.js` AND rewrites the `?v=hash` in `template.html`, but does NOT touch the 35 SEO landings. Browsers hitting those landings still get the freshly-mutated `curated.js` (the server ignores `?v=`), only cache invalidation lags. To fully sync, run `scripts/build_pages.py` after standalone mutations, or just rely on the next `refresh_all.sh` to regenerate everything.

## iOS app data contract (`/app/v1/`)

The iOS app (`~/SwfitProjects/DXBCompass`) reads ONLY `https://dxbcompass.com/app/v1/` — never site files like `/periods/all.js` or `/sales/<slug>/data.json`. Spec: `~/SwfitProjects/DXBCompass/DATA_CONTRACT.md`.

- Generator: `scripts/build_app_v1.py` (phase 8c of `refresh_all.sh`). Repackages already-built site artifacts; parses `PARENT_OVERRIDES` / `_SEARCH_ALIASES` from `js/viewer.js`, `MASKS` from `js/masks.js` and `KNOWN_BAD_POINTS` from `js/detail-panel.js`, so site-side edits there flow into the app automatically. `data_as_of` = max Sales `instance_date` in `tx.parquet`.
- Files: `manifest.json` (sha256 per file), eager `map/polygons.geojson` + `map/masks.json` + `areas/index.json` (~2 MB raw), lazy `areas/<slug>.json` (~340 files, 7.6 MB total). Writes only changed files; manifest untouched when nothing changed.
- **v1 is additive-only.** Old app versions live for months. Never rename/remove a field, change a type or unit, or drop a mask period inside v1 — breaking changes go to a new `/app/v2/` generated alongside v1. The script warns when an area key disappears (it's the favorites id) — handle via `aliases` in `areas/index.json`.
- Site refactors that rename fields in `sales|rents/<slug>/data.json` or the `*_PERIODS` consts must keep `build_app_v1.py` emitting the same v1 shape.

## Tests

```bash
/usr/bin/python3 -m pytest              # full suite (~5 s); real-data tests auto-skip without parquet / built pages
/usr/bin/python3 -m pytest -m "not data"  # fast subset, also run by the pre-commit hook
```
Tests live in `tests/` and write only to `tmp_path` / `:memory:` DuckDB. `refresh_all.sh` phase 11d runs them after a rebuild. Legacy golden scripts (`scripts/test_*.py`) still run standalone and via `tests/test_golden_scripts.py`.

## Refresh playbook

Per-source manual refresh:
```bash
./scripts/dld_check_new.sh        # checks tx + rents — prints "Up to date" or "NEWER"
./scripts/dld_refresh.sh          # downloads + parquetizes tx + rents if newer
python3 scripts/dld_projects_pull.py   # RERA register
./scripts/dld_buildings_pull.sh && python3 scripts/dld_buildings_to_signal.py   # DM Buildings
./scripts/dld_communities_pull.sh && python3 scripts/dld_communities_to_geojson.py   # DM admin polygons
./scripts/khda_refresh.sh         # KHDA schools + universities
python3 scripts/osm_schools_pull.py
python3 scripts/osm_medical_pull.py
python3 scripts/osm_malls_pull.py
python3 scripts/osm_subcommunities_pull.py
```

After any of those (or after editing `polygon_overrides.json` / `dm_to_dld_aliases.json`), run:
```bash
./scripts/refresh_all.sh    # rebuilds 5 masks + every inlined const + 22K SEO pages + sitemap, ends with smoke test
```
It does NOT pull network sources — those still own their own refresh scripts above.

## Deploy — generated pages live only on `gh-pages`

Generated pages (`en/ ru/ ar/ hi/ zh/ buildings/ app/`, `sales/<slug>/`, `rents/<slug>/`) are gitignored in `main`: committing them grew the repo ~3.4 GB/month (history was purged with `git filter-repo` on 2026-10-26). `scripts/deploy.sh` packs them into one orphan commit on `gh-pages` (force-push, no history) and starts the Pages workflow, which checks out `main` and overlays `gh-pages` before the Jekyll build.

```bash
./scripts/refresh_all.sh
git commit -am "Refresh data"  # tracked files refresh_all touched: index.html, template.html, periods/, polygons/, */data/
./scripts/deploy.sh            # pushes gh-pages, pushes main if ahead, starts the deploy
```

- Pushing `main` alone redeploys code with whatever pages are already on `gh-pages`.
- Restore one generated file from the live snapshot: `git restore -s origin/gh-pages -W -- <path>`.
- New generated top-level dir → add it to `.gitignore` AND `GEN=` in `scripts/deploy.sh`, or it never reaches the site.
