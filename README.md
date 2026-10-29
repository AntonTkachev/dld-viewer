# DXB Compass — Dubai real-estate map from DLD open data

Interactive map + ~22K static SEO pages for Dubai property prices, rents, yields and growth, built from Dubai Land Department transactions and Ejari rent contracts.

**Live:** [dxbcompass.com](https://dxbcompass.com)

## What's inside

- **District choropleth** (Leaflet, OSM tiles) on curated DM admin polygons, split where DLD communities don't match admin boundaries (Marina, JVC, Sports City…)
- **Masks:** sales, rents, growth, lifecycle, payback, investor, formula, income, off-plan premium, yearly sell/rent — each with 1y/3y/5y/10y/all periods, map + table view
- **District pages** with charts (timeline, rooms, vintages, off-plan vs ready), FAQ, POIs and a PDF report
- **Buildings:** per-building pages, directory and a map layer
- **Infrastructure layers:** metro, schools (KHDA ratings), universities, medical, mosques, malls, construction projects (RERA)
- **5 languages:** EN / RU / AR / HI / ZH
- **iOS app feed** at `/app/v1/`

## Data

DLD transactions (~1.7M) and Ejari rents (~10M) from the Dubai Pulse open API, deduplicated into Parquet; RERA projects register, DM building completions and admin polygons; KHDA directories; OpenStreetMap POIs. Full source catalog, refresh playbook and data caveats: [CLAUDE.md](CLAUDE.md).

## Build & deploy

Static site, no backend. Python (`/usr/bin/python3` with duckdb + shapely) generates everything from `data/`:

```bash
./scripts/dld_refresh.sh     # pull new DLD snapshots → data/*.parquet
./scripts/refresh_all.sh     # rebuild masks, bundles, all pages, sitemap; runs tests
./scripts/deploy.sh          # generated pages → gh-pages branch, GitHub Pages deploy
```

Tests: `/usr/bin/python3 -m pytest` (see `tests/`).

Layout: `template.html` + `js/` + `css/` (viewer), `templates/` (page templates), `scripts/build_*.py` (generators, helpers in `scripts/_*.py`), `periods/` `polygons/` `pois/` (cache-busted data bundles).

## Acknowledgments

- Data: [Dubai Land Department](https://dubailand.gov.ae/) and [Dubai Pulse](https://data.dubai/) open data, [KHDA](https://web.khda.gov.ae/)
- Map data: [OpenStreetMap](https://www.openstreetmap.org/) contributors
- Libraries: [Leaflet](https://leafletjs.com/), [Chart.js](https://www.chartjs.org/)
