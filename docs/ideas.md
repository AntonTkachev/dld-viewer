# Product ideas — what to build next

Captured from competitive audit (dxbinsight.com / dxbinteract.com, June 2026).
Each idea includes: why, how, expected effort, what data we already have.

---

## 1. Building-level pages (highest ROI — start here)

**What:** `/buildings/<slug>/` pages, one per unique `building_name` in `tx.parquet`.
Each shows the full transaction history for that building:
- price-over-time chart
- per-sqft trend
- recent sales table
- resale-pair view (same unit, two sales — % change)
- summary: total deals, median price, median ppsqm, % resale vs first-sale
- localized in 5 languages (we already do this for districts)

**Why it wins:**
- 5–10K unique pages (estimate from `SELECT COUNT(DISTINCT building_name) FROM tx.parquet`),
  each with organic SEO content nobody else has indexed.
- Long-tail queries (*"burj views tower price history"*, *"23 marina resale 2024"*) —
  dxbinsight catches these behind a paywall (so Google can't index), we'd catch them open.
- Self-validating for users: a buyer can confirm the listing price they're seeing
  matches historical reality for that building.
- Lays the foundation for resale-chain analytics (idea #3).

**Data we already have:**
- `building_name_en`, `building_name_ar` in tx.parquet (also in rents.parquet for rental history)
- `instance_date`, `actual_worth`, `procedure_area`, `rooms`, `usage_en`
- For lat/lng we'd lean on OSM building polygons or building-name → district centroid fallback
  (see idea #2).

**Build plan (~1–2 days):**
1. `scripts/build_building_aggregates.py` — DuckDB scan, group by `(area_name_en, building_name_en)`
   to disambiguate cross-area same-name buildings, emit one JSON per building under
   `buildings/data/<slug>.json`.
2. `templates/building.html` — render template; reuse most of `detail-panel.js`.
3. `scripts/build_building_pages.py` — emit static HTML per building, 5 languages,
   add to sitemap.
4. Cross-link from district pages (*"Buildings in this area: …"*) and from POI pages
   (*"Nearest deals: …"*).

**Risk / unknowns:**
- Naming collisions: «Burj Khalifa» appears under multiple `area_name_en` values in raw data?
  Need to dedupe carefully; probably namespace by area.
- Some buildings have <10 deals — auto-skip pages below threshold to avoid thin content
  penalties from Google.
- Slug collisions across languages; pick canonical slug (probably English-romanized).

---

## 2. Geocoding enrichment per transaction

**What:** for each transaction record (or at least each aggregated district/building/project),
compute and ship `nearest_metro`, `nearest_mall`, `nearest_school`, `nearest_hospital`,
`nearest_park` with distance in meters. Surface in carded UI ("median deal: 850m from
Burj Khalifa station").

**Why it wins:**
- Strongest UX-visible feature dxbinsight has — and they often get it wrong
  (e.g. they label "Jumeirah Beach Residency" as a metro stop; it's a tram).
- Buyer-facing relevance is high: proximity to metro / school is a major decision factor.
- Once computed, also enables filtering and ranking ("show me deals within 500m of metro").

**Data we already have:**
- `data/osm_*.json` — schools, universities, medical, malls, mosques, metro POIs
- POI lat/lng + categories — ready for spatial join
- Building/transaction coordinates we DON'T have, but can approximate via building polygon
  centroid (OSM) or district centroid fallback.

**Build plan (~few hours):**
1. `scripts/build_nearest_pois.py` — for each building (or district centroid),
   compute nearest POI of each category, write to `data/nearest_pois.json`
   keyed by building/area.
2. Patch `build_sale_aggregates.py` / `build_rent_aggregates.py` to join in nearest-POI
   labels into the emitted aggregates.
3. Patch `detail-panel.js` to render the new fields.

**Risk:** without per-transaction coords, the "nearest" is district-level approximation —
needs to be labeled honestly ("near this district" not "near this property").

---

## 3. `is_resale` flag + resale-chain analytics

**What:** boolean per transaction indicating it's a resale (not first sale). Plus
derived "resale chain" — for each property_id, the sequence of all sales over time
with % change between each.

**Why it wins:**
- Trivially computable from existing data: window function over `(property_id, date)`.
- Gives a filter ("first sale only / resale only") that buyers ask for.
- Powers a **unique** view nobody else has in open access: "this exact unit sold for
  4.2M in 2015, 5.1M in 2019, 6.8M in 2023 — +62% over 8 years". This is gold for buyer
  due diligence and would be a strong sharable-on-social moment.
- District-level metric: "% of recent deals that are resales" — proxy for market maturity
  (new launches vs secondary).

**Data we already have:**
- `property_id` in raw DLD CSV — we currently DROP this during dedup; need to keep it.
- `instance_date`, `actual_worth` — already there.
- (Optional) `parcel_id` from Buildings/Land Registry datasets (459613, 465348) as
  fallback when property_id is missing.

**Build plan (~1 day):**
1. Modify `scripts/dld_to_parquet.sh` to keep `property_id` in the parquet output.
2. New script: compute resale chains via `RANK() OVER (PARTITION BY property_id ORDER BY date)`.
3. Emit a `resale_chains/<property_id>.json` shard or embed into building pages.
4. UI: add "show resale history" button on building pages; add "% resale" stat on
   district summary cards.

**Risk:** `property_id` semantics across snapshots — if DLD reassigns IDs we'd compute
wrong chains. Spot-check 100 known resales (e.g. landmark Marina towers) before going wide.

---

## Future / nice-to-have (not prioritized)

- **Project-level pages** (`/projects/marina-pinnacle/`) — uses `project_name_en`, similar
  pattern to building pages but coarser; may overlap with #1 enough to skip.
- **Procedure filter** (mortgage vs cash) — interesting macro signal but niche audience.
- **Search autocomplete** across building+project+district — UX polish, not differentiator.
- **Popular searches widget** on homepage — "feels alive" but low real value.
- **"What's around" panel** — expand #2 from nearest-1 to nearest-N of each category
  within radius.

## What NOT to copy from competitors

- WhatsApp OTP login / paywall / accounts — against our open SEO model.
- Snapshot stat panels — we already have these in detail-panel and district pages.
- Off-plan as a separate page — we already differentiate off-plan vs ready in aggregates;
  splitting into a dedicated page is over-engineering.
- Sort-by / pagination on transaction lists — we don't show raw transaction lists, this
  mechanic doesn't apply.
