"""Shared read/write for pois/all.js — the externalized bundle of the 16
POI-layer consts (POIS, METRO_*, SCHOOLS, UNIVERSITIES, MEDICAL, MOSQUES,
PROJECTS, MALLS, TRAM_*, ETIHAD_*, GOLD_*) that used to be inlined directly
into template.html. Every generator that used to patch one of these consts
into template.html now calls patch_const() here instead.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / 'template.html'
JS_OUT = ROOT / 'pois' / 'all.js'

CONST_ORDER = [
    'POIS', 'METRO_LINES', 'METRO_STATIONS', 'SCHOOLS', 'UNIVERSITIES',
    'MEDICAL', 'MOSQUES', 'PROJECTS', 'MALLS', 'TRAM_LINE', 'TRAM_STATIONS',
    'ETIHAD_LINE', 'ETIHAD_STATIONS', 'GOLD_LINE', 'GOLD_STATIONS',
    'GOLD_INTERCHANGES',
]

_CONST_RE = re.compile(r'^const (\w+) = (.*);$', re.MULTILINE)


def read_bundle() -> dict:
    if not JS_OUT.exists():
        return {}
    text = JS_OUT.read_text(encoding='utf-8')
    return {m.group(1): json.loads(m.group(2)) for m in _CONST_RE.finditer(text)}


def write_js(consts: dict) -> str:
    lines = [
        'const ' + name + ' = ' + json.dumps(consts[name], separators=(',', ':'), ensure_ascii=False) + ';\n'
        for name in CONST_ORDER if name in consts
    ]
    JS_OUT.parent.mkdir(parents=True, exist_ok=True)
    JS_OUT.write_text(''.join(lines), encoding='utf-8')
    return hashlib.sha256(JS_OUT.read_bytes()).hexdigest()[:8]


def write_bundle(consts: dict) -> str:
    write_js(consts)
    return restamp_template()


def patch_const(name: str, value) -> str:
    consts = read_bundle()
    consts[name] = value
    return write_bundle(consts)


def restamp_template() -> str:
    h = hashlib.sha256(JS_OUT.read_bytes()).hexdigest()[:8]
    text = HTML.read_text(encoding='utf-8')
    tag = f'<script src="/pois/all.js?v={h}"></script>\n'
    if 'pois/all.js' in text:
        text = re.sub(r'<script src="/pois/all\.js\?v=[0-9a-f]+"></script>\n', tag, text)
    else:
        anchor = re.search(r'<script src="/periods/all\.js\?v=[0-9a-f]+"></script>\n', text)
        if not anchor:
            raise RuntimeError('periods/all.js anchor not found in template.html')
        text = text[:anchor.end()] + tag + text[anchor.end():]
    HTML.write_text(text, encoding='utf-8')
    return h
