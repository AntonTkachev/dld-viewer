"""End-to-end KHDA ↔ OSM merge (khda_*_merge_into_viewer.merge) on tiny in-memory fixtures."""
import pytest

km = pytest.importorskip('khda_merge_into_viewer')
ku = pytest.importorskip('khda_uni_merge_into_viewer')


def square(lon, lat, d=0.01):
    return [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]


def feat(name, ring):
    return {'properties': {'name': name}, 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}


def osm(name, lat=25.0, lon=55.0, **kw):
    return {'name': name, 'lat': lat, 'lon': lon, **kw}


def school(sid, name, area='Nowhere Land'):
    return {'school_id': sid, 'center_id': f'c{sid}', 'name': name, 'curriculum': 'UK',
            'overall_rating': 'Good', 'wellbeing_rating': 'High', 'inclusion_rating': 'Good',
            'area': area, 'phone': f'04-{sid}', 'grade_range': 'FS1-Y13'}


def uni(uid, name, area=''):
    return {'university_id': uid, 'name': name, 'area': area, 'established_year': '2000',
            'star_rating': '4', 'rating_year': '2024'}


def run(osm_rows, khda_rows, features=(), manual=None):
    return km.merge(osm_rows, khda_rows, list(features), manual_coords=manual or {})


def by_name(rows):
    return {r['name']: r for r in rows}


ZERO = {'exact': 0, 'jaccard': 0, 'seqratio': 0, 'proximity': 0, 'polygon': 0,
        'none': 0, 'unnamed': 0, 'geo_rejected': 0, 'manual': 0}


def stats(**kw):
    return {**ZERO, **kw}


# OSM pre-filter

@pytest.mark.parametrize('name', [
    'American University in Dubai', 'Emirates Driving Institute', 'Belhasa Driving Center',
    'Musical Arts Centre', 'Staff Accommodation Block', 'Dubai Football Academy', 'كلية دبي',
])
def test_prefilter_drops_non_k12(name):
    out, st = run([osm(name)], [school('1', 'Repton School')])
    assert out == [] and st == ZERO


def test_prefilter_keeps_school_and_copies_osm_tags():
    o = osm('Repton', name_ar='ريبتون', operator='Repton', school_type='private', website='x', phone='ignored')
    out, _ = run([o, osm('Same', name_ar='Same')], [])
    assert out[0] == {'name': 'Repton', 'lat': 25.0, 'lon': 55.0, 'name_ar': 'ريبتون', 'operator': 'Repton',
                      'school_type': 'private', 'website': 'x', 'in_khda': False}
    assert 'name_ar' not in out[1]


def test_unnamed_kept_but_not_matched():
    out, st = run([osm('')], [school('1', 'School')])
    assert out == [{'name': '(unnamed school)', 'lat': 25.0, 'lon': 55.0, 'in_khda': False}]
    assert st == stats(unnamed=1)


# each stage in isolation

def test_stage_exact_copies_khda_fields():
    out, st = run([osm('Dubai English Speaking School')], [school('7', 'Dubai English Speaking School L.L.C', 'Oud Metha')])
    assert st == stats(exact=1)
    assert out[0] == {'name': 'Dubai English Speaking School', 'lat': 25.0, 'lon': 55.0,
                      'khda_id': '7', 'center_id': 'c7', 'curriculum': 'UK', 'rating': 'Good',
                      'wellbeing': 'High', 'inclusion': 'Good', 'area': 'Oud Metha', 'phone': '04-7',
                      'grade_range': 'FS1-Y13', 'in_khda': True}


def test_stage_jaccard():
    out, st = run([osm('Kings Barsha')], [school('1', 'Kings School Al Barsha')])
    assert st == stats(jaccard=1) and out[0]['khda_id'] == '1'


def test_stage_seqratio_typo():
    k = [school('1', 'Dubai English Speaking College', 'Academic City'), school('2', 'Dubai American Academy')]
    out, st = run([osm('Dubai Engllish Speaking College')], k)
    assert st == stats(seqratio=1) and out[0]['khda_id'] == '1'


def test_stage_proximity_breaks_branch_ambiguity():
    k = [school('1', 'Al Mawakeb School Al Barsha', 'Al Barsha'),
         school('2', 'Al Mawakeb School Al Garhoud', 'Al Garhoud')]
    out, st = run([osm('Al Mawakeb', addr_suburb='Al Garhoud')], k)
    assert st == stats(proximity=1) and out[0]['khda_id'] == '2'


def test_ambiguity_without_area_hint_is_unmatched():
    k = [school('1', 'Al Mawakeb School Al Barsha', 'Al Barsha'),
         school('2', 'Al Mawakeb School Al Garhoud', 'Al Garhoud')]
    out, st = run([osm('Al Mawakeb', addr_suburb='Deira')], k)
    assert st == stats(none=1) and out[0]['in_khda'] is False


