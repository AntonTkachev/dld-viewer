---
name: linkedin-outreach
description: Find LinkedIn posts about Dubai real estate (ROI, rental yield, off-plan vs ready, pricing) where real DLD/Ejari data from dxbcompass.com would genuinely help — draft data-grounded professional replies, then post them via claude-in-chrome browser automation. Use when the user asks to run the LinkedIn outreach / LinkedIn scan / "find LinkedIn posts to reply to" for dxbcompass.com. Runs under the user's real LinkedIn identity — never invoke on a schedule or without the user explicitly asking for this run.
---

# LinkedIn outreach for dxbcompass.com

Goal: find LinkedIn posts where people ask genuine, answerable questions about
Dubai property ROI / rental yield / pricing, and answer with real numbers
from registered DLD (sales) and Ejari (rent contract) data, mentioning
dxbcompass.com where it adds value. Growth-by-being-genuinely-helpful, not
link spam. This runs under the user's **real LinkedIn identity** — reputation
matters more than volume, and treat every rule below as load-bearing.

This is the LinkedIn sibling of `reddit-outreach` (`.claude/skills/reddit-outreach/SKILL.md`)
but the mechanics differ in one important way — see Step 0.

## Non-negotiable rules

1. **Never fabricate or estimate a number.** Every figure must come from a
   live dxbcompass.com page (fetch it, don't recall it from memory — pages
   update weekly) or a direct DuckDB query against `data/tx.parquet` /
   `data/rents.parquet`. If the site doesn't have the number and it can't be
   verified from a primary source, say less — don't guess.
2. **Never frame anything as a named broker/developer lying or scamming.**
   Frame it as "registered data shows" — factual, not adversarial.
3. **Disclose affiliation plainly whenever linking dxbcompass.com** — a line
   like "(I built this — free tool on registered DLD/Ejari data, no login)".
   Never post the link without that disclosure.
3a. **Every dxbcompass.com link gets a UTM tag** — append
   `?utm_source=linkedin&utm_medium=social&utm_campaign=outreach` to the URL
   (e.g. `dxbcompass.com/en/growth?utm_source=linkedin&utm_medium=social&utm_campaign=outreach`).
   GA4 was showing this traffic as unattributed `(direct)` with no way to
   tell it apart from organic visits — confirmed 2026-10-02. Without the tag
   there is no way to measure whether a comment actually drove traffic.
4. **No template reuse.** Every comment is written fresh for that specific
   post — identical phrasing across posts is the fastest way to look like a
   bot on a professional network, more so than on Reddit.
