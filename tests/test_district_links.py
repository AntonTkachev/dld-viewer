"""Links to district pages only point at pages that get built."""
import json

import build_poi_pages
from _district_html import build_mode_switcher


def test_mode_switcher_both_modes():
    html = build_mode_switcher('business-bay', 'sale', 'en')
    assert html.count('<a ') == 2 and '/sales/business-bay/' in html and '/rents/business-bay/' in html


def test_mode_switcher_drops_missing_mode():
    html = build_mode_switcher('al-marmoom', 'rent', 'en', has_other=False)
    assert html.count('<a ') == 1 and '/rents/al-marmoom/' in html and 'class="active"' in html


def test_poi_district_pages_follow_aggregates(tmp_path, monkeypatch):
    (tmp_path / 'sale.json').write_text(json.dumps({'marsa dubai': {'name': 'Dubai Marina'}, '__dubai__': {'name': 'Dubai'}}))
    (tmp_path / 'rent.json').write_text(json.dumps({'marsa dubai': {'name': 'Dubai Marina'}, 'al marmoom': {'name': 'Al Marmoom'}}))
    monkeypatch.setattr(build_poi_pages, 'AGG_DIR', str(tmp_path))
    pages = build_poi_pages._district_pages()
    assert pages == {'marsa dubai': ('Dubai Marina', 'dubai-marina', 'sale'), 'al marmoom': ('Al Marmoom', 'al-marmoom', 'rent')}
    link = build_poi_pages.build_district_link('en', {'name': 'Al Marmoom', 'slug': 'al-marmoom', 'mode': 'rent'})
    assert '/en/rents/al-marmoom/' in link


def test_poi_locator_prefers_smallest_polygon():
    sq = lambda x0, y0, s: {'type': 'Polygon', 'coordinates': [[[x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s], [x0, y0]]]}
    feats = [{'properties': {'key': 'parent'}, 'geometry': sq(0, 0, 10)}, {'properties': {'key': 'child'}, 'geometry': sq(2, 2, 2)}]
    pages = {'parent': ('Parent', 'parent', 'sale'), 'child': ('Child', 'child', 'sale')}
    locate = build_poi_pages._build_district_locator(feats, pages)
    assert locate(3, 3)['key'] == 'child' and locate(8, 8)['key'] == 'parent' and locate(20, 20) is None
