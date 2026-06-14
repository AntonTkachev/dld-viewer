# DLD Viewer — Dubai districts × transactions × infrastructure

Single-file HTML viewer (Leaflet + Chart.js + OSM tiles) for Dubai real estate.

**Live:** [antontkachev.github.io/dld-viewer](https://antontkachev.github.io/dld-viewer/)

## What's inside

- **421 district polygons** sourced from OpenStreetMap (admin_level=10 + place=suburb/neighbourhood + named landuse=residential), including the Hatta exclave
- **Real DLD transaction aggregates** for 2026 YTD (Jan 1 – Jun 14): 102,932 transactions, 395 млрд AED volume
- **Drill-down panel** with Chart.js: daily timeline, rooms breakdown, Off-Plan vs Ready, top projects, top deals, recent deals — clickable from any district
- **Villa / Apartment filter** — split the choropleth by property type
- **Infrastructure layers** (OSM): Dubai Metro 3 lines (Red / Green / Blue under construction), 261 schools (KHDA-style placeholder fields), 45 universities, 83 hospitals, 643 mosques, 119 malls, 281 named construction projects
- **i18n**: RU / EN / AR / HI switchable

## Data caveats

- Transaction data: real from `dubailand.gov.ae/en/open-data/real-estate-data`, Transactions tab, 2026 YTD CSV
- School / hospital / mall / project / mosque / university popup fields beyond OSM tags (curriculum, fees, DHA rating, anchor tenants, etc) are **synthetic placeholders** structured to match the eventual KHDA / DHA / DLD API schemas. Marked with `~` in popups.
- 189 / 421 polygons have direct CSV matches; remaining either have no 2026 transactions or no parent area in CSV.

## How it's built

The whole viewer is one self-contained `index.html` (~3.5 MB) with all data inlined as JSON consts. No backend, no build step. Just open in any browser.

Source pipeline:
- `_data_communities.geojson` — polygons (Overpass API + DLD `carea-lookup`)
- `_data_aggregates.json` — per-area aggregates from the transactions CSV
- These are inlined into `index.html` by the rebuild scripts

## Acknowledgments

- Polygons & basemap: [OpenStreetMap](https://www.openstreetmap.org/) contributors
- Transactions: [Dubai Land Department](https://dubailand.gov.ae/) Open Data
- Map library: [Leaflet](https://leafletjs.com/)
- Charts: [Chart.js](https://www.chartjs.org/)
