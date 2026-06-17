# DLD Viewer — Dubai districts × transactions × infrastructure

Single-file HTML viewer (Leaflet + Chart.js + OSM tiles) for Dubai real estate.

**Live:** [antontkachev.github.io/dld-viewer](https://antontkachev.github.io/dld-viewer/)

## What's inside

- **421 district polygons** sourced from OpenStreetMap (admin_level=10 + place=suburb/neighbourhood + named landuse=residential), including the Hatta exclave
- **Real DLD aggregates from Parquet (full history)** — sales 1995-2026 (1.72M transactions, 6.7 трлн AED), rents 2001-2030 (10.1M contracts), refreshed weekly from Dubai Pulse
- **Drill-down panel** with Chart.js: monthly timeline (YoY trend), rooms breakdown, Off-Plan vs Ready, top projects, top deals, recent deals — clickable from any district
- **Villa / Apartment / Rent filter** — split the choropleth by property type or switch to rental view
- **Infrastructure layers** (OSM): Dubai Metro 3 lines (Red / Green / Blue under construction), 261 schools (KHDA-style placeholder fields), 45 universities, 83 hospitals, 643 mosques, 119 malls, 281 named construction projects
- **i18n**: RU / EN / AR / HI switchable

## Data caveats

- Source: Dubai Pulse `dataset-download` API — DLD Transactions (`470061`) + Rent Contracts (`468586`). See [CLAUDE.md](CLAUDE.md) for refresh pipeline.
- School / hospital / mall / project / mosque / university popup fields beyond OSM tags (curriculum, fees, DHA rating, anchor tenants, etc) are **synthetic placeholders** structured to match the eventual KHDA / DHA / DLD API schemas. Marked with `~` in popups.
- Three parquet admin sectors (Marsa Dubai, Al Thanyah Fifth, Al Barsha South Fifth) are remapped at build time to community-style keys (Dubai Marina / JLT / JVC) so polygons find data.

## How it's built

The whole viewer is one self-contained `index.html` (~8.8 MB) with all data inlined as JSON consts. No backend, no build step. Just open in any browser.

Source pipeline:
- `data/tx.parquet`, `data/rents.parquet` — refreshed via `./scripts/dld_refresh.sh`
- `_data_communities.geojson` — polygons (Overpass API + DLD `carea-lookup`)
- `_data_sale_aggregates.json`, `_data_rent_aggregates.json` — per-area aggregates built by `/tmp/build_sale_aggregates.py` and `/tmp/build_rent_aggregates.py`
- Inlined into `index.html` by the rebuild scripts

## Acknowledgments

- Polygons & basemap: [OpenStreetMap](https://www.openstreetmap.org/) contributors
- Transactions: [Dubai Land Department](https://dubailand.gov.ae/) Open Data
- Map library: [Leaflet](https://leafletjs.com/)
- Charts: [Chart.js](https://www.chartjs.org/)
