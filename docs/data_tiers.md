# Data tiers

Two-tier model: **free** (forever-public, indexed by Google for SEO) and
**premium** (gated behind auth after launch). Today everyone sees both; the
split exists so future gating is one server-side line, not a 20K-page rebuild.

## Free tier — never lock down

These fields drive SEO. They appear in inline HTML (`AGGREGATES`,
`RENT_AGGREGATES`, etc.) AND in `data.json`. Removing them would tank our
organic traffic.

Per-district sale/rent aggregates:

- `name`, `n`, `total`
- Distribution: `med`, `mean`, `p25`, `p75`, `p90`
- `med_sqm`, `med_ppsqm`, `avg_per_day`
- Property-type splits: `flat`, `villa`, `commercial`, `land` (each carries its
  own n/total/median/percentile block — same shape, smaller)
- `rooms_flat`, `rooms_villa` — counts by room mix
- `offplan` — `{Ready: N, Off-Plan: N}`
- `timeline` — monthly `{d, n, med, vol, ppsqm}` since DLD started publishing
- `by_rooms_unit` — per-room aggregate medians
- `trend_pct`

POI categories (`SCHOOLS`, `UNIVERSITIES`, `MEDICAL`, `MOSQUES`, `MALLS`,
`PROJECTS`, `METRO_STATIONS`) are all free — they're open data or OSM mirrors,
no commercial value in restricting them.

## Premium tier — gate after launch

Defined in `scripts/build_district_pages.py:PREMIUM_FIELDS`. Emitted into a
parallel `<mode>_premium` block under `data.json`:

```json
{
  "sales": { /* free fields */ },
  "sales_premium": {
    "top_deals":  [...],
    "recent":     [...],
    "top_projects": [...],
    "timeline_by_rooms": {...}
  }
}
```

Rationale per field:

- **`top_deals`** — 10 largest transactions per district with project name,
  date, value. Transaction-level info competitors paywall.
- **`recent`** — 20 most-recent transactions. Freshness is a premium signal.
- **`top_projects`** — top 10 projects per district with volume + median.
  Project-level breakdown is market-intel competitors paywall.
- **`timeline_by_rooms`** — monthly timeline split by 7 room types. Very
  granular, very valuable, not needed for SEO.

In the HTML, premium sections carry `data-tier="premium"` on the `<details>`
element. The renderer treats missing premium fields as "no data" and quietly
hides the section — so when the gate strips `*_premium` from `data.json` for
unauthorized users, the UI degrades gracefully.

## How the gate will work (post-launch)

1. Move from GH Pages to Cloudflare Pages.
2. Cloudflare Worker intercepts `/.../data.json` requests:
   - No / invalid API key → strip `*_premium` keys from the JSON, return rest.
   - Valid key → pass through unchanged.
3. Cache the unauth version at the edge; pass-through with bypass for auth.
4. Add a small login UI in the page chrome — sets the API key in
   `localStorage`, the page reload sends it as a header.

No rebuild of 20K pages needed. No reshape of `data.json`. The split is
already shipped today — just connect the gate later.

## When adding new aggregate fields

Decide tier at design time, not at gate time. Ask:

1. **Is it a SEO signal?** Would removing it hurt our ranking for the page?
   → free.
2. **Is it individual transaction / project / building grain?** → premium.
3. **Is it derivable from other free fields?** → free (no point gating it).
4. **Is it freshness-sensitive?** → premium (freshness is paid).

If still unsure, lean **premium**. It's cheap to downgrade later; expensive
(reputation, SEO penalty for content removal) to restrict something that was
public.

## Anti-pattern: don't half-gate

Either fully strip the field from `data.json`, or send it whole. Sending
"degraded" data (rounded values, sampled subsets) is technically possible but
loses the trust signal of free-tier accuracy. Keep the split binary: present
or absent.
