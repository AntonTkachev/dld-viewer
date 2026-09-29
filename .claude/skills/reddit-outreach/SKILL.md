---
name: reddit-outreach
description: Find Reddit threads in r/dubairealestate (and r/dubai) where real DLD/Ejari data from this project would genuinely help — then draft data-grounded replies for the user to review and approve one by one. Use when the user asks to run the Reddit outreach / Reddit scan / "find Reddit posts to reply to" for dxbcompass.com. Never invoke on a schedule or without the user explicitly asking for this run.
---

# Reddit outreach for dxbcompass.com

Goal: find Reddit posts where people are asking genuine questions about Dubai
property ROI / rent / yield — the exact thing our DLD+Ejari data answers well
— and help them with real numbers, mentioning dxbcompass.com where it's
actually useful. This is growth-by-being-genuinely-helpful, not link
spamming. Treat every rule below as load-bearing, not a suggestion.

## Non-negotiable rules

1. **Never post anything without the user's explicit per-item approval in
   this conversation.** Not "approve all 5" — each draft gets shown, each
   gets its own yes/no/edit. Posting a comment is an irreversible public
   action; treat it exactly like the "explicit permission required" actions
   it is.
2. **Never fabricate a number.** Every figure in a draft must come from
   `data/tx.parquet` / `data/rents.parquet` (query with DuckDB) or an
   already-published page (`blog/best-payback-1br-2026/`, a `sales/<slug>/`
   or `rents/<slug>/` district page, `faq/`). If the data can't support a
   confident answer, say less, don't guess.
3. **Never accuse a named broker/agency of lying.** Frame it as "here's what
   DLD's registered data shows" — factual, not adversarial. Quora/Reddit
   readers connect the dots themselves.
4. **Disclose affiliation whenever you link dxbcompass.com** — one line like
   "(I built this — free DLD/Ejari explorer, no login)". Undisclosed
   affiliate-style links are exactly what gets accounts shadow-banned.
5. **No template reuse.** Every reply is written fresh for that specific
   post. Identical phrasing across threads is the #1 bot tell.
6. **Respect the self-promo pacing cap**: no more than **2 replies that
   include a dxbcompass.com link, per subreddit, per rolling 7 days**. Check
   this with `--report` before drafting (see Step 3). Over the cap → either
   draft a reply with real numbers and no link, or skip and just tell the
   user what you found.
7. **Cap this run at 3 posted replies total**, however many good candidates
   turn up. Human accounts don't reply to 8 threads in one sitting.

## Step 0 — how posting works here (read this, don't re-litigate it)

`claude-in-chrome` refuses to navigate to reddit.com at all — this is a hard
restriction in the tool itself, not a per-session permission to request or a
risk call to re-evaluate. Do not attempt to drive Reddit's site through
`claude-in-chrome`, and do not write or suggest a separate browser-automation
script (Playwright, Selenium, etc.) to do it instead — that would just be a
different technical path to the same thing the tool already refuses, and
that's not something to build around.

The actual submit click is always the user's own action, done by hand, in
their own already-logged-in browser. What this skill automates is
everything up to that click: finding the post, checking it's worth
answering, grounding the reply in real data, drafting it, and — once
approved — opening the exact tab and loading the exact text into the
clipboard so posting is one paste and one click. See Step 6.

## Step 1 — scan

```bash
python3 scripts/reddit_scan.py
```

Read-only, no auth, ~1-2 minutes (one combined OR-query request per
subreddit, paced to stay under Reddit's anonymous rate limit — looping
per-keyword instead measured at 10+ minutes with mostly 429s, don't revert
to that). Prints new candidate posts as JSON to stdout (title, url, author,
body, matched_query, created_utc). State lives in
`data/.reddit_outreach/seen.json` — already-surfaced posts won't repeat on
the next run, so don't re-run it twice in a row expecting the same list.

## Step 2 — filter for relevance

Drop a candidate if it is:
- A listing/ad ("For Sale", "AED X | community | handover date", "DM for
  details", "Posting as: Agent") — nothing to answer, just noise from the
  keyword match.
- Already asked-and-answered well by existing top comments — check before
  drafting; don't pile on.
- Off-topic (matched a keyword incidentally, e.g. "worth it" about moving
  countries, not property).
- A competitor's own tool/post (e.g. someone sharing their own DLD-data
  side project) — not a target for a reply with our link; feel free to
  mention this to the user as market intel, but skip it.

Keep it if it's a genuine question our data can move the needle on: "is X%
ROI realistic in [area]", "is my rent fair", "which area for yield",
"off-plan vs ready for cash flow", etc.

## Step 3 — check pacing (first time this session)

We can't reliably read a subreddit's rules page headlessly (Reddit's JSON
endpoints 403 anonymous requests, and the HTML page is a client-rendered
shell with nothing in it — confirmed, don't keep trying). Fall back to the
general Reddit self-promotion norm (rule 6, roughly the sitewide "10% of
your activity" guideline) and the pacing cap below. If the user happens to
know a subreddit bans links outright, respect that when they mention it.

Run:

```bash
python3 scripts/reddit_scan.py --report
```

If a subreddit is already at or over 2 link-replies in the last 7 days,
apply rule 6 above.

## Step 4 — ground the answer in real data

Pull real numbers relevant to the post's actual question, e.g.:

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

Prefer linking an existing page over restating numbers from scratch when one
already covers it well: `blog/best-payback-1br-2026/` for yield/payback
questions, `sales/<slug>/` or `rents/<slug>/` for a single district's
price/rent history. Use `dm_to_dld_aliases.json` to map a DLD admin area
name to its public display name/slug before linking.

## Step 5 — draft the reply

Write like a knowledgeable redditor answering a question, not a marketer:
- Answer the actual question first, in the first sentence.
- Real numbers, with the "gross yield, excludes service charges/vacancy"
  caveat when quoting a yield.
- Link only if it adds something the comment text doesn't already say.
- Disclosure line if linking (rule 4).
- Short. Reddit downvotes essay-length self-promotion.

## Step 6 — approval + handoff for posting

Show the user every candidate draft together (numbered list: post title +
url + draft text + which pacing/rule checks applied). This is the one
approval checkpoint — the user reviewing and replying "yes to these" for a
list they've actually seen in full satisfies rule 1, it's not a blind
"approve all 5" for items they haven't read.

Once approved, do the handoff for the whole approved batch in one go —
don't make the user come back to you between each item:

```bash
open "<post url 1>"
open "<post url 2>"
...
```

(`open` just launches each URL in the user's default browser, same as
clicking a link — it does not touch Reddit's page or DOM in any way, so it's
not covered by the Step 0 restriction.) Then print each approved text in the
chat response as its own labeled block ("Tab 1 — <title>: ```...```"), so the
user can select-and-copy directly from the conversation at their own pace
instead of relying on clipboard timing (a single `pbcopy` was tried and
proved awkward for more than one item — it only holds one thing, and the
user's clipboard kept getting overwritten by other activity before they got
to paste it).

Wait for one follow-up message telling you which ones actually got posted
(not a full one-post-at-a-time back-and-forth), then mark each confirmed one:

```bash
python3 scripts/reddit_scan.py --mark-replied "<post_id>" "<subreddit>" "<url>"
```

The rule-7 pacing cap (max 3 per run) is enforced by how many drafts you
bring to Step 6 in the first place, not by making the user check in between
posts.

## Stop conditions

Stop and ask the user rather than guessing when: a post is ambiguous about
whether it wants investment advice or just venting, the subreddit's rules
are unclear about self-promotion, or you've already posted 3 replies this
run.
