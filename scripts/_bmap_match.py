"""Name normalization and the staged DLD → OSM building name matcher (build_buildings_map.py)."""
import collections
import difflib
import re

from _bmap_geo import GEO_SANITY_KM, haversine_km

# Words that carry no discriminating power in Dubai tower names. Used to
# normalize names before exact/jaccard match.
STOP = {
    'tower', 'towers', 'residence', 'residences', 'residential', 'building',
    'apartments', 'apartment', 'flats', 'flat', 'villa', 'villas',
    'the', 'of', 'for', 'and', 'by', 'at', 'a', 'an',
    'dubai', 'al', 'el',
    'llc', 'l.l.c', 'dwc', 'co', 'company', 'group',
    'phase', 'block', 'plot',
}

JACCARD_THRESHOLD = 0.6
SEQMATCH_THRESHOLD = 0.82          # Building-name fuzzy match
PROJECT_SEQMATCH_THRESHOLD = 0.92  # project_name fallback — stricter, to
                                   # reject collisions like Bluewaters ↔ Blue Waves.


# Suffix patterns that DLD attaches to break a single building into sub-units.
# Stripping them lets `Skycourts Tower A`/`B`/`C` collapse to `Skycourts Tower`.
# NOTE: we only strip single trailing LETTERS (A/B/C) after Tower/Block/etc —
# NOT numbers. Numbers (Tower 1, Tower 2) are distinct buildings and must be
# preserved in tokens so cross-tower false matches are impossible.
_SUFFIX_RE = re.compile(
    r'\s*'
    r'('
        r'-\s*(residential|commercial|office|retail|hotel|tower|podium)s?'
    r'|'
        r'\s+(tower|block|building|phase|wing|cluster)\s+[a-z]'  # letter only, not digits
    r'|'
        r'\s+[a-z]'                       # trailing single letter (Tower A → Tower)
    r'|'
        r'\s*\((branch|tower|building|residential|commercial|phase \d+)\)'
    r')\s*$',
    re.IGNORECASE,
)

# Token normalization: Roman numerals and English number words → Arabic digits.
# Lets "THE WIND TOWER II" match "Wind Tower 2" and "WIND ONE" match "Wind Tower 1".
# 'i' (single char) is filtered by the len>1 guard, so we start at ii/two.
_ROMAN = {
    'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
    'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
    # 'six'/'seven' intentionally omitted — they appear as brand names in Dubai
    # ("Six Senses", "Seven City", "Seven Hotel") and would cause cross-type
    # false positives when matched against OSM buildings named with digit '6'/'7'.
    'eight': '8', 'nine': '9', 'ten': '10',
}


def strip_subunit(s: str) -> str:
    """Iteratively strip trailing sub-unit suffixes."""
    prev = ''
    cur = (s or '').strip()
    while cur != prev:
        prev = cur
        cur = _SUFFIX_RE.sub('', cur).strip()
    return cur


def tokens(s: str):
    s = strip_subunit(s or '')
    s = s.lower()
    s = re.sub(r"\bl\.?l\.?c\.?\b", '', s)
    s = re.sub(r"[^a-z0-9 ]+", ' ', s)
    result = set()
    for t in s.split():
        if not t or t in STOP or (len(t) <= 1 and not t.isdecimal()):
            continue
        result.add(_ROMAN.get(t, t))  # normalize Roman numerals
    return result


def _trailing_subunit(s: str) -> str:
    """Extract trailing sub-unit designator (single letter A/B/C or digits 1/2/3)
    when it is preceded by a space — indicates a unit qualifier, not part of the name.
    Returns uppercase string or '' if none found."""
    m = re.search(r'(?<=\s)([A-Za-z]|\d+)\s*$', (s or '').strip())
    return m.group(1).upper() if m else ''


def _trailing_num(s: str) -> str:
    """Extract trailing digit sequence from a string regardless of preceding space.
    Used for Arabic names where DLD sometimes omits the space (e.g. 'الجاز3' vs 'الجاز 2')."""
    m = re.search(r'\d+\s*$', (s or '').strip())
    return m.group().strip() if m else ''


def norm_key(s: str) -> str:
    return ' '.join(sorted(tokens(s)))


def alpha(s: str) -> str:
    s = strip_subunit(s or '').lower()
    s = re.sub(r"[^a-z0-9]+", '', s)
    return s


