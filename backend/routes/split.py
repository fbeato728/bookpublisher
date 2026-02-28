import os
import json
import re
from flask import Blueprint, request, jsonify
from lxml import etree

split_bp = Blueprint('split', __name__)

PROJECTS_DIR = '/srv/bookpublisher/projects'
GLOBAL_DIR   = '/srv/bookpublisher/global'

XHTML_TEMPLATE = """<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <link rel="stylesheet" href="../styles/main.css" type="text/css"/>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>
{body}
  </body>
</html>"""

# Namespace declarations that belong only on <html>, not on every element
_NS_ATTRS = re.compile(
    r'\s+xmlns(?::\w+)?="[^"]*"',
    re.IGNORECASE
)

def _serialize_element(el):
    """Serialize a body element to string, stripping redundant namespace declarations."""
    raw = etree.tostring(el, encoding='unicode', pretty_print=True)
    return _NS_ATTRS.sub('', raw)


@split_bp.route('/api/projects/<project_id>/full-xhtml', methods=['GET'])
def get_full_xhtml(project_id):
    """Return the full.xhtml content as text."""
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', 'full.xhtml')
    if not os.path.exists(path):
        return jsonify({'error': 'full.xhtml not found'}), 404
    with open(path, encoding='utf-8') as f:
        content = f.read()
    return jsonify({'content': content})


@split_bp.route('/api/projects/<project_id>/split', methods=['POST'])
def apply_splits(project_id):
    """
    Apply split points to full.xhtml and generate chapter files.

    Expects JSON:
    {
      "splits": [
        {"before_index": 0, "type": "chapter", "name": "Chapter 1", "filename": "1000_chapter_1"},
        {"before_index": 5, "type": "chapter", "name": "Chapter 2", "filename": "1100_chapter_2"},
        ...
      ]
    }
    before_index: index of the paragraph/element in the body before which the split occurs.
    0 means this split starts at the very first element.
    """
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    meta_path   = os.path.join(project_dir, 'meta.json')
    full_path   = os.path.join(project_dir, 'xhtml', 'full.xhtml')
    xhtml_dir   = os.path.join(project_dir, 'xhtml')

    if not os.path.exists(full_path):
        return jsonify({'error': 'full.xhtml not found'}), 404

    with open(meta_path) as f:
        meta = json.load(f)
    book_title = meta.get('title', 'Untitled')

    data   = request.json
    splits = data.get('splits', [])

    if not splits:
        return jsonify({'error': 'No splits provided'}), 400

    # Parse the full XHTML
    parser = etree.XMLParser(recover=True, encoding='utf-8')
    with open(full_path, 'rb') as f:
        tree = etree.parse(f, parser)

    ns = {'x': 'http://www.w3.org/1999/xhtml'}
    body = tree.find('.//x:body', ns)
    if body is None:
        body = tree.find('.//body')
    if body is None:
        return jsonify({'error': 'Could not parse body from full.xhtml'}), 500

    # Get all direct children of body as a list
    elements = list(body)
    total = len(elements)

    # Sort splits by before_index
    splits_sorted = sorted(splits, key=lambda s: s['before_index'])

    # Build chunks: each chunk is a list of elements
    chunks = []
    for i, split in enumerate(splits_sorted):
        start = split['before_index']
        end   = splits_sorted[i+1]['before_index'] if i+1 < len(splits_sorted) else total
        chunks.append({
            'type':     split['type'],
            'name':     split['name'],
            'filename': split['filename'],
            'elements': elements[start:end]
        })

    # Write each chunk as an XHTML file
    saved = []
    for chunk in chunks:
        body_content = '\n'.join(_serialize_element(el) for el in chunk['elements'])

        xhtml = XHTML_TEMPLATE.format(
            title=f"{book_title} — {chunk['name']}",
            body=body_content
        )

        filename = chunk['filename'] + '.xhtml'
        filepath = os.path.join(xhtml_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(xhtml)

        saved.append({
            'filename': filename,
            'type':     chunk['type'],
            'name':     chunk['name'],
        })
        print(f"Saved: {filename}")

    # Update meta with chapter list
    meta['chapters'] = saved
    meta['status']   = 'split'
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    return jsonify({'saved': saved})


@split_bp.route('/api/projects/<project_id>/chapters', methods=['GET'])
def list_chapters(project_id):
    """List all chapter XHTML files for a project."""
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404
    with open(meta_path) as f:
        meta = json.load(f)
    return jsonify(meta.get('chapters', []))


@split_bp.route('/api/projects/<project_id>/chapters/<filename>', methods=['GET'])
def get_chapter(project_id, filename):
    """Get content of a specific chapter file."""
    if not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    with open(path, encoding='utf-8') as f:
        content = f.read()
    return jsonify({'content': content, 'filename': filename})


@split_bp.route('/api/projects/<project_id>/chapters/<filename>', methods=['DELETE'])
def delete_chapter(project_id, filename):
    """Delete a chapter file and remove it from meta.json."""
    if not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    os.remove(path)
    # Remove from meta.json chapter list
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        meta['chapters'] = [c for c in meta.get('chapters', []) if c.get('filename') != filename]
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
    return jsonify({'ok': True})


@split_bp.route('/api/projects/<project_id>/chapters/<filename>', methods=['PUT'])
def save_chapter(project_id, filename):
    """Save updated content of a chapter file."""
    if not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    content = request.json.get('content', '')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'ok': True})


