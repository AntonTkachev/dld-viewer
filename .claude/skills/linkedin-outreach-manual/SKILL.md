---
name: linkedin-outreach-manual
description: Find LinkedIn posts about Dubai real estate (ROI, rental yield, off-plan vs ready, pricing) where real DLD/Ejari data from dxbcompass.com would genuinely help, and draft data-grounded professional replies that the user pastes and posts by hand. Never opens or drives linkedin.com in a browser. This is the default for "LinkedIn outreach / LinkedIn scan / find LinkedIn posts to reply to" — the older browser-automated `linkedin-outreach` skill is kept only for reference and must not be used unless the user names it explicitly. Never invoke on a schedule or without the user explicitly asking for this run.
---

# LinkedIn outreach for dxbcompass.com (manual posting)

Same goal and the same content rules as `.claude/skills/linkedin-outreach/SKILL.md`:
find posts where registered DLD (sales) / Ejari (rent) numbers genuinely add
to the discussion, and answer with real figures, mentioning dxbcompass.com
where it adds value. The difference is mechanical: **Claude never touches
LinkedIn through the user's browser session.** Claude finds and drafts; the
user opens, pastes and posts by hand — the same split as `reddit-outreach`.

## Why this skill exists (don't re-litigate it)

2026-10 the user's LinkedIn account got a temporary restriction (a couple of
days) for "using third-party software". The old skill drove the logged-in
session through the claude-in-chrome extension: 6–9 keyword searches with
~15 scroll ticks each, clipboard tricks to read permalinks, synthetic typing,
and 3 comments submitted within ~5.5 minutes (timing log 2026-10-06). That
is exactly what LinkedIn User Agreement §8.2 prohibits and what its
extension/automation detection looks for.

So in this skill:
- **No `mcp__claude-in-chrome__*` calls on linkedin.com — not for search,
  not for reading posts, not for posting, not for engagement check-ins.**
  Not even "just one quick look". If a step seems to need it, ask the user
  to do that step by hand instead.
- No Playwright/Selenium/AppleScript/JXA substitute either — a different
  technical path to the same automation is the same risk.
- After the restriction, assume the account is under closer scrutiny for a
  while. If the user mentions a new warning, CAPTCHA or restriction, stop the
  run and tell them.

## Non-negotiable rules

1. **Never fabricate or estimate a number.** Every figure comes from a live
   dxbcompass.com page (fetch it, pages update weekly) or a direct DuckDB
   query on `data/tx.parquet` / `data/rents.parquet`. If it can't be
   verified, say less.
2. **Never frame a named broker/developer as lying or scamming.** "Registered
   data shows…" — factual, not adversarial.
3. **Disclose affiliation whenever linking dxbcompass.com** — e.g. "(I built
   this — free tool on registered DLD/Ejari data, no login)".
3a. **Every dxbcompass.com link gets a UTM tag:**
   `?utm_source=linkedin&utm_medium=social&utm_campaign=outreach`.
4. **No template reuse.** Each comment is written fresh for that post.
5. **Style:** professional, first person, no marketing language, no emoji,
   no hashtags, no "Great question!". 2–4 sentences: answer with the real
   number first, then the caveat (gross vs net, service charges, vacancy,
   small sample), then the source / link.
6. **Pacing caps** (persisted via `scripts/linkedin_outreach_state.py`):
   - Max **3 drafts per run**.
   - Max **1 comment with a dxbcompass.com link per rolling 24h** — over
     the cap, draft the reply with real numbers and no link.
   - Tell the user to space their own posting out (e.g. one comment, then
     the next after 15–30+ minutes or later in the day) — three comments in
     a few minutes looks scripted even when a human clicks submit.
7. **Skip anything ambiguous** — venting vs. a genuine question, or where a
   reply would read as unsolicited.
8. **Never post.** The user posts every comment themselves.

## Step 1 — find candidates (without the user's LinkedIn session)

Sources, in order:

1. **Links or pasted text from the user.** If the user brings posts they saw
   in their own feed, those are the best candidates — use them first.
2. **Web search for public LinkedIn posts** with `WebSearch`, e.g.
   `site:linkedin.com/posts "Dubai" "rental yield"`. Rotate through queries
   and put several in one turn:
   `Dubai real estate ROI`, `Dubai rental yield`, `off-plan Dubai`,
   `Dubai property investment 2026`, `UAE property market`,
   `is Dubai real estate still worth it`, `Dubai property ROI realistic`,
   `Dubai service charges yield`, `JVC rental yield` (swap in other areas).
   Use `mode: "extended"` only when standard results are thin or stale.
   Keep only posts from roughly the last 2 weeks — older threads are dead
   and a late comment looks odd.
