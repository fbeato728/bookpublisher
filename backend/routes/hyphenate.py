"""
hyphenate.py — Flask blueprint for hyphenating project XHTML files.

Uses a standalone port of the Hyphenate This! Calibre plugin logic.
No Calibre dependency — reads cat.dic directly from hyphthisdicts.zip.
"""

import os
import re
import zipfile
import tempfile

from flask import Blueprint, jsonify
from lxml  import etree

from .hyphenator import Hyphenator

hyphenate_bp = Blueprint('hyphenate', __name__)

from config import PROJECTS_DIR

# ── Config ────────────────────────────────────────────────────────────────────
DICT_ZIP       = '/home/apps/.config/calibre/plugins/hyphthisdicts.zip'
DICT_NAME      = 'cat.dic'
XHTML_NS       = 'http://www.w3.org/1999/xhtml'
SKIP_FILES     = {'full.xhtml', 'nav.xhtml'}

MIN_WORD_LEN   = 5
LEFT_MIN       = 2
RIGHT_MIN      = 2
TAGS_IGNORE    = ['h1', 'h2', 'h3']

SOFT_HYPHEN    = '\u00AD'
_WORD_RE       = re.compile(r'\w+|[^\w]', re.UNICODE)

# ── Hyphenator singleton ──────────────────────────────────────────────────────
_hyph = None

def _get_hyphenator():
    global _hyph
    if _hyph is not None:
        return _hyph
    if not os.path.exists(DICT_ZIP):
        raise RuntimeError(f'Dictionary zip not found: {DICT_ZIP}')
    with zipfile.ZipFile(DICT_ZIP) as z:
        if DICT_NAME not in z.namelist():
            raise RuntimeError(f'{DICT_NAME} not found in {DICT_ZIP}')
        tmp = tempfile.NamedTemporaryFile(suffix='.dic', delete=False)
        tmp.write(z.read(DICT_NAME))
        tmp.close()
    _hyph = Hyphenator(tmp.name, left=LEFT_MIN, right=RIGHT_MIN)
    return _hyph


# ── XPath query builder ───────────────────────────────────────────────────────
def _build_query():
    conditions = ' and '.join(f"local-name() != '{t}'" for t in TAGS_IGNORE)
    query      = f'//h:body//*[{conditions}]//text()'
    ignore_set = {f'{{{XHTML_NS}}}{t}' for t in TAGS_IGNORE}
    return ignore_set, query


# ── Per-file processing ───────────────────────────────────────────────────────
def _hyphenate_file(filepath, hyph):
    ignore_set, query = _build_query()
    ns     = {'h': XHTML_NS}
    parser = etree.XMLParser(recover=True, encoding='utf-8')

    with open(filepath, 'rb') as f:
        tree = etree.parse(f, parser)

    # Try namespaced query first; fall back to plain query for files without xmlns
    text_nodes = tree.xpath(query, namespaces=ns)
    if not text_nodes:
        conditions_plain = ' and '.join(f"local-name() != '{t}'" for t in TAGS_IGNORE)
        text_nodes       = tree.xpath(f'//body//*[{conditions_plain}]//text()')

    for t in text_nodes:
        parent = t.getparent()
        if parent is None:
            continue
        tag_local = parent.tag.split('}')[-1] if '}' in parent.tag else parent.tag
        if tag_local in TAGS_IGNORE:
            continue
        # Strip any existing soft hyphens before hyphenating — makes the
        # operation idempotent (safe to run multiple times on the same file)
        clean_t = t.replace(SOFT_HYPHEN, '')

        # Split around {{TOKEN}} patterns — hyphenate only non-token segments
        _TOKEN_RE = re.compile(r'(\{\{[A-Z_]+\}\})')
        segments = _TOKEN_RE.split(clean_t)
        newt = ''
        for seg in segments:
            if _TOKEN_RE.match(seg):
                # Token — pass through untouched
                newt += seg
            else:
                for w in _WORD_RE.findall(seg):
                    if len(w) < MIN_WORD_LEN or '-' in w:
                        newt += w
                    else:
                        newt += hyph.inserted(w).replace('-', SOFT_HYPHEN)
        if t.is_text:
            parent.text = newt
        elif t.is_tail:
            parent.tail = newt

    with open(filepath, 'wb') as f:
        f.write(etree.tostring(tree, xml_declaration=True,
                               pretty_print=True, encoding='UTF-8'))


# ── Endpoint ──────────────────────────────────────────────────────────────────
@hyphenate_bp.route('/api/projects/<project_id>/hyphenate', methods=['POST'])
def hyphenate_project(project_id):
    xhtml_dir = os.path.join(PROJECTS_DIR, project_id, 'xhtml')
    if not os.path.exists(xhtml_dir):
        return jsonify({'error': 'Project xhtml directory not found'}), 404

    files = sorted(
        f for f in os.listdir(xhtml_dir)
        if f.endswith('.xhtml') and f not in SKIP_FILES
    )
    if not files:
        return jsonify({'error': 'No files to hyphenate'}), 400

    try:
        hyph = _get_hyphenator()
    except Exception as e:
        return jsonify({'error': f'Could not load hyphenator: {e}'}), 500

    processed, errors = [], []
    for filename in files:
        try:
            _hyphenate_file(os.path.join(xhtml_dir, filename), hyph)
            processed.append(filename)
        except Exception as e:
            errors.append({'file': filename, 'error': str(e)})

    return jsonify({'ok': True, 'processed': processed, 'errors': errors})


@hyphenate_bp.route('/api/projects/<project_id>/dehyphenate', methods=['POST'])
def dehyphenate_project(project_id):
    xhtml_dir = os.path.join(PROJECTS_DIR, project_id, 'xhtml')
    if not os.path.exists(xhtml_dir):
        return jsonify({'error': 'Project xhtml directory not found'}), 404

    files = sorted(
        f for f in os.listdir(xhtml_dir)
        if f.endswith('.xhtml') and f not in SKIP_FILES
    )
    if not files:
        return jsonify({'error': 'No files to process'}), 400

    processed, errors = [], []
    for filename in files:
        try:
            path = os.path.join(xhtml_dir, filename)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            cleaned = content.replace(SOFT_HYPHEN, '')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            processed.append(filename)
        except Exception as e:
            errors.append({'file': filename, 'error': str(e)})

    return jsonify({'ok': True, 'processed': processed, 'errors': errors})