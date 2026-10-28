"""KHDA ↔ OSM school/university name matching stages (CLAUDE.md § KHDA)."""
import pytest

km = pytest.importorskip('khda_merge_into_viewer')
ku = pytest.importorskip('khda_uni_merge_into_viewer')


def khda(*rows, mod=km):
    out = []
    for r in rows:
        r = dict(r) if isinstance(r, dict) else {'name': r}
        r['_toks'], r['_alpha'] = mod.tokens(r['name']), mod.alpha(r['name'])
        out.append(r)
    return out


def square(lon, lat, d=0.01):
    return [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]


def feat(name, ring):
    return {'properties': {'name': name}, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}


# stage 1: exact normalized

@pytest.mark.parametrize('a,b', [
    ('Dubai English Speaking School L.L.C', 'Dubai English Speaking School'),
    ('GEMS Wellington Academy - Branch', 'Gems Wellington Academy'),
    ('Raffles World Academy DWC-LLC', 'raffles world academy'),
    ('The Westminster School, Dubai', 'Westminster School'),
])
def test_norm_key_strips_suffixes_case_punctuation(a, b):
    assert km.norm_key(a) == km.norm_key(b)


def test_tokens_drop_stopwords_and_single_chars():
    assert km.tokens('The International School of Arts & Sciences') == {'arts', 'sciences'}
    assert km.tokens('A B Private School') == set()
    assert km.tokens(None) == set()


def test_alpha_is_alnum_only():
    assert km.alpha('Al-Mawakeb School, L.L.C.') == 'almawakebschool'


# stage 2: token Jaccard

def test_jaccard_subset_bonus_wins():
    k = khda('Kings School Al Barsha', 'Arcadia School')
    win, scored = km.match_jaccard('Kings Al Barsha', k)
    assert win is k[0]
    assert scored[0][0] >= 0.6


def test_jaccard_below_threshold_returns_none_with_candidates():
    k = khda('Emirates British Nursery Mirdif')
    win, scored = km.match_jaccard('Emirates Rose Garden Mirdif Tower', k)
    assert win is None and scored


def test_jaccard_ambiguous_branches_defer():
    k = khda({'name': 'Al Mawakeb School Al Barsha', 'area': 'Al Barsha'},
             {'name': 'Al Mawakeb School Al Garhoud', 'area': 'Al Garhoud'})
    win, scored = km.match_jaccard('Al Mawakeb', k)
    assert win is None and len(scored) == 2


def test_jaccard_identical_token_sets_not_ambiguous():
    k = khda('Repton School', 'Repton School L.L.C')
    win, _ = km.match_jaccard('Repton School Dubai', k)
    assert win is k[0]


def test_jaccard_empty_name():
    assert km.match_jaccard('School', khda('Repton School')) == (None, [])


# stage 3: SequenceMatcher typos

def test_seqratio_catches_typo():
    k = khda('Dubai English Speaking College', 'Dubai American Academy')
    assert km.match_seqratio('Dubai Engllish Speaking College', k) is k[0]


def test_seqratio_needs_distinctive_token():
    k = khda('Delhi Private School')
    assert km.match_seqratio('Dubai Private School', k) is None


def test_seqratio_threshold():
    k = khda('Kings School Nad Al Sheba')
    assert km.match_seqratio('Kings Kids Nursery Jumeirah Beach', k) is None


# stage 4: proximity tiebreaker

def test_proximity_picks_area_in_suburb():
    k = khda({'name': 'Al Mawakeb School Al Barsha', 'area': 'Al Barsha'},
             {'name': 'Al Mawakeb School Al Garhoud', 'area': 'Al Garhoud'})
    _, scored = km.match_jaccard('Al Mawakeb', k)
    assert km.match_proximity({'name': 'Al Mawakeb', 'addr_suburb': 'Al Garhoud'}, scored) is k[1]


def test_proximity_no_hit_or_two_hits():
    k = khda({'name': 'X Academy One', 'area': 'Al Qusais'}, {'name': 'X Academy Two', 'area': 'Al Qusais'})
    _, scored = km.match_jaccard('X Academy', k)
    assert km.match_proximity({'name': 'X', 'addr_suburb': 'Al Qusais'}, scored) is None
    assert km.match_proximity({'name': 'X', 'addr_suburb': 'Deira'}, scored) is None
    assert km.match_proximity({'name': 'X'}, []) is None


# stage 5: polygon proximity

def test_match_polygon_single_candidate_in_district():
    k = khda({'name': 'Sunmarke School', 'area': 'Jumeirah Village Triangle'},
             {'name': 'Sunmarke Nursery', 'area': 'Al Barsha'})
    assert km.match_polygon({'name': 'Sunmarke'}, 'Jumeirah Village Triangle', k) is k[0]


def test_match_polygon_needs_district_and_tokens():
    k = khda({'name': 'Sunmarke School', 'area': 'Jumeirah Village Triangle'})
    assert km.match_polygon({'name': 'Sunmarke'}, '', k) is None
    assert km.match_polygon({'name': 'School'}, 'Jumeirah Village Triangle', k) is None


def test_find_district_smallest_container():
    feats = [feat('Big', square(55.0, 25.0, 1.0)), feat('Small', square(55.2, 25.2, 0.1))]
    assert km.find_district(feats, 25.25, 55.25) == 'Small'
    assert km.find_district(feats, 25.9, 55.9) == 'Big'
    assert km.find_district(feats, 24.0, 54.0) == ''


# geo-sanity

def test_area_norm_ordinals_and_al_prefix():
    assert km._area_norm('Al Barsha First') == km._area_norm('barsha 1') == 'barsha1'


def test_geo_consistent_rejects_far_namesake():
    lookup = km.build_polygon_lookup([feat('Al Sufouh First', square(55.18, 25.10, 0.02))])
    winner = {'area': 'Al Sufouh 1'}
    assert km.geo_consistent({'lat': 25.11, 'lon': 55.19}, winner, lookup)
    assert not km.geo_consistent({'lat': 25.26, 'lon': 55.30}, winner, lookup)
    assert km.geo_consistent({'lat': 25.26, 'lon': 55.30}, {'area': 'Nowhere Land'}, lookup)


def test_polygon_centroid_multipolygon_uses_largest_ring():
    g = {'type': 'MultiPolygon', 'coordinates': [[square(0, 0, 1)], [square(10, 10, 2) + [[10, 10]] * 2]]}
    lat, lon = km.polygon_centroid(g)
    assert lat > 9 and lon > 9


# universities

def test_uni_tokens_drop_campus_noise():
    assert ku.tokens('Heriot-Watt University Block 2 Academic City') == {'heriot', 'watt'}
    assert ku.tokens('Middlesex University Dubai Building 16') == {'middlesex'}


def test_uni_jaccard_requires_distinctive_token():
    k = khda('Institute of Management Technology', 'Murdoch University', mod=ku)
    assert ku.match_jaccard('Global Business Management Technology College', k)[0] is None
    assert ku.match_jaccard('Murdoch University Dubai', k)[0] is k[1]


def test_uni_seqratio_typo():
    k = khda('Manipal Academy of Higher Education', mod=ku)
    assert ku.match_seqratio('Manipaal Academy of Higher Education', k) is k[0]
