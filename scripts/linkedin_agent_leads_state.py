#!/usr/bin/env python3
"""Bookkeeping for the linkedin-agent-leads skill.

Finds Dubai real-estate agents on LinkedIn for later manual outreach about
dxbcompass.com, excluding agents at agencies that already run their own
competing DLD-data tool (see data/competitor_agencies.json). This script
does not touch LinkedIn or the browser at all — it only tracks what's
already been found, so repeat runs surface new agents instead of the same
ones, and prints the lead table.

State lives in data/.linkedin_agent_leads/leads.json (gitignored):
  [{"name": ..., "title": ..., "company": ..., "url": ...,
    "last_activity": "<free text as seen on profile, e.g. '2 weeks ago'>",
    "found_date": iso8601, "contacted": bool, "contacted_date": iso8601|null},
   ...]

Dedup key is the profile url. The competitor exclusion list
(data/competitor_agencies.json, tracked in git — curated, not runtime state)
is matched by substring against match_keywords, case-insensitive. Keep that
file updated as new competitor tools are discovered; this script doesn't
infer that part, it just checks against a list a human/Claude maintains.

Usage:
  python3 scripts/linkedin_agent_leads_state.py --check-competitor "<company name>"
  python3 scripts/linkedin_agent_leads_state.py --list-competitors
  python3 scripts/linkedin_agent_leads_state.py --add-lead --name N --title T \
      --company C --url U [--last-activity "2 weeks ago"]
  python3 scripts/linkedin_agent_leads_state.py --report [--uncontacted-only]
  python3 scripts/linkedin_agent_leads_state.py --mark-contacted <url>
"""
import argparse
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, 'data', '.linkedin_agent_leads')
LEADS_PATH = os.path.join(STATE_DIR, 'leads.json')
COMPETITORS_PATH = os.path.join(ROOT, 'data', 'competitor_agencies.json')


def _load_leads():
    if os.path.exists(LEADS_PATH):
        with open(LEADS_PATH, encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_leads(data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LEADS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_competitors():
    with open(COMPETITORS_PATH, encoding='utf-8') as f:
        return json.load(f)


def check_competitor(company):
    company_lower = company.lower()
    for entry in _load_competitors():
        for kw in entry['match_keywords']:
            if kw.lower() in company_lower:
                print('MATCH: "{}" -> {} ({}, {})'.format(
                    company, entry['company'], entry['tool_name'], entry['tool_url']))
                return entry
    print('no match — not a known competitor-owned agency')
    return None


def list_competitors():
    for entry in _load_competitors():
        print('{} -> {} ({})'.format(entry['company'], entry['tool_name'], entry['tool_url']))
        print('  keywords: {}'.format(', '.join(entry['match_keywords'])))
        print('  source: {}'.format(entry['source']))


def add_lead(name, title, company, url, last_activity=None):
    leads = _load_leads()
    if any(l['url'] == url for l in leads):
        print('already have a lead for {} — skipped'.format(url))
        return
    match = None
    for entry in _load_competitors():
        if any(kw.lower() in company.lower() for kw in entry['match_keywords']):
            match = entry
            break
    if match:
        print('REFUSED: {} is at {}, which already has {} ({}) — not adding'.format(
            name, match['company'], match['tool_name'], match['tool_url']))
        return
    leads.append({
        'name': name,
        'title': title,
        'company': company,
        'url': url,
        'last_activity': last_activity,
        'found_date': datetime.now(timezone.utc).isoformat(),
        'contacted': False,
        'contacted_date': None,
    })
    _save_leads(leads)
    print('added lead: {} ({}, {})'.format(name, title, company))


def report(uncontacted_only=False):
    leads = _load_leads()
    if uncontacted_only:
        leads = [l for l in leads if not l.get('contacted')]
    if not leads:
        print('No leads logged yet.')
        return
    print('| Name | Title | Company | Last activity | Contacted | URL |')
    print('|---|---|---|---|---|---|')
    for l in leads:
        print('| {} | {} | {} | {} | {} | {} |'.format(
            l['name'], l['title'], l['company'], l.get('last_activity') or '?',
            'yes' if l.get('contacted') else 'no', l['url']))
    n_contacted = sum(1 for l in leads if l.get('contacted'))
    print('\n{} lead(s) total, {} already contacted.'.format(len(leads), n_contacted))


def mark_contacted(url):
    leads = _load_leads()
    matches = [l for l in leads if l['url'] == url]
    if not matches:
        print('No lead found for {} — add it first with --add-lead.'.format(url))
        return
    matches[-1]['contacted'] = True
    matches[-1]['contacted_date'] = datetime.now(timezone.utc).isoformat()
    _save_leads(leads)
    print('marked {} as contacted'.format(url))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-competitor', metavar='COMPANY')
    parser.add_argument('--list-competitors', action='store_true')
    parser.add_argument('--add-lead', action='store_true')
    parser.add_argument('--name')
    parser.add_argument('--title')
    parser.add_argument('--company')
    parser.add_argument('--url')
    parser.add_argument('--last-activity')
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--uncontacted-only', action='store_true')
    parser.add_argument('--mark-contacted', metavar='URL')
    args = parser.parse_args()

    if args.check_competitor:
        check_competitor(args.check_competitor)
    elif args.list_competitors:
        list_competitors()
    elif args.add_lead:
        if not (args.name and args.title and args.company and args.url):
            parser.error('--add-lead requires --name --title --company --url')
        add_lead(args.name, args.title, args.company, args.url, args.last_activity)
    elif args.report:
        report(uncontacted_only=args.uncontacted_only)
    elif args.mark_contacted:
        mark_contacted(args.mark_contacted)
    else:
        parser.print_help()