5. **Style**: professional, first person, no marketing language, no emoji
   spam, no hashtags in the comment itself. 2–4 sentences: answer the actual
   question first with the real number, then the caveat (e.g. "gross yield,
   before service charges and vacancy"), then the source.
6. **Pacing caps** (persisted across runs via `linkedin_outreach_state.py`,
   not just within one run):
   - Max **3 comments total per run**.
   - Max **1 comment with a dxbcompass.com link per rolling 24h**. Check with
     `--report` before drafting (Step 3). Over the cap → for otherwise-good
     candidates, draft a reply with real numbers and **no link** instead of
     skipping them outright.
7. **Skip anything ambiguous** — venting vs. a genuine investment question,
   or a post where a reply might read as unsolicited/off-topic — rather than
   guessing.
8. **Never post without the user having seen the exact draft text in this
   conversation first.** The user granted blanket "full autonomy to post, no
   per-item approval" for this workflow (2026-09-30) — but flagged separately
   and *not yet resolved*: LinkedIn actively detects and can restrict accounts
   for automated posting behavior, a risk independent of comment quality,
   and higher-stakes here than on Reddit because this is a real professional
   identity. Until the user explicitly confirms they accept that risk (the
   way Reddit's auto-poster was explicitly approved — see that skill's Step
   0), show the full batch of drafts and get one "yes, post these" before
   Step 6 runs. Once they confirm, remove this line and Step 6's approval
   gate, the same way Reddit's skill documents its own approval history.

## Step 0 — how this differs from reddit-outreach

`claude-in-chrome` refuses to navigate to reddit.com at all, which is why the
Reddit skill drives Chrome via AppleScript/JXA instead. **LinkedIn has no such
restriction** — verified 2026-09-30, `claude-in-chrome` navigates
linkedin.com, reads search results, and can click/type normally. That means
for LinkedIn, scanning *and* posting both go through `claude-in-chrome`
directly against the user's real, already-logged-in session. No separate
automation script is needed for the browser side.

LinkedIn also has no anonymous search API (unlike Reddit's `search.rss`), so
there is no headless `linkedin_scan.py` — Step 1 below is done by driving the
browser tools directly, same as a human would search.

`scripts/linkedin_outreach_state.py` exists only for pacing bookkeeping
(Step 3, Step 6) — it never touches the browser or LinkedIn's network.

**Log step timing as you go — this is not optional.** The 2026-09-30 run
got asked "why did 3 comments take 30 minutes, did you do it slowly on
purpose?" and had no real answer, because nothing was timestamped — every
explanation offered was a plausible-sounding guess. Don't repeat that. At
the very start of a run:

```bash
python3 scripts/linkedin_outreach_state.py --log-step run_start
```

Then call `--log-step <label>` at each boundary below (`scan_done`,
`candidate_found:<author>`, `permalink_copied:<author>`,
`draft_ready:<author>`, `comment_typed:<author>`,
`comment_verified:<author>`, `comment_submitted:<author>`). At the end of
the run:

```bash
python3 scripts/linkedin_outreach_state.py --timing-report
```

and report the real per-step breakdown to the user, not a reconstruction
from memory.

## Step 1 — scan

Use `mcp__claude-in-chrome__tabs_context_mcp` (create a tab if needed), then
for each query navigate to LinkedIn's post-search, sorted by recency:

```
https://www.linkedin.com/search/results/content/?keywords=<url-encoded query>&sortBy=%22date_posted%22
```

**Scroll before reading — don't skip this.** LinkedIn lazy-loads search
results; the page starts with only ~3 posts in the DOM. A first run of this
skill (2026-09-30) called `get_page_text` immediately after navigation and
concluded LinkedIn had nothing, based on 3 posts per query. Scrolling down
~15 ticks (`computer` action `scroll`, direction `down`) before extracting
brought that up to 9+ posts per query — 3x the coverage. Scroll at least
twice per query before calling `get_page_text`.

Also check comment counts on each post (e.g. "1 комментарий" / "N comments")
— click through to expand and read them. A post's own text is often broker
broadcast even when a genuine question is buried in its replies (this is
literally what the task asked for originally: "check comments... often has
genuine questions buried in the replies"). Watch for the difference between
a buyer asking a real question and another broker/agent commenting
professional shop-talk on a colleague's post — the latter isn't a candidate
even though it looks like a question grammatically.

**Grab the permalink the moment a post looks like a plausible candidate —
don't come back for it later.** A 2026-10-01 run fetched 3 permalinks as a
separate pass after drafting was already done, and that alone was ~18
browser round-trips (6 per post) out of the run's total — the single most
expensive part of the whole workflow, more than all the searching and
drafting combined. Do this instead, inline, as soon as a post clears Step 2:

1. Click the post's `•••` menu (top-right of the post card).
   → `--log-step candidate_found:<author>`
2. Click "Скопировать ссылку на публикацию" (Copy link to post) — this
   copies a `https://lnkd.in/p/...` permalink to the clipboard.
3. Click the LinkedIn search box, `triple_click` to select any existing
   text, then `key` `cmd+v` to paste — the pasted URL is now readable via a
   screenshot of the search box. Don't run the query; this is just a
   scratch surface to read clipboard contents back, since there's no direct
   "read clipboard" tool.
4. Record the URL, then either clear the search box or just `navigate` away
   — no need to restore it.
   → `--log-step permalink_copied:<author>`

If a keystroke here comes back denied by the permission classifier, that's
the classifier doing its job — stop and tell the user what you were trying
to do rather than trying another way around it.

Query list (rotate through these; don't stop after one or two — see the
finding below):
`Dubai real estate`, `Dubai property investment`, `Dubai rental yield`,
`off-plan Dubai`, `Dubai ROI`, `UAE property market`,
`Dubai real estate market 2026`, `is Dubai real estate still worth it`,
`Dubai property ROI realistic`.

Also check comments under posts from specific well-known Dubai real estate
commentators/pages, if the user names any — often has genuine questions
buried in the replies that keyword search misses entirely.

**Finding from the 2026-09-30 run, worth knowing before you start:**
LinkedIn's Dubai-real-estate content is dominated by broker/agency broadcast
posts (market-stat carousels, lead-gen "DM me for the ROI sheet" posts) —
not individual buyers asking questions. A run of 6 keyword searches returned
zero genuine candidates, all broker self-promotion. This is a structurally
different environment from Reddit. Budget for more queries than you'd expect
to need, and don't be surprised if a run comes back empty — report that
honestly rather than stretching a marginal post into a "candidate."

## Step 2 — filter for relevance

**Keep** a post if either:
- It's a specific, answerable question our data can move the needle on:
  "is X% yield realistic in [area]", "is off-plan still worth it vs ready",
  "how has [area] performed over N years", "what's a fair rent for
  [property type] in [area]"; OR
- It's an **analytical/data-driven post** (broker or otherwise) where a
  registered-data figure is a natural, additive contribution to the
  discussion already happening — not a hijack. Revised 2026-10-01: the
  "question-only" bar returned zero candidates across 7 searches and 33 post
  reads (2026-09-30/10-01 runs) because LinkedIn's Dubai-real-estate niche
  is fundamentally discussion/thought-leadership, not Q&A — but that same
  scan showed practitioners *do* comment on each other's analytical posts
  with added data points, and it reads as normal, not spammy (e.g. a CRE
  dealmaker adding "we underwrite off actual Ejari comps, not listings" to
  a post about ROI assumptions). Good signal for this bucket: the post
  itself cites real numbers, asks a rhetorical "what does the data actually
  say" question, or explicitly invites pushback/discussion in its own text.

**Drop** a post if it is:
- A pure listing/ad post ("URGENT SALE", unit mix, asking price) or a
  lead-gen post whose entire point is capturing a DM/WhatsApp lead ("DM for
  the ROI sheet", "send me your budget", "Posting as: Agent") — a registered-
  data comment here doesn't fit the post's own frame and reads as random.
- A hiring/recruitment post, event/conference promo, or anything off-topic
  that only matched a keyword incidentally.
- Already well-answered in the comments with the same data point we'd add.
- Another vendor's own data-tool/product post (e.g. a competing Dubai
  property-data startup promoting itself, or a post that cites a competing
  data source like Baytify as its own compiled research) — note this to the
  user as competitive intel, don't reply to it.

The line between "analytical post, fair game" and "ad with analytics-flavored
copy, skip it" is usually the post's own call-to-action: does it end with
"here's what to think about" (discussion) or "DM/WhatsApp me for the
shortlist/sheet" (lead capture)? The former is fine to add a data comment
to; forcing a reply onto the latter is what makes an account look spammy.

## Step 3 — check pacing

```bash
python3 scripts/linkedin_outreach_state.py --report
```

If the last-24h link-comment count is already ≥1, every draft this run that
would otherwise carry a link goes out **without** the link instead (rule 6).

## Step 4 — ground the answer in real data

Prefer fetching the matching live page over restating numbers from memory:
- `dxbcompass.com/en/growth/` — median AED/m² price growth by district
  (1/3/5/10-year windows).
- `dxbcompass.com/en/sales/<area-slug>/` — sale price history for a district.
- `dxbcompass.com/en/rents/<area-slug>/` — rent history for a district.
- `dxbcompass.com/en/payback/<area-slug>/` and
  `dxbcompass.com/en/blog/best-payback-1br-2026/` — rental payback / yield
  rankings.

If the post needs a number not already published, query the source parquet
directly (same pattern as `reddit-outreach` Step 4):

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
display name/slug before linking to a page.

## Step 5 — draft the reply

Follow rule 5 above. Concretely:
- First sentence answers the question with the real number.
- Second: the caveat (gross vs net yield, service charges, vacancy, sample
  size if small).
- Third (only if linking): the dxbcompass.com page + one-line disclosure
  (rule 3).
- No emoji, no hashtags, no "Great question!" filler.

Once a draft is finished for a candidate: `--log-step draft_ready:<author>`.

## Step 6 — approval, then posting

Per rule 8: show the user every candidate draft together (numbered list:
post URL + author + the actual question + draft text + which pacing rule
applied — linked / no-link). Get one explicit go-ahead for the batch before
posting anything.

Once approved, for each item, drive `claude-in-chrome` against the user's
real session (interleave with `--log-step`, see Step 0):
1. `navigate` to the post's URL. → `--log-step candidate_opened:<author>`
2. `find` the comment box, click it.
3. `computer` `type` the approved draft text exactly as shown to the user.
   → `--log-step comment_typed:<author>`
4. Before submitting, re-read the typed text back (screenshot or
   `get_page_text`) and confirm it matches — LinkedIn's comment box is a rich
   text field and can mangle pasted vs typed text.
   → `--log-step comment_verified:<author>`
5. Click the real submit/post button.
6. Confirm the comment landed (it should appear in the thread).
   → `--log-step comment_submitted:<author>`

Log each success:

```bash
python3 scripts/linkedin_outreach_state.py --mark-replied "<post url>" <true|false>
```

(`true`/`false` = whether that comment included a dxbcompass.com link.)

**On pacing between posts**: the original intent was a randomized 20–40s
gap between posts, since three comments landing back-to-back reads as
scripted regardless of platform (LinkedIn's automation detection is
generally considered stricter than Reddit's). In practice, a standalone
`sleep` call is blocked by this environment's sandbox (it flags bare
waits with nothing to check as wasted polling) — confirmed 2026-09-30, don't
re-attempt it or look for a workaround. The natural round-trips of steps
1–6 above (page loads, screenshots, verification reads) already introduce
real but uncontrolled delay between posts; there is currently no reliable
way to add a deliberate pause on top of that within a single run. If this
starts to matter in practice (e.g. LinkedIn flags the account), tell the
user — that's a signal the workflow needs a different mechanism (e.g. a
scheduled follow-up run instead of one run posting all 3 back to back),
not something to solve by forcing a wait.

Report back to the user as each one lands, don't wait for the whole batch:
post URL, the comment text, and which pacing rule applied. If good
candidates were skipped solely due to the daily link cap, say so explicitly.
Close the run with `--timing-report` and share the real numbers.

## Stop conditions

Stop and ask the user rather than guessing when: a post is ambiguous about
whether it wants investment advice or is just venting, a query batch (6+
searches) returns zero genuine candidates and you're unsure whether to keep
searching or report back empty, LinkedIn shows a CAPTCHA/unusual-activity
challenge on the account (stop everything and tell the user immediately —
do not attempt to solve it), or you've already posted 3 comments this run.