def test_stage_polygon_weak_name_in_containing_district():
    jvt = feat('Jumeirah Village Triangle', square(55.18, 25.04, 0.02))
    k = [school('1', 'Sunmarke Kindergarten Nursery', 'Jumeirah Village Triangle')]
    out, st = run([osm('Sunmarke Kids', lat=25.05, lon=55.19)], k, [jvt])
    assert st == stats(polygon=1) and out[0]['khda_id'] == '1'


def test_polygon_stage_needs_features_and_containment():
    k = [school('1', 'Sunmarke Kindergarten Nursery', 'Jumeirah Village Triangle')]
    jvt = feat('Jumeirah Village Triangle', square(55.18, 25.04, 0.02))
    assert run([osm('Sunmarke Kids', lat=25.05, lon=55.19)], k)[1] == stats(none=1)
    assert run([osm('Sunmarke Kids', lat=25.30, lon=55.40)], k, [jvt])[1] == stats(none=1)


# geo-sanity

def test_geo_sanity_rejects_far_namesake_at_every_stage():
    sufouh = feat('Al Sufouh First', square(55.18, 25.10, 0.02))
    k = [school('1', 'GEMS Wellington International School', 'Al Sufouh 1')]
    far, st = run([osm('GEMS Wellington International', lat=25.26, lon=55.30)], k, [sufouh])
    assert far[0]['in_khda'] is False
    assert st == stats(none=1, geo_rejected=3)  # exact, jaccard, seqratio
    near, st = run([osm('GEMS Wellington International', lat=25.11, lon=55.19)], k, [sufouh])
    assert st == stats(exact=1) and near[0]['khda_id'] == '1'


# first-wins

def test_first_wins_khda_not_reused_by_later_stage():
    k = [school('1', 'Repton School')]
    out, st = run([osm('Repton School'), osm('Repton'), osm('Repton Junior')], k)
    assert [r.get('khda_id') for r in out] == ['1', None, None]
    assert st == stats(exact=1, none=2)


def test_first_wins_follows_osm_order():
    k = [school('1', 'Repton School')]
    out, st = run([osm('Repton Junior'), osm('Repton School')], k)
    assert [r.get('khda_id') for r in out] == ['1', None]
    assert st == stats(jaccard=1, none=1)


# manual coords (KHDA-only rows)

def test_manual_coords_preclaim_and_append():
    k = [school('9', 'Hidden Academy Oasis'), school('5', 'Repton School')]
    out, st = run([osm('Hidden Oasis'), osm('Repton School')], k, manual={'9': (25.1, 55.2)})
    assert st == stats(exact=1, none=1, manual=1)
    assert out[0]['in_khda'] is False  # id 9 was pre-claimed
    assert out[-1] == {'name': 'Hidden Academy Oasis', 'lat': 25.1, 'lon': 55.2, 'khda_id': '9',
                       'center_id': 'c9', 'curriculum': 'UK', 'rating': 'Good', 'wellbeing': 'High',
                       'inclusion': 'Good', 'area': 'Nowhere Land', 'phone': '04-9',
                       'grade_range': 'FS1-Y13', 'in_khda': True, 'manual_coords': True}


def test_manual_coords_missing_id_skipped(capsys):
    out, st = run([], [school('1', 'Repton School')], manual={'404': (25.1, 55.2)})
    assert out == [] and st == ZERO
    assert 'id=404' in capsys.readouterr().err


def test_default_manual_coords_is_module_constant():
    assert km.merge.__defaults__ == (km.MANUAL_COORDS,)


# full mix

def test_mixed_fixture_stats_and_output():
    jvt = feat('Jumeirah Village Triangle', square(55.18, 25.04, 0.02))
    k = [school('1', 'Dubai English Speaking School L.L.C'),
         school('2', 'Kings School Al Barsha'),
         school('3', 'Al Mawakeb School Al Barsha', 'Al Barsha'),
         school('4', 'Al Mawakeb School Al Garhoud', 'Al Garhoud'),
         school('5', 'Sunmarke Kindergarten Nursery', 'Jumeirah Village Triangle'),
         school('6', 'KHDA Only Academy'),
         school('7', 'Manual Placed School')]
    o = [osm('Dubai English Speaking School'), osm('Kings Barsha'), osm('Al Mawakeb', addr_suburb='Al Barsha'),
         osm('Sunmarke Kids', lat=25.05, lon=55.19), osm('Totally Unknown Nursery'), osm(''),
         osm('Heriot-Watt University')]
    out, st = run(o, k, [jvt], manual={'7': (25.2, 55.3)})
    assert st == stats(exact=1, jaccard=1, proximity=1, polygon=1, none=1, unnamed=1, manual=1)
    got = {r['name']: r.get('khda_id') for r in out}
    assert got == {'Dubai English Speaking School': '1', 'Kings Barsha': '2', 'Al Mawakeb': '3',
                   'Sunmarke Kids': '5', 'Totally Unknown Nursery': None, '(unnamed school)': None,
                   'Manual Placed School': '7'}
    assert 'KHDA Only Academy' not in got  # no OSM marker, no manual coords


