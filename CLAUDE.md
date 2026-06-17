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

   **Current handling: hardcoded `ROLLUP_SQL` CASE** in `build_{sale,rent}_aggregates.py`. Pattern is hand-curated, not auto-detected. Surveying for new fragmentation: query areas where `master_project_en` values share first 1-2 words (DuckDB `REGEXP_REPLACE` to extract family root).

   What NOT to roll up: `Arabian Ranches - 1 / II / 3` (legit separate geographies), `DAMAC Hills` vs `DAMAC Hills 2` (different `area_name_en` sectors), `Marsa Dubai` containing `Dubai Marina / JBR / Dubai Harbour` (legitimately distinct communities). Geographic separation > naming similarity.

   **Better long-term:** swap the CASE-list for a community taxonomy table joined at view-time, source of truth for sub→parent mapping. Or pull community polygons from DLD's GIS shapefile (not OSM) and key by spatial join. Currently a thinking-required problem; CASE is a stopgap.

## File / data layout

```
data/
  tx.parquet            ← deduplicated transactions
  rents.parquet         ← deduplicated rent contracts
~/Downloads/dld_transactions/
  transactions_<date>_*/<filename>.csv.gz   ← raw snapshot (golden source backup)
  download.log
~/Downloads/dld_rent_contracts/
  rent_contracts_<date>_*/<filename>.csv.gz
  download.log
scripts/
  dld_download.sh       ← polite (1.5 MB/s) resumable downloader
  dld_to_parquet.sh     ← dedup latest snapshot → parquet (DuckDB)
  dld_check_new.sh      ← compare API listing vs local — flag if newer exists
  dld_refresh.sh        ← orchestrates download → parquet
  dld_filter.py         ← optional: filter CSV.gz by date column (pre-parquet era)
  khda_scrape.py        ← fetch KHDA Education Directory → data/khda_schools.csv
  osm_schools_pull.py   ← Overpass `amenity=school` in Dubai bbox → data/osm_schools.json
  khda_merge_into_viewer.py ← join OSM + KHDA, write SCHOOLS into index.html
  khda_refresh.sh       ← weekly orchestrator: runs all three above in sequence
```

Raw downloads live outside the repo (`~/Downloads/...`) because they're large (~2.4 GB) and regeneratable. `.gitignore` blocks `transactions-*.csv` / `rents-*.csv` in repo root (legacy DLD-portal exports — superseded by Parquet).

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

## Source / API reference

- Portal: <https://data.dubai/en/l/470061> (TX), <https://data.dubai/en/l/468586> (Rents)
- Listing API: `https://data.dubai/o/dda/data-services/dataset-download?datasetId=<id>&page=1&pageSize=200&sortDir=desc`
- Returns JSON with `data.metadata[].file_folder` + `files[].file_url` (presigned S3, 600s TTL — `dld_download.sh` refreshes per round).
