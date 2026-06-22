#!/usr/bin/env python3
"""Delete old root-level Russian index.html files after the /ru/-prefix migration.

Before the migration, Russian pages lived at /sales/, /rents/, /faq/,
/sales/<slug>/, /sales/<slug>/<period>/ etc. After moving everything under
/ru/, the OLD paths still have stale Russian index.html files alongside
the data.json shared-asset files. This script walks the OLD top-level dirs
and deletes only the index.html files where a /ru/<same-path>/index.html
counterpart now exists. data.json and other files are preserved (they are
language-neutral assets fetched by all locales).

Idempotent: re-running is safe; missing files are silently skipped.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Top-level dirs that previously held Russian pages at the root.
OLD_RU_TOPS = (
    'sales', 'rents', 'growth', 'payback', 'lifecycle', 'faq',
    'metro', 'schools', 'universities', 'medical', 'mosques',
    'construction', 'malls',
)


def main():
    deleted = 0
    kept = 0
    skipped_no_ru = 0
    for top in OLD_RU_TOPS:
        top_dir = os.path.join(ROOT, top)
        if not os.path.isdir(top_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(top_dir):
            if 'index.html' not in filenames:
                continue
            rel = os.path.relpath(dirpath, ROOT)
            ru_counterpart = os.path.join(ROOT, 'ru', rel, 'index.html')
            old_index = os.path.join(dirpath, 'index.html')
            if os.path.isfile(ru_counterpart):
                os.remove(old_index)
                deleted += 1
            else:
                # No /ru/ version exists yet — leave the file (might be an
                # old page the new builders no longer produce; safer to
                # leave and have it 404 later via cleanup than delete and
                # lose content)
                kept += 1
                skipped_no_ru += 1

    print(f'deleted: {deleted}', file=sys.stderr)
    print(f'kept (no /ru/ counterpart): {kept}', file=sys.stderr)

    # Sanity: report what data.json files survived in each old dir.
    surviving_data = 0
    for top in OLD_RU_TOPS:
        for dirpath, _, filenames in os.walk(os.path.join(ROOT, top)):
            if 'data.json' in filenames:
                surviving_data += 1
    print(f'data.json files preserved (language-neutral assets): {surviving_data}', file=sys.stderr)


if __name__ == '__main__':
    main()
