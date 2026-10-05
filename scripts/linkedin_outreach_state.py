#!/usr/bin/env python3
"""Pacing/bookkeeping for the linkedin-outreach skill.

LinkedIn has no anonymous search API (unlike Reddit's search.rss) — scanning
and posting both happen through claude-in-chrome driving the user's real,
logged-in browser. This script only tracks what was already posted, so the
"max 1 dxbcompass.com link per day" and "max 3 comments per run" rules in
.claude/skills/linkedin-outreach/SKILL.md can be enforced across runs, not
just within a single conversation.

State lives in data/.linkedin_outreach/replied.json (gitignored):
  [{"url": ..., "had_link": bool, "date": iso8601,
    "post_reactions_at_post_time": int|null,
    "post_comments_at_post_time": int|null,
    "checkins": [{"date": iso8601, "views": int, "reactions": int}, ...]},
   ...]

The post_reactions/post_comments/checkins fields exist to test a hypothesis
raised 2026-10-05: does a post's own popularity (reactions/comments) predict
how many views our comment gets? A manual spot-check of 7 comments that day
was too small and noisy to tell (a post with ~0 of its own reactions got 29
views on our comment; an 82-reaction post got 28) — see --engagement-report.
Don't encode a selection rule from this until there's enough logged data to
actually see a pattern (rough bar: 20-30 check-ins). Until then this is pure
bookkeeping, not a filter.

Step timing lives in data/.linkedin_outreach/timing.jsonl (gitignored, one
JSON object per line: {"ts": iso8601, "label": "..."}). This exists because
the 2026-09-30 run got asked "why did 3 comments take 30 minutes" and had no
real answer — every prior claim about where time went was a guess, since
nothing was actually timestamped. Call --log-step at each step boundary
during a run (see .claude/skills/linkedin-outreach/SKILL.md Step 6) so
--timing-report gives real deltas next time, not another guess.

Usage:
  python3 scripts/linkedin_outreach_state.py --report
  python3 scripts/linkedin_outreach_state.py --mark-replied <url> <true|false> \
      [--post-reactions N] [--post-comments N]
  python3 scripts/linkedin_outreach_state.py --log-engagement <url> <views> <reactions>
  python3 scripts/linkedin_outreach_state.py --engagement-report
  python3 scripts/linkedin_outreach_state.py --log-step <label>
  python3 scripts/linkedin_outreach_state.py --timing-report
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(ROOT, 'data', '.linkedin_outreach')
REPLIED_PATH = os.path.join(STATE_DIR, 'replied.json')
TIMING_PATH = os.path.join(STATE_DIR, 'timing.jsonl')


def _load():
    if os.path.exists(REPLIED_PATH):
        with open(REPLIED_PATH, encoding='utf-8') as f:
            return json.load(f)
    return []


def _save(data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(REPLIED_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def report():
    replied = _load()
    now = datetime.now(timezone.utc)
    for window_hours, label in ((24, 'Last 24h'), (168, 'Last 7 days')):
        cutoff = now - timedelta(hours=window_hours)
        in_window = [r for r in replied if datetime.fromisoformat(r['date']) >= cutoff]
        links = [r for r in in_window if r.get('had_link')]
        print('{}: {} comment(s) total, {} with a dxbcompass.com link'.format(
            label, len(in_window), len(links)))
        for r in links:
            print('  - {} ({})'.format(r['url'], r['date']))


def mark_replied(url, had_link, post_reactions=None, post_comments=None):
    replied = _load()
    replied.append({
        'url': url,
        'had_link': had_link,
        'date': datetime.now(timezone.utc).isoformat(),
        'post_reactions_at_post_time': post_reactions,
        'post_comments_at_post_time': post_comments,
        'checkins': [],
    })
    _save(replied)
    extra = ''
    if post_reactions is not None or post_comments is not None:
        extra = ' (post had {} reactions, {} comments)'.format(
            post_reactions if post_reactions is not None else '?',
            post_comments if post_comments is not None else '?')
    print('logged reply to {} (link={}){}'.format(url, had_link, extra))


def log_engagement(url, views, reactions):
    replied = _load()
    matches = [r for r in replied if r['url'] == url]
    if not matches:
        print('No --mark-replied entry found for {} — log that first.'.format(url))
        return
    entry = matches[-1]  # most recent, in case the same url was ever replied to twice
    entry.setdefault('checkins', []).append({
        'date': datetime.now(timezone.utc).isoformat(),
        'views': views,
        'reactions': reactions,
    })
    _save(replied)
    print('logged check-in for {}: {} views, {} reactions'.format(url, views, reactions))


def engagement_report():
    replied = _load()
    if not replied:
        print('No replies logged yet.')
        return
    print('{:<28} {:>9} {:>9} {:>9} {:>9} {:>6}'.format(
        'posted', 'post_rxn', 'post_cmt', 'our_views', 'our_rxn', 'link'))
    for r in replied:
        checkins = r.get('checkins') or []
        latest = checkins[-1] if checkins else {}
        print('{:<28} {:>9} {:>9} {:>9} {:>9} {:>6}  {}'.format(
            r['date'][:19],
            r.get('post_reactions_at_post_time', '?'),
            r.get('post_comments_at_post_time', '?'),
            latest.get('views', '-'),
            latest.get('reactions', '-'),
            'yes' if r.get('had_link') else 'no',
            r['url'],
        ))
    n_with_checkin = sum(1 for r in replied if r.get('checkins'))
    print('\n{} of {} comments have at least one check-in logged.'.format(n_with_checkin, len(replied)))
    if n_with_checkin < 20:
        print('Below the ~20-30 check-in bar needed before drawing conclusions '
              'about whether post popularity predicts comment views — keep logging.')


def log_step(label):
    os.makedirs(STATE_DIR, exist_ok=True)
    entry = {'ts': datetime.now(timezone.utc).isoformat(), 'label': label}
    with open(TIMING_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print('[{}] {}'.format(entry['ts'], label))


def timing_report():
    if not os.path.exists(TIMING_PATH):
        print('No timing log yet — nothing has called --log-step.')
        return
    with open(TIMING_PATH, encoding='utf-8') as f:
        lines = [json.loads(line) for line in f if line.strip()]
    if not lines:
        print('Timing log is empty.')
        return
    # A run is everything since the last "run_start" label (or the whole
    # file, if no run_start was ever logged).
    run_start_idxs = [i for i, e in enumerate(lines) if e['label'] == 'run_start']
    run = lines[run_start_idxs[-1]:] if run_start_idxs else lines
    print('Steps in most recent run ({} entries):'.format(len(run)))
    prev_ts = None
    total_start = datetime.fromisoformat(run[0]['ts'])
    for entry in run:
        ts = datetime.fromisoformat(entry['ts'])
        delta = '' if prev_ts is None else '  (+{:.0f}s)'.format((ts - prev_ts).total_seconds())
        print('  {}  {}{}'.format(entry['ts'], entry['label'], delta))
        prev_ts = ts
    total = (prev_ts - total_start).total_seconds()
    print('Total: {:.0f}s ({:.1f} min)'.format(total, total / 60))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', action='store_true')
    parser.add_argument('--mark-replied', nargs=2, metavar=('URL', 'HAD_LINK'))
    parser.add_argument('--post-reactions', type=int, metavar='N',
                         help='Post\'s own reaction count at the time we commented (with --mark-replied).')
    parser.add_argument('--post-comments', type=int, metavar='N',
                         help='Post\'s own comment count at the time we commented (with --mark-replied).')
    parser.add_argument('--log-engagement', nargs=3, metavar=('URL', 'VIEWS', 'REACTIONS'))
    parser.add_argument('--engagement-report', action='store_true')
    parser.add_argument('--log-step', metavar='LABEL')
    parser.add_argument('--timing-report', action='store_true')
    args = parser.parse_args()

    if args.report:
        report()
    elif args.mark_replied:
        url, had_link = args.mark_replied
        mark_replied(url, had_link.strip().lower() in ('true', '1', 'yes'),
                     post_reactions=args.post_reactions, post_comments=args.post_comments)
    elif args.log_engagement:
        url, views, reactions = args.log_engagement
        log_engagement(url, int(views), int(reactions))
    elif args.engagement_report:
        engagement_report()
    elif args.log_step:
        log_step(args.log_step)
    elif args.timing_report:
        timing_report()
    else:
        parser.print_help()