3. **Read a candidate** with `WebFetch` on its public `linkedin.com/posts/…`
   URL. That's an anonymous server-side fetch, not the user's session. If it
   hits an authwall or returns too little, don't escalate to the browser —
   list the URL to the user as "couldn't read it, open it and paste the text
   if it looks interesting", or drop it.

Expect a low hit rate: LinkedIn's Dubai real-estate content is mostly
broker broadcast and lead-gen. An empty run is a valid result — report it
honestly instead of stretching a marginal post.

Existing comments usually can't be read anonymously. Say so in the handoff
and ask the user to skim the thread before pasting, so they don't repeat a
data point someone already added.

## Step 2 — filter for relevance

**Keep** a post if either:
- It asks a specific question our data answers: "is X% yield realistic in
  [area]", "off-plan vs ready", "how has [area] performed", "fair rent for
  [type] in [area]"; or
- It's an **analytical/data-driven post** that invites discussion, where a
  registered-data figure is a natural addition, not a hijack.

**Drop** a post if it is:
- A listing/ad or lead-gen post ("DM me for the ROI sheet", "send your
  budget", "URGENT SALE").
- Hiring, event promo, or off-topic keyword matches.
- Already answered with the same data point (when visible).
- A competing data tool's own post, or research built on a competing source
  (e.g. Baytify) — mention it to the user as market intel, don't reply.

Rule of thumb: a post ending in "here's what to think about" is fair game.
One ending in "DM/WhatsApp me for the shortlist" is not.

## Step 3 — check pacing

```bash
python3 scripts/linkedin_outreach_state.py --report
```

If the last-24h link count is already ≥1, every draft this run goes without
a link.

## Step 4 — ground the answer in real data

Prefer fetching the matching live page:
- `dxbcompass.com/en/growth/` — median AED/m² growth by district.
- `dxbcompass.com/en/sales/<slug>/`, `dxbcompass.com/en/rents/<slug>/`.
- `dxbcompass.com/en/payback/<slug>/`, `dxbcompass.com/en/blog/best-payback-1br-2026/`.

Otherwise query the parquet directly:

```bash
python3 -c "
import duckdb
con = duckdb.connect()
print(con.execute('''
    SELECT area_name_en, median(CAST(annual_amount AS DOUBLE)) AS med_rent, count(*) n
    FROM read_parquet('data/rents.parquet')
    WHERE ejari_property_type_en = 'Flat'
      AND area_name_en = ?
      AND CAST(contract_start_date AS DATE) >= (CURRENT_DATE - INTERVAL 12 MONTH)
    GROUP BY 1
''', ['<area>']).fetchdf())
"
```

Use `data/dm_to_dld_aliases.json` to map a DLD admin area name to its public
slug before linking.

## Step 5 — draft the reply

Follow rule 5: number first, caveat second, link + disclosure third (only
if linking and under the cap).

## Step 6 — handoff

Show all drafts together, as a numbered list: post URL + author + what they
asked + the draft text + whether it's linked or not.

The user reviews them and may edit. Then, for the approved ones:

```bash
open "<post url 1>"
open "<post url 2>"
```

(`open` launches the URL in the user's default browser, like clicking a link.
It doesn't read or drive the page, so it's allowed under the no-browser rule.)

Print each approved text as its own labeled block ("Tab 1 — <author>:
```...```") so the user can copy them one at a time. Remind them to space
the posts out (rule 6).

Wait for one follow-up message saying which ones actually went up, then log
only those:

```bash
python3 scripts/linkedin_outreach_state.py --mark-replied "<post url>" <true|false> \
    [--post-reactions N] [--post-comments N]
```

`true`/`false` = whether the posted text had a dxbcompass.com link. Pass the
post's reaction/comment counts only if the user tells you them or they were
visible in the WebFetch result. Leave them out rather than guess.

## Step 7 — engagement check-in (only when asked)

Claude can't open the comments any more. When the user asks how past
comments are doing, list the URLs from
`python3 scripts/linkedin_outreach_state.py --engagement-report`. The user
reads the views/reactions under their own comment and sends them back. Log
each one:

```bash
python3 scripts/linkedin_outreach_state.py --log-engagement "<post url>" <views> <reactions>
```

As before, don't turn post popularity into a selection filter until there
are ~20–30 check-ins.

## Stop conditions

Stop and ask instead of guessing when a post is ambiguous (advice vs.
venting), a batch of searches finds nothing and you're unsure whether to keep
going, or the user mentions any new LinkedIn warning or restriction.