GLOBAL_TEMPLATES = '/srv/bookpublisher/global/templates'

CHAPTER_RE = re.compile(r'^\d{4}_')  # chapter files start with 4 digits + underscore
SKIP_FILES  = {'full.xhtml', 'nav.xhtml'}

@split_bp.route('/api/projects/<project_id>/xhtml', methods=['GET'])
def list_xhtml_files(project_id):
    """List structural (non-chapter) XHTML files in the project xhtml dir."""
    xhtml_dir = os.path.join(PROJECTS_DIR, project_id, 'xhtml')
    if not os.path.exists(xhtml_dir):
        return jsonify([])
    files = sorted(
        f for f in os.listdir(xhtml_dir)
        if f.endswith('.xhtml')
        and f not in SKIP_FILES
        and not CHAPTER_RE.match(f)
    )
    return jsonify(files)

BLANK_XHTML_TEMPLATE = """<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <link rel="stylesheet" href="../styles/main.css" type="text/css"/>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>
    <p class="normalText"></p>
  </body>
</html>"""

@split_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['POST'])
def create_xhtml_file(project_id, filename):
    """Create a new blank XHTML file in the project xhtml dir."""
    if not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if os.path.exists(path):
        return jsonify({'error': 'File already exists'}), 409
    title = os.path.splitext(filename)[0]
    content = BLANK_XHTML_TEMPLATE.format(title=title)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'ok': True, 'filename': filename, 'content': content})

@split_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['GET'])
def get_xhtml_file(project_id, filename):
    """Get any XHTML file — project file first, then global template fallback."""
    if not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    content = None
    source  = None

    # 1. Project xhtml dir
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            content = f.read()
        source = 'project'
    else:
        # 2. Global templates dir
        tmpl = os.path.join(GLOBAL_TEMPLATES, filename)
        if os.path.exists(tmpl):
            with open(tmpl, encoding='utf-8') as f:
                content = f.read()
            source = 'global'

    if content is None:
        return jsonify({'error': 'File not found'}), 404

    # Fill {{TOKEN}} placeholders for preview using project metadata
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        tokens = {
            '{{TITLE}}':           meta.get('title', ''),
            '{{AUTHOR}}':          meta.get('author', ''),
            '{{COVER_IMAGE}}':     meta.get('digital_cover', ''),
            '{{FIRST_EDITION}}':   meta.get('first_edition', ''),
            '{{ORIGINAL_TITLE}}':  meta.get('original_title', meta.get('title', '')),
            '{{ORIGINAL_YEAR}}':   meta.get('original_year', ''),
            '{{ORIGINAL_AUTHOR}}': meta.get('original_author', meta.get('author', '')),
            '{{TRANSLATOR}}':      meta.get('translator', ''),
            '{{TRANSLATION_YEAR}}':meta.get('translation_year', ''),
            '{{ISBN}}':            meta.get('isbn', ''),
            '{{DEPOT_LEGAL}}':     meta.get('depot_legal', ''),
        }
        for token, value in tokens.items():
            content = content.replace(token, value)

    return jsonify({'content': content, 'filename': filename, 'source': source})


@split_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['PUT'])
def save_xhtml_file(project_id, filename):
    """Save any XHTML file to the project xhtml dir."""
    if not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    content = request.json.get('content', '')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'ok': True, 'source': 'project'})


@split_bp.route('/api/projects/<project_id>/styles/<filename>', methods=['GET'])
def get_css_file(project_id, filename):
    """Get a CSS file — project styles dir first, then global fallback."""
    if not filename.endswith('.css') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    # 1. Project styles dir
    path = os.path.join(PROJECTS_DIR, project_id, 'styles', filename)
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'filename': filename, 'source': 'project'})

    # 2. Global styles dir
    global_path = os.path.join(GLOBAL_DIR, 'styles', filename)
    if os.path.exists(global_path):
        with open(global_path, encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'filename': filename, 'source': 'global'})

    return jsonify({'error': 'File not found'}), 404


@split_bp.route('/api/projects/<project_id>/styles/<filename>', methods=['PUT'])
def save_css_file(project_id, filename):
    """Save a CSS file to the project styles dir."""
    if not filename.endswith('.css') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    styles_dir = os.path.join(PROJECTS_DIR, project_id, 'styles')
    os.makedirs(styles_dir, exist_ok=True)
    path = os.path.join(styles_dir, filename)
    content = request.json.get('content', '')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'ok': True, 'source': 'project'})