def test_merge_does_not_mutate_inputs():
    o, k = [osm('Repton School')], [school('1', 'Repton School')]
    run(o, k)
    assert o == [osm('Repton School')] and k == [school('1', 'Repton School')]


# universities

def urun(osm_rows, khda_rows, features=()):
    return ku.merge(osm_rows, khda_rows, list(features))


UZERO = {'exact': 0, 'jaccard': 0, 'seqratio': 0, 'polygon': 0, 'none': 0, 'khda_only': 0}


def ustats(**kw):
    return {**UZERO, **kw}


def test_uni_stage_exact_copies_fields_and_osm_tags():
    out, st = urun([osm('Murdoch University Dubai', amenity='university', addr_city='Dubai', name_ar='مردوخ')],
                   [uni('3', 'Murdoch University', 'Dubai Knowledge Park')])
    assert st == ustats(exact=1)
    assert out == [{'name': 'Murdoch University Dubai', 'lat': 25.0, 'lon': 55.0, 'name_ar': 'مردوخ',
                    'addr_city': 'Dubai', 'amenity': 'university', 'khda_uni_id': '3',
                    'khda_area': 'Dubai Knowledge Park', 'khda_established': '2000', 'khda_stars': '4',
                    'khda_rating_year': '2024', 'in_khda': True}]


def test_uni_stage_jaccard():
    out, st = urun([osm('Heriot Watt')], [uni('1', 'Heriot-Watt University Edinburgh')])
    assert st == ustats(jaccard=1) and out[0]['khda_uni_id'] == '1'


def test_uni_stage_seqratio():
    out, st = urun([osm('Manipaal Academy Higher Educaton')], [uni('1', 'Manipal Academy of Higher Education')])
    assert st == ustats(seqratio=1) and out[0]['khda_uni_id'] == '1'


def test_uni_stage_polygon():
    dso = feat('Dubai Silicon Oasis', square(55.37, 25.11, 0.03))
    k = [uni('1', 'Rochester Institute of Technology Dubai Silicon Oasis Campus', 'Dubai Silicon Oasis')]
    out, st = urun([osm('Rochester Institute Tech', lat=25.12, lon=55.38)], k, [dso])
    assert st == ustats(polygon=1) and out[0]['khda_uni_id'] == '1'


def test_uni_unnamed_and_osm_only():
    out, st = urun([{'lat': 25.0, 'lon': 55.0}, osm('Some Random College')], [])
    assert [r['in_khda'] for r in out] == [False, False]
    assert out[0]['name'] == '(unnamed)' and st == ustats(none=2)


def test_uni_passes_are_global_first_wins():
    # exact pass runs over all OSM rows before jaccard, so the later exact row wins
    out, st = urun([osm('Heriot Watt Edinburgh'), osm('Heriot-Watt University')], [uni('1', 'Heriot-Watt University')])
    assert [r.get('khda_uni_id') for r in out] == [None, '1']
    assert st == ustats(exact=1, none=1)


def test_uni_khda_only_alias_substring_and_skip():
    feats = [feat('Dubai International Financial Centre', square(55.27, 25.20, 0.02)),
             feat('Al Sufouh 1', square(55.15, 25.09, 0.02)),
             feat('Dubai Internet City Phase 2', square(55.16, 25.10, 0.02))]
    k = [uni('1', 'London Business School', 'DIFC'),
         uni('2', 'SP Jain', 'Dubai Knowledge Park'),
         uni('3', 'Hult', 'Dubai Internet City Phase'),
         uni('4', 'No Area U', ''),
         uni('5', 'Mars Campus', 'Olympus Mons')]
    out, st = urun([], k, feats)
    assert st == ustats(khda_only=3)
    got = by_name(out)
    assert set(got) == {'London Business School', 'SP Jain', 'Hult'}
    lbs = got['London Business School']
    assert lbs['source'] == 'khda' and lbs['khda_area'] == 'DIFC' and lbs['in_khda'] is True
    assert (lbs['lat'], lbs['lon']) == tuple(round(c, 6) for c in ku.poly_centroid(feats[0]['geometry']))
    assert got['SP Jain']['lat'] == round(ku.poly_centroid(feats[1]['geometry'])[0], 6)


def test_uni_matched_khda_not_added_again():
    feats = [feat('Dubai International Financial Centre', square(55.27, 25.20, 0.02))]
    out, st = urun([osm('London Business School')], [uni('1', 'London Business School', 'DIFC')], feats)
    assert len(out) == 1 and st == ustats(exact=1)
