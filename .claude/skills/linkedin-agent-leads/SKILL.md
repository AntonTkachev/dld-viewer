---
name: linkedin-agent-leads
description: Find active Dubai real-estate agents on LinkedIn for later manual outreach about dxbcompass.com, excluding anyone at an agency that already runs its own competing DLD-data tool (fam Properties' DXB Interact, Allsopp & Allsopp's data.hub, Driven Properties' Market Guide — see data/competitor_agencies.json). Outputs a lead table only — never drafts or sends LinkedIn messages. Use when the user asks to find/update the agent leads list, or run the LinkedIn agent scan. Never invoke on a schedule or without the user explicitly asking for this run.
---

# LinkedIn agent leads for dxbcompass.com

Goal: build and maintain a list of active Dubai real-estate agents who are
good outreach targets for dxbcompass.com — matching role/location/activity
criteria below, **and** working at an agency that has no in-house DLD data
tool of its own (so dxbcompass.com is a genuine gap-filler for them, not a
redundant pitch). This skill only researches and compiles the list — it
never drafts or sends a connection request / message. That's a separate
step the user does by hand, or a different skill if one gets built later.

This reuses the manual methodology worked out in the first list-building
pass (2026-10-05, found 20 agents, researched competitor tools): targeted
company+title searches beat generic ones, and activity has to be verified
per-profile, not assumed from the headline.

## Non-negotiable rules

1. **Never send a connection request, InMail, or message from this skill.**
   Compiling a public lead list is the only job here. If the user wants to
   actually reach out, that's a separate explicit ask.
2. **Always check the agent's current company against
   `data/competitor_agencies.json`** before adding them as a lead (Step 3).
   A match on any of an entry's `match_keywords` (substring, case-
   insensitive) means skip — don't add them, don't ask the user, just
   exclude and move on. If a company name looks like it *might* be a
   sub-brand/franchise of a listed competitor but isn't an exact
   keyword match (e.g. a new "X by fäm" variant), flag it to the user
   instead of guessing either way.
3. **This exclusion list is a living document, not a one-time snapshot.**
   If, while researching, you find evidence that another agency has quietly
   shipped its own DLD/transaction data tool, add it to
   `data/competitor_agencies.json` (new entry: `company`, `match_keywords`,
   `tool_name`, `tool_url`, `source`, `verified` date, `notes`) before
   continuing — don't just mention it in chat and lose it next run.
4. **Dedup against already-found leads.** Check
   `python3 scripts/linkedin_agent_leads_state.py --report` at the start of
   a run; don't re-surface a profile URL already logged. If an existing
   lead's current company now matches the competitor list (they moved
   employers), say so — don't silently drop them from the file, since the
   user may already have reached out.
5. **Never fabricate an activity date, title, or company.** Only report what
   a profile's own "Все действия" (recent activity) page or main profile
   page actually shows, read directly, not inferred from the search-result
   snippet alone (snippets are frequently stale — see Step 2).
6. **Pace browsing like a human, same as the original scan.** LinkedIn's
   Terms of Service prohibit automated scraping, and the user explicitly
   accepted a "slow, manual-style browsing" risk profile for this kind of
   work (2026-10-05) — not a blanket license to crawl faster. Keep using
   targeted searches + individual profile checks, not bulk/sequential
   scraping of entire result pages. Batch `browser_batch` calls 2-4
   profiles at a time (navigate + screenshot pairs), not more.
7. **No personal data beyond what's needed for outreach**: name, headline
   title, current company, profile URL, and the freeform "last activity"
   text as shown on the page. Don't record email addresses, phone numbers,
   or anything else even if visible on the profile.

## Step 0 — check competitor list and existing leads first

```bash
python3 scripts/linkedin_agent_leads_state.py --list-competitors
python3 scripts/linkedin_agent_leads_state.py --report
```

Know what's already excluded and already found before searching, so you
don't redo work or re-surface the same names.

