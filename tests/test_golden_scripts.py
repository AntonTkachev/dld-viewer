"""Wraps the standalone golden/regression scripts (unchanged) so pytest reports them too.
Each runs against its own checkout: DLD_DATA_ROOT/scripts/<name>.py (default: this repo)."""
import os
import subprocess
import sys

import pytest

from conftest import DATA_ROOT

CASES = [
    ('validate_script_tags.py', ['template.html'], False),
    ('test_masks.py', ['index.html', 'periods/all.js'], False),
    ('test_buildings_match.py', ['data/buildings_geo.json'], True),
    ('test_building_pages.py', ['buildings/search-index.json', 'en/buildings/index.html', 'sitemap.xml'], True),
]


@pytest.mark.parametrize('script,needs,is_data', CASES, ids=[c[0] for c in CASES])
def test_golden_script(script, needs, is_data, request):
    if is_data:
        request.applymarker(pytest.mark.data)
    missing = [n for n in needs if not os.path.exists(os.path.join(DATA_ROOT, n))]
    if missing:
        pytest.skip(f'{script}: missing {missing} (generated output; set DLD_DATA_ROOT)')
    p = subprocess.run([sys.executable, os.path.join(DATA_ROOT, 'scripts', script)],
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, (p.stdout + p.stderr)[-4000:]