def build_indices(osm: list):
    """Index OSM polygons. We maintain SEPARATE indices for direct match vs
    compound fallback so that a coincidence like `name=Palm Jumeirah` on a
    huge place=neighbourhood polygon never resolves a DLD building called
    `Muraba Residences Palm Jumeirah`.
      *_b   → building-tagged polygons only (eligible for direct match)
      *_c   → compound/site/place polygons (eligible only as project/master fallback)
    """
    by_exact_b   = collections.defaultdict(list)
    by_alpha_b   = {}
    by_ar_b      = collections.defaultdict(list)
    token_rows_b = []
    by_exact_c   = collections.defaultdict(list)
    by_alpha_c   = {}
    for o in osm:
        k = o.get('kind', 'building')
        if k == 'district':
            # place=neighbourhood/suburb/quarter — far too coarse to attach
            # a single building to. Skip entirely.
            continue
        is_building = (k == 'building')
        bx = by_exact_b if is_building else by_exact_c
        ba = by_alpha_b if is_building else by_alpha_c
        for name_field in ('name:en', 'name', 'official_name',
                           'addr:housename', 'loc_name', 'alt_name',
                           'building:name'):
            n = (o.get(name_field) or
                 o.get(name_field.replace(':', '_')))
            if not n:
                continue
            k = norm_key(n)
            if k:
                bx[k].append(o)
            a = alpha(n)
            if a:
                ba.setdefault(a, o)
            t = tokens(n)
            if t and is_building:
                token_rows_b.append((t, o))
            # Extra: for "N, Street Name" address-format OSM buildings, also
            # index under a compact alt-key so DLD "Project N" can match them.
            # "1, Blue Waters Island Street" → strip road-type and geo-qualifier
            # words → join → "bluewaters 1" → same norm_key as DLD's "1 bluewaters".
            _addr_m = re.match(r'^(\d+),\s*(.+)$', n)
            if _addr_m and is_building:
                _addr_num  = _addr_m.group(1)
                _addr_words = _addr_m.group(2).lower().split()
                _ROAD_TYPES = {'street','road','avenue','lane','drive','boulevard',
                               'way','walk','close','court','place','terrace'}
                _GEO_QUAL   = {'island','islands','bay','creek','beach','peninsula',
                               'park','heights','hills','lake','lakes',
                               'garden','gardens','quarter'}
                # Strip trailing road-type then trailing geo-qualifier
                while _addr_words and _addr_words[-1] in _ROAD_TYPES:
                    _addr_words.pop()
                while _addr_words and _addr_words[-1] in _GEO_QUAL:
                    _addr_words.pop()
                if _addr_words:
                    _compact = ''.join(_addr_words)  # join without spaces
                    _alt_n   = f"{_compact} {_addr_num}"
                    _alt_k   = norm_key(_alt_n)
                    if _alt_k and _alt_k != k:
                        bx[_alt_k].append(o)
        # Arabic side — only building-tagged polygons can resolve a direct AR match.
        if is_building:
            for name_field in ('name:ar', 'name_ar', 'official_name:ar'):
                n = o.get(name_field) or o.get(name_field.replace(':', '_'))
                if n and _is_ar(n):
                    k = norm_ar(n)
                    if k:
                        by_ar_b[k].append(o)
            n = o.get('name')
            if n and _is_ar(n):
                k = norm_ar(n)
                if k:
                    by_ar_b[k].append(o)
    return (by_exact_b, by_alpha_b, token_rows_b, by_ar_b,
            by_exact_c, by_alpha_c)


def _is_ar(s: str) -> bool:
    return any('؀' <= ch <= 'ۿ' for ch in (s or ''))


