"""JS sanity via node: every shipped js parses, and each page's classic scripts share
one global scope without duplicate let/const/class declarations. Pages + script lists
are discovered from the HTML templates, so renamed/split js files are picked up."""
import glob
import os
import re
import shutil
import subprocess

import pytest

from conftest import ROOT

NODE = shutil.which('node')
pytestmark = [pytest.mark.node, pytest.mark.skipif(not NODE, reason='node not on PATH')]

PAGES = ['template.html', 'index.html'] + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, 'templates', '*.html')))
SCRIPT_RE = re.compile(r'<script\b([^>]*)>(.*?)</script>', re.S | re.I)
SRC_RE = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']')
TYPE_RE = re.compile(r'\btype\s*=\s*["\']([^"\']+)["\']')
JS_TYPES = ('', 'text/javascript', 'application/javascript', 'module')


def local_path(src):
    if src.startswith(('http://', 'https://', '//')):
        return None
    src = re.sub(r'^__[A-Z_]+__', '', src.split('?', 1)[0].split('#', 1)[0])
    return os.path.join(ROOT, src.lstrip('/'))


def page_scripts(page):
    """[(label, code, is_module)] in document order; None code = missing file."""
    html = open(os.path.join(ROOT, page), encoding='utf-8').read()
    html = re.sub(r'<!--.*?-->', '', html, flags=re.S)
    out = []
    for i, (attrs, body) in enumerate(SCRIPT_RE.findall(html)):
        t = (TYPE_RE.search(attrs).group(1).lower() if TYPE_RE.search(attrs) else '')
        if t not in JS_TYPES:
            continue
        m = SRC_RE.search(attrs)
        if m:
            p = local_path(m.group(1))
            if p is None:
                continue
            out.append((os.path.relpath(p, ROOT), open(p, encoding='utf-8').read() if os.path.exists(p) else None, t == 'module'))
        elif body.strip():
            out.append((f'{page}#inline{i}', body, t == 'module'))
    return out


def node_check(path):
    p = subprocess.run([NODE, '--check', path], capture_output=True, text=True)
    return p.returncode, (p.stderr or p.stdout)


def shipped_js():
    pats = ['js/*.js', 'polygons/*.js', 'periods/*.js', 'pois/*.js', 'transactions/data/*.js', 'rents/data/*.js']
    files = sorted({os.path.relpath(f, ROOT) for pat in pats for f in glob.glob(os.path.join(ROOT, pat))})
    for page in PAGES:
        if os.path.exists(os.path.join(ROOT, page)):
            files += [l for l, c, _ in page_scripts(page) if c is not None and '#inline' not in l and l not in files]
    return files


@pytest.mark.parametrize('rel', shipped_js())
def test_node_check(rel):
    code, err = node_check(os.path.join(ROOT, rel))
    assert code == 0, err[-2000:]


@pytest.mark.parametrize('page', PAGES)
def test_page_scripts_exist(page):
    if not os.path.exists(os.path.join(ROOT, page)):
        pytest.skip(f'{page} missing')
    missing = [l for l, c, _ in page_scripts(page) if c is None]
    assert not missing, f'{page} references missing scripts: {missing}'


@pytest.mark.parametrize('page', PAGES)
def test_page_global_scope_no_duplicate_declarations(page, tmp_path):
    if not os.path.exists(os.path.join(ROOT, page)):
        pytest.skip(f'{page} missing')
    parts, spans, line = [], [], 1
    for label, code, is_module in page_scripts(page):
        if code is None:
            continue
        if is_module:
            mod = tmp_path / (re.sub(r'\W', '_', label) + '.mjs')
            mod.write_text(code, encoding='utf-8')
            rc, err = node_check(str(mod))
            assert rc == 0, f'{label}: {err[-1500:]}'
            continue
        chunk = code.rstrip('\n') + '\n;\n'
        spans.append((line, label))
        parts.append(chunk)
        line += chunk.count('\n')
    joined = tmp_path / 'page.js'
    joined.write_text(''.join(parts), encoding='utf-8')
    rc, err = node_check(str(joined))
    if rc:
        m = re.search(r'page\.js:(\d+)', err)
        where = next((lbl for start, lbl in reversed(spans) if m and start <= int(m.group(1))), '?')
        pytest.fail(f'{page}: scripts clash in the shared global scope (near {where}):\n{err[-1500:]}')


def test_every_js_file_is_referenced():
    """A split-off js/*.js nobody loads is dead or forgotten in a template."""
    hay = ''
    for pat in ('*.html', 'templates/*.html', 'js/*.js', 'scripts/*.py'):
        for f in glob.glob(os.path.join(ROOT, pat)):
            hay += open(f, encoding='utf-8', errors='ignore').read()
    orphans = [f for f in sorted(glob.glob(os.path.join(ROOT, 'js', '*.js')))
               if hay.count(os.path.basename(f)) == 0]
    assert not orphans, f'unreferenced js files: {orphans}'


def test_clash_detector_self_check(tmp_path):
    f = tmp_path / 'page.js'
    f.write_text('const A = 1;\n;\nfunction b() {}\n;\nlet A = 2;\n;\n')
    rc, err = node_check(str(f))
    assert rc != 0 and 'already been declared' in err
    f.write_text('var A = 1;\n;\nvar A = 2;\n;\nfunction b() {}\n;\nfunction b() {}\n;\n')
    assert node_check(str(f))[0] == 0