## Step 1 — search by company + title (not generic keywords)

Generic searches like `Real Estate Agent Dubai` return mostly small/
independent agents and low signal. Targeted `<title> <company> Dubai`
queries against named medium/large agencies work far better — this is what
the first pass confirmed across ~15 company searches.

Use `mcp__claude-in-chrome__tabs_context_mcp` (create a tab if needed), then
for each agency **not already in the competitor list**, search:

```
https://www.linkedin.com/search/results/people/?keywords=<title>%20<company>%20Dubai&origin=GLOBAL_SEARCH
```

Rotate through titles — `Real Estate Agent`, `Property Consultant`,
`Real Estate Broker`, `Off-Plan Specialist` — and agencies. Good agency
candidates (medium/large, not yet excluded): Betterhomes, Metropolitan
Premium Properties, Engel & Völkers Dubai, haus & haus, D&B Properties,
White & Co, Dacha Real Estate, Hamptons International, Provident Estate,
Espace Real Estate, Tanami Properties, Savills Dubai, Knight Frank Dubai —
plus any other medium/large agency the user names. **Skip searches for
fäm Properties, Allsopp & Allsopp, and Driven Properties entirely** — every
agent there is excluded by definition, so don't spend search budget there.

Use `get_page_text` to read results, then `find` (batched — multiple names
in one call) to grab profile URLs for promising candidates: title matches
one of the four, location is Dubai/UAE, company isn't already excluded.

## Step 2 — verify activity per profile (don't trust the snippet)

Search-result snippets can be stale (an agent's headline may say one
company while `recent-activity` shows them at another, or show a reshare
from 8 months ago under a title that looks current). For each candidate:

1. `navigate` to `<profile-url>/recent-activity/all/`.
2. `wait` ~2s, then `screenshot`. If the page shows skeleton/placeholder
   loading blocks instead of content, retry once (navigate again + wait +
   screenshot) before concluding there's nothing there.
3. Read the top post's date. Keep the candidate only if it's within roughly
   the last 1-2 months (LinkedIn shows relative dates: "X дн./нед./мес.").
   A reshare of someone else's content counts as activity, not just
   original posts.
4. "Пока нет контента для отображения" (no content yet) = reject.

Batch 2-4 candidates per `browser_batch` call (navigate+wait+screenshot ×N)
per rule 6.

## Step 3 — exclude by company, then log

For every candidate who passed Step 2, check the company before adding:

```bash
python3 scripts/linkedin_agent_leads_state.py --check-competitor "<company as shown on profile>"
```

If it matches, drop the candidate (rule 2) — don't log them. Otherwise:

```bash
python3 scripts/linkedin_agent_leads_state.py --add-lead \
  --name "<name>" --title "<title as shown>" --company "<company as shown>" \
  --url "<profile url>" --last-activity "<e.g. '3 weeks ago'>"
```

`--add-lead` re-checks the competitor list itself and refuses silently if
there's a match, as a safety net — but do the explicit `--check-competitor`
call first anyway so you report the right reason to the user if a good-
looking candidate gets dropped.

## Step 4 — report

```bash
python3 scripts/linkedin_agent_leads_state.py --report --uncontacted-only
```

Show the user the full current lead table (not just this run's additions,
unless they ask for only the new ones) and call out: how many new leads
this run, how many candidates were found but excluded for being at a
competitor-owned agency (name the agency + tool), and how many were
rejected for stale/no activity.

## Stop conditions

Stop and ask the user rather than guessing when: a company's name looks
like it might be a sub-brand of an already-excluded agency but doesn't
match any `match_keywords` exactly (rule 2/3), LinkedIn shows a CAPTCHA/
unusual-activity challenge (stop everything, tell the user immediately —
do not attempt to solve it), or a run of 4+ company searches turns up no
qualifying candidates and you're unsure whether to keep going or report
back short.
