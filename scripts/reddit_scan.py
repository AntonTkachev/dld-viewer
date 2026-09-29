#!/usr/bin/env python3
"""Find candidate Reddit posts for data-grounded replies — read-only, no auth.

Uses Reddit's public search.rss (Atom feed), NOT the OAuth Data API: the API
now requires a manually-approved app (Reddit closed self-service registration
in late 2025) and forbids commercial use on the free tier. RSS is a separate,
unauthenticated, ToS-compliant path with its own (tight but workable) rate
limit — confirmed live: ~1 request per 40-60s per IP is fine, faster gets 429.

This script only reads. It never posts, and it has no Reddit credentials.
Posting happens later, one item at a time, with explicit human approval —
see .claude/skills/reddit-outreach/SKILL.md.

State lives in data/.reddit_outreach/ (gitignored):
  seen.json     — post ids already surfaced, so reruns don't repeat them
  replied.json  — post ids we actually replied to (id, subreddit, date, url),
                  used for the self-promo-ratio report

Usage:
  python3 scripts/reddit_scan.py                 # scan configured subs, print new candidates as JSON
  python3 scripts/reddit_scan.py --report         # show reply counts per subreddit, last 7/30 days
  python3 scripts/reddit_scan.py --mark-replied <post_id> <subreddit> <url>
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, 'data', '.reddit_outreach')
SEEN_PATH = os.path.join(STATE_DIR, 'seen.json')
REPLIED_PATH = os.path.join(STATE_DIR, 'replied.json')

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36'
ATOM_NS = '{http://www.w3.org/2005/Atom}'
REQUEST_GAP_SECONDS = 50  # measured live: sustained anonymous search.rss allows ~1 req/45-60s, not less

# (subreddit, [keywords combined into ONE OR query], max_age_hours)
# One request per subreddit, not one per keyword — Reddit's anonymous rate
# limit for search.rss is tight enough (~1 req/45-60s) that per-keyword
# looping made a 2-subreddit scan take 10+ minutes and mostly draw 429s.
# dubairealestate: on-topic, high precision. dubai: broader, noisier — keep
# the query narrow so we don't surface generic non-property posts.
TARGETS = [
    ('dubairealestate', ['ROI', 'rental yield', 'payback', 'overpriced',
                          'guaranteed ROI', 'worth it', 'off-plan', 'good investment'], 72),
    ('dubai', ['rent increase fair', 'overpriced apartment', 'rera rent index'], 72),
]


def _load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _strip_html(raw):
    text = html.unescape(raw or '')
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_search_rss(subreddit, query):
    url = ('https://www.reddit.com/r/{}/search.rss?q={}&restrict_sr=1&sort=new'
           .format(subreddit, urllib.parse.quote(query)))
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                wait = int(e.headers.get('x-ratelimit-reset', 30)) + 2
                print('  ! {} / "{}" -> 429, backing off {}s'.format(subreddit, query, wait), file=sys.stderr)
                time.sleep(wait)
                continue
            print('  ! {} / "{}" -> HTTP {}'.format(subreddit, query, e.code), file=sys.stderr)
            return []
        except urllib.error.URLError as e:
            print('  ! {} / "{}" -> {}'.format(subreddit, query, e), file=sys.stderr)
            return []
    else:
        return []

    root = ET.fromstring(body)
    posts = []
    for entry in root.findall(ATOM_NS + 'entry'):
        post_id = entry.findtext(ATOM_NS + 'id') or ''
        title = entry.findtext(ATOM_NS + 'title') or ''
        link_el = entry.find(ATOM_NS + 'link')
        link = link_el.get('href') if link_el is not None else ''
        author_el = entry.find(ATOM_NS + 'author/' + ATOM_NS + 'name')
        author = author_el.text if author_el is not None else ''
        updated = entry.findtext(ATOM_NS + 'updated') or ''
        content_raw = entry.findtext(ATOM_NS + 'content') or ''
        body_text = _strip_html(content_raw)[:1500]
        posts.append({
            'id': post_id,
            'subreddit': subreddit,
            'title': html.unescape(title),
            'url': link,
            'author': author,
            'created_utc': updated,
            'body': body_text,
        })
    return posts


def _tag_matched_keyword(post, keywords):
    haystack = (post['title'] + ' ' + post['body']).lower()
    for kw in keywords:
        if kw.lower() in haystack:
            return kw
    return 'combined'


def scan():
    seen = _load_json(SEEN_PATH, {})
    now = datetime.now(timezone.utc)
    by_id = {}

    for i, (subreddit, keywords, max_age_hours) in enumerate(TARGETS):
        cutoff = now - timedelta(hours=max_age_hours)
        query = ' OR '.join('"{}"'.format(k) if ' ' in k else k for k in keywords)
        print('scanning r/{} for [{}]...'.format(subreddit, ', '.join(keywords)), file=sys.stderr)
        for post in fetch_search_rss(subreddit, query):
            try:
                created = datetime.fromisoformat(post['created_utc'].replace('Z', '+00:00'))
            except ValueError:
                created = now
            if created < cutoff:
                continue
            post['matched_query'] = _tag_matched_keyword(post, keywords)
            by_id.setdefault(post['id'], post)
        if i < len(TARGETS) - 1:
            time.sleep(REQUEST_GAP_SECONDS)

    new_candidates = [p for pid, p in by_id.items() if pid not in seen]

    today = now.date().isoformat()
    for p in by_id:
        seen[p] = today
    # trim old seen entries so the file doesn't grow forever
    cutoff_date = (now - timedelta(days=30)).date().isoformat()
    seen = {k: v for k, v in seen.items() if v >= cutoff_date}
    _save_json(SEEN_PATH, seen)

    print(json.dumps(new_candidates, ensure_ascii=False, indent=2))
    print('-> {} new candidate(s) out of {} matched'.format(len(new_candidates), len(by_id)), file=sys.stderr)


def report():
    replied = _load_json(REPLIED_PATH, [])
    now = datetime.now(timezone.utc)
    for window_days in (7, 30):
        cutoff = now - timedelta(days=window_days)
        counts = {}
        for r in replied:
            ts = datetime.fromisoformat(r['date'])
            if ts >= cutoff:
                counts[r['subreddit']] = counts.get(r['subreddit'], 0) + 1
        print('Last {} days:'.format(window_days))
        if not counts:
            print('  (no replies logged)')
        for sub, n in sorted(counts.items()):
            print('  r/{}: {} repl{}'.format(sub, n, 'y' if n == 1 else 'ies'))


def mark_replied(post_id, subreddit, url):
    replied = _load_json(REPLIED_PATH, [])
    replied.append({
        'id': post_id,
        'subreddit': subreddit,
        'url': url,
        'date': datetime.now(timezone.utc).isoformat(),
    })
    _save_json(REPLIED_PATH, replied)
    print('logged reply to {} in r/{}'.format(post_id, subreddit))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--mark-replied', nargs=3, metavar=('POST_ID', 'SUBREDDIT', 'URL'))
    args = parser.parse_args()

    if args.report:
        report()
    elif args.mark_replied:
        mark_replied(*args.mark_replied)
    else:
        scan()
