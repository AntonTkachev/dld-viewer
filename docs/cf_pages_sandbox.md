# Cloudflare Pages — private sandbox

A parallel deployment on Cloudflare Pages, gated by Cloudflare Access so
only specific emails can view it. The public GitHub Pages site at
`antontkachev.github.io/dld-viewer/` stays unaffected — same repo, two
deployments.

## Why

- Test CF-specific things (real HTTP security headers via `_headers`,
  Pages Functions / Workers, Bot Fight Mode, Rate Limiting, Turnstile,
  CSP without `unsafe-inline` once we wire nonces) **without** touching
  production SEO traffic.
- Validate the premium-tier gate (see `data_tiers.md`) on a Worker before
  pointing it at real users.
- Anyone scraping the public URL has no idea this sandbox exists.

## One-time setup (done in CF dashboard, ~15 min)

1. **Create a Cloudflare account.** Free. No card required for Pages or
   Access.

2. **Pages → Create project → Connect to Git → select `dld-viewer` repo.**
   - Production branch: `main`
   - Build command: *(leave empty)* — all HTML is pre-built in the repo
   - Build output directory: `/`
   - Environment variables: *(none)*

3. Wait ~1 min for first deploy. URL: `dld-viewer.pages.dev`. Open it —
   should look identical to the GitHub Pages version. `_headers` and
   `_redirects` are picked up automatically.

4. **Zero Trust → Access → Applications → Add application → Self-hosted:**
   - Application name: `DLD viewer sandbox`
   - Session duration: 30 days
   - Application domain: `dld-viewer.pages.dev` (path: leave blank)
   - Identity providers: enable **One-time PIN** (email OTP — no signup
     for the visitor, just types email, gets code).
   - Add policy:
     - Action: Allow
     - Rule: `Emails`, value: `dgenerosg@gmail.com` (add other allowed
       emails as needed)
   - Save.

5. Open `dld-viewer.pages.dev` in an incognito window. Should redirect to
   the Access login page. Enter the allowed email, get an OTP, log in.
   Bots, crawlers, anyone without auth — blocked at the edge.

## What's now testable on the sandbox

- **HTTP security headers** (`_headers`) — real ones, much stronger than
  the `<meta http-equiv>` CSP on GH Pages. Inspect with browser DevTools
  or `curl -I`.
- **Pages Functions / Workers** — drop a TypeScript/JS file in
  `functions/api/...` and it deploys as a Worker route. Free up to 100K
  requests/day. This is where the premium gate will live.
- **Per-deploy preview URLs** — every push to a non-`main` branch creates
  a separate URL (`<commit>.dld-viewer.pages.dev`) for testing a single
  PR in isolation.

## What's NOT testable on the gated sandbox

Cloudflare Access blocks requests **before** Bot Fight Mode and Rate
Limiting evaluate. So:

- **Bot Fight Mode** — needs an unauthenticated environment to fire.
- **Rate Limiting Rules** — same.
- **Turnstile** — works behind Access, but the user is already
  authenticated, so the test isn't realistic.

To test these, the right move is a **second** CF Pages project with no
Access policy, deployed under a non-discoverable subdomain. Don't link to
it from anywhere, don't add it to `sitemap.xml`. Probe it with `curl`,
`puppeteer`, etc. to see what CF blocks.

## File checklist (in this repo)

- `_headers` — HTTP security headers for CF Pages responses. GH Pages
  ignores this file.
- `_redirects` — currently empty; will hold Worker routes when the
  premium gate lands.
- `_config.yml` — GH Pages exclude list. Already in place; CF Pages
  ignores this file.

So both deploys read from the same repo, each picks up only what it
understands, neither interferes with the other.