def norm_ar(s: str) -> str:
    """Normalize an Arabic name for exact match. Removes Latin chars, digits,
    and Arabic diacritics; collapses whitespace."""
    s = s or ''
    s = re.sub(r'[ً-ٰٟ]', '', s)  # diacritics
    s = re.sub(r'[A-Za-z0-9]+', ' ', s)
    s = re.sub(r'[^؀-ۿ ]+', ' ', s)
    return ' '.join(s.split())


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def match_one(dld_name: str,
              by_exact_b, by_alpha_b, token_rows_b, by_ar_b,
              by_exact_c, by_alpha_c,
              dld_name_ar='', dld_project='', dld_master='',
              area_centroid=None, exclude_ids=frozenset()):
    """Return (osm_row, match_kind) or (None, None).

    Direct name matches (steps 1-3) are restricted to building-tagged OSM
    polygons; compound/site/place polygons are eligible only via the
    project_name fallback (step 4)."""
    # 1. Exact normalized (EN) — buildings only.
    k = norm_key(dld_name)
    hits = [h for h in by_exact_b.get(k, []) if h.get('osm_id') not in exclude_ids]
    if hits:
        # build_indices appends one entry per name_field, so the same OSM building
        # can appear multiple times. Deduplicate by osm_id for disambiguation.
        unique_ids = {h.get('osm_id') for h in hits}
        if len(unique_ids) > 1:
            # Multiple distinct OSM buildings share the same norm_key
            # (e.g. "Silverene Tower A" and "Silverene Tower B" both → {'silverene'}).
            # 1) Prefer the one whose trailing sub-unit letter/number matches DLD.
            dld_sub = _trailing_subunit(dld_name)
            if dld_sub:
                sub_hits = [h for h in hits
                            if _trailing_subunit(h.get('name') or h.get('name:en') or '')
                               == dld_sub]
                sub_unique = {h.get('osm_id') for h in sub_hits}
                if len(sub_unique) == 1:
                    return sub_hits[0], 'exact'
            # 2) Fall back to geo-proximity: pick the building closest to the
            #    DLD area centroid. Avoids returning "Al Murjan Tower" (Sharjah)
            #    when "Murjan" (Dubai Marina) is the correct hit for Marsa Dubai.
            if area_centroid:
                seen_geo = set()
                unique_hits = []
                for h in hits:
                    oid = h.get('osm_id')
                    if oid not in seen_geo:
                        seen_geo.add(oid)
                        unique_hits.append(h)
                closest = min(unique_hits,
                              key=lambda h: haversine_km(area_centroid[0], area_centroid[1],
                                                          h['lat'], h['lon']))
                return closest, 'exact'
        return hits[0], 'exact'

    # 1c-pre. Alpha exact: same character sequence after removing all non-alphanum.
    # Catches compound-word splits like "GOLDCREST VIEWS 2" ↔ "Gold Crest Views 2"
    # and run-together DLD names like "ALNAKHEEL 1" ↔ "Al Nakheel 1".
    # Must run BEFORE Arabic exact so English alpha match wins over wrong Arabic
    # match when OSM only has one Arabic building for a numbered series.
    a_pre = alpha(dld_name)
    if a_pre and by_alpha_b.get(a_pre) and by_alpha_b[a_pre].get('osm_id') not in exclude_ids:
        return by_alpha_b[a_pre], 'alpha_exact'

    # 1b. Exact Arabic — buildings only.
    # Sub-unit disambiguation: when multiple Arabic buildings share the same
    # norm_ar key (digits stripped), prefer the one whose trailing number matches.
    # When only one Arabic candidate exists but its sub-unit number differs from
    # DLD's, skip the Arabic match (fall through to fuzzy steps) — avoids
    # "ALJAZ 3" wrongly matching the only Arabic building "الجاز 2".
    if dld_name_ar:
        kar = norm_ar(dld_name_ar)
        ar_hits = [h for h in by_ar_b.get(kar, []) if h.get('osm_id') not in exclude_ids]
        if ar_hits:
            ar_unique_ids = {h.get('osm_id') for h in ar_hits}
            dld_ar_sub = _trailing_subunit(dld_name_ar)
            if len(ar_unique_ids) > 1:
                if dld_ar_sub:
                    ar_sub_hits = [h for h in ar_hits
                                   if _trailing_subunit(
                                       h.get('name:ar') or h.get('name_ar') or h.get('name') or '')
                                      == dld_ar_sub]
                    ar_sub_unique = {h.get('osm_id') for h in ar_sub_hits}
                    if len(ar_sub_unique) == 1:
                        return ar_sub_hits[0], 'exact_ar'
                return ar_hits[0], 'exact_ar'
            else:
                # Single Arabic candidate: verify trailing number matches.
                # Use _trailing_num (not _trailing_subunit) because DLD sometimes
                # omits the space before the digit (e.g. 'الجاز3' not 'الجاز 3').
                dld_ar_num = _trailing_num(dld_name_ar)
                if dld_ar_num:
                    osm_ar_num = _trailing_num(
                        ar_hits[0].get('name:ar') or ar_hits[0].get('name_ar') or
                        ar_hits[0].get('name') or '')
                    if osm_ar_num and osm_ar_num != dld_ar_num:
                        pass  # number mismatch → skip, fall through to fuzzy steps
                    else:
                        return ar_hits[0], 'exact_ar'
                else:
                    return ar_hits[0], 'exact_ar'

    # 2. Jaccard ≥ threshold (EN tokens) — buildings only.
    dt = tokens(dld_name)
    if dt:
        best = (0.0, None)
        for tt, osm in token_rows_b:
            if osm.get('osm_id') in exclude_ids:
                continue
            j = jaccard(dt, tt)
            if j > best[0]:
                best = (j, osm)
        if best[0] >= JACCARD_THRESHOLD and best[1]:
            return best[1], 'jaccard'

    # 2b. Token-subset: all DLD tokens appear in some OSM building's token set.
    # Catches abbreviated DLD names, e.g. "Grande" → "Grande Signature Residences".
    # Accept only when there is a single best candidate (unambiguous subset).
    # Deduplicate by osm_id — token_rows_b indexes each OSM building once per
    # name_field, so the same building can appear multiple times with equal j.
    if dt:
        seen_sub = set()
        subset_hits = []
        for tt, osm in token_rows_b:
            if dt < tt:  # proper subset only (equal sets already caught above)
                oid = osm.get('osm_id')
                if oid in exclude_ids:
                    continue
                if oid not in seen_sub:
                    seen_sub.add(oid)
                    subset_hits.append((jaccard(dt, tt), osm))
        if subset_hits:
            subset_hits.sort(key=lambda x: -x[0])
            if len(subset_hits) == 1 or subset_hits[0][0] > subset_hits[1][0]:
                return subset_hits[0][1], 'subset'

    # 2c. Reverse subset: all OSM tokens appear in DLD token set.
    # Catches OSM using shorter/abbreviated names, e.g.:
    #   DLD "PARK ISLAND BLAKELY" → OSM "Blakely Tower" ({'blakely'} ⊂ DLD)
    #   DLD "AL SEEF 1" → OSM "Al Seef Tower" ({'seef'} ⊂ DLD {'seef','1'})
    # Guard: skip when all OSM tokens are pure numbers — those are too ambiguous.
    # Deduplicate by osm_id (same fix as 2b above).
    # Same unambiguous-best guard as 2b.
    if dt:
        seen_rev = set()
        rev_hits = []
        for tt, osm in token_rows_b:
            if tt and tt < dt and not all(t.isdecimal() for t in tt):
                oid = osm.get('osm_id')
                if oid in exclude_ids:
                    continue
                if oid not in seen_rev:
                    seen_rev.add(oid)
                    rev_hits.append((jaccard(dt, tt), osm))
        if rev_hits:
            rev_hits.sort(key=lambda x: -x[0])
            if len(rev_hits) == 1 or rev_hits[0][0] > rev_hits[1][0]:
                hit = rev_hits[0][1]
                # Geo-check before committing: if this hit is far from the area
                # centroid, fall through to seqmatch which may find a closer
                # building. (e.g. "GREEN LAKES S1" rev_subsets to "Green Tower"
                # 27 km away, while seqmatch finds "Green Lakes 1" 2 km away.)
                if area_centroid:
                    _d = haversine_km(area_centroid[0], area_centroid[1],
                                      hit['lat'], hit['lon'])
                    if _d > GEO_SANITY_KM:
                        pass  # fall through to seqmatch
                    else:
                        return hit, 'rev_subset'
                else:
                    return hit, 'rev_subset'

    # 3. SequenceMatcher on alpha-only — buildings only.
    a = alpha(dld_name)
    if a:
        close_all = difflib.get_close_matches(a, list(by_alpha_b.keys()),
                                              n=5, cutoff=SEQMATCH_THRESHOLD)
        for ck in close_all:
            cand = by_alpha_b[ck]
            if cand.get('osm_id') in exclude_ids:
                continue
            # Token guard: require at least one distinctive token in common.
            # Exceptions (accept without token overlap):
            #   • identical alpha strings ("MAG218" vs "MAG 218" differ only in spacing)
            #   • near-identical alpha strings (≥0.95 ratio) — catches compound-word
            #     splits like "Blue Bell" vs "Bluebell" where tokenisation diverges.
            ratio = difflib.SequenceMatcher(None, a, ck).ratio()
            if ratio >= 0.95 or tokens(dld_name) & tokens(cand.get('name', '')):
                return cand, 'seqmatch'
            break

    # 1c. Exact norm-key match against compound index (buildings-only step 1
    # missed it). E.g. "Skycourts Tower A" norm='skycourts' matches compound
    # "Skycourts Towers" norm='skycourts'. Treated as project_exact so the
    # 300k m² area guard and compound vis apply.
    _c_hits = [h for h in by_exact_c.get(k, []) if h.get('osm_id') not in exclude_ids]
    if k and _c_hits:
        return _c_hits[0], 'project_exact'

    # 4. project_name fallback — Skycourts Tower A → Skycourts compound.
    # Only useful when project ≠ master (otherwise the OSM hit would be a
    # whole district like Palm Jumeirah / Discovery Gardens).
    # Compound index includes landuse and site relations only — large
    # place=neighbourhood polygons are filtered out at load time below.
    if dld_project and dld_project != dld_name and dld_project != dld_master:
        kp = norm_key(dld_project)
        hits = [h for h in (by_exact_c.get(kp, []) + by_exact_b.get(kp, []))
                if h.get('osm_id') not in exclude_ids]
        if hits:
            return hits[0], 'project_exact'
        ap = alpha(dld_project)
        if ap:
            close_all = difflib.get_close_matches(
                ap, list(by_alpha_c.keys()) + list(by_alpha_b.keys()),
                n=5, cutoff=PROJECT_SEQMATCH_THRESHOLD)
            for ck in close_all:
                cand = by_alpha_c.get(ck) or by_alpha_b.get(ck)
                if cand and cand.get('osm_id') not in exclude_ids:
                    return cand, 'project_seqmatch'

    return None, None
