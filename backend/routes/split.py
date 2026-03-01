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

    # Chapter 0: content before the first split marker (only if non-empty)
    chunks = []
    first_index = splits_sorted[0]['before_index'] if splits_sorted else 0
    if first_index > 0:
        pre_elements = elements[0:first_index]
        if pre_elements:
            chunks.append({
                'type':     'chapter',
                'name':     'chapter 0',
                'filename': '0000_chapter_0',
                'elements': pre_elements,
            })

    # Build chunks: each chunk is a list of elements
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


@split_bp.route('/api/projects/<project_id>/chapters/sync', methods=['POST'])
def sync_chapters(project_id):
    """
    Atomically apply chapter renames, deletions and reorder.
    Body: {
      "chapters": [{"filename": "...", "name": "...", "type": "..."}, ...],
      "delete":   ["old_filename.xhtml", ...]
    }
    Renames are inferred from name changes (slug regenerated from new name).
    Order in chapters list becomes the canonical spine order.
    Both meta.json and build_config.json are updated.
    """
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    meta_path   = os.path.join(project_dir, 'meta.json')
    bc_path     = os.path.join(project_dir, 'build_config.json')
    xhtml_dir   = os.path.join(project_dir, 'xhtml')

    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404

    data     = request.json or {}
    desired  = data.get('chapters', [])    # [{filename, name, type}, ...]
    to_delete = data.get('delete', [])     # [filename, ...]

    errors = []

    # 1. Delete files
    for fname in to_delete:
        if '/' in fname or '..' in fname:
            continue
        fpath = os.path.join(xhtml_dir, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception as e:
                errors.append(f'Could not delete {fname}: {e}')

    # 2. Rename files where name changed → new slug filename
    #    We keep the 4-digit prefix and type, regenerate slug from new name
    final_chapters = []
    for ch in desired:
        old_filename = ch.get('filename', '')
        new_name     = ch.get('name', '').strip()
        ch_type      = ch.get('type', 'chapter')

        if not old_filename or '/' in old_filename or '..' in old_filename:
            continue

        # Regenerate filename from new name
        parts = re.match(r'^(\d{4})_(\w+)_(.*?)\.xhtml$', old_filename)
        if parts and new_name:
            prefix   = parts.group(1)
            slug     = re.sub(r'-+', '-', re.sub(r'[^a-z0-9]', '-', new_name.lower())).strip('-')
            new_filename = f"{prefix}_{ch_type}_{slug}.xhtml"
        else:
            new_filename = old_filename

        old_path = os.path.join(xhtml_dir, old_filename)
        new_path = os.path.join(xhtml_dir, new_filename)

        if old_filename != new_filename and os.path.exists(old_path):
            if os.path.exists(new_path):
                errors.append(f'Cannot rename {old_filename}: {new_filename} already exists')
                new_filename = old_filename  # keep old
            else:
                try:
                    os.rename(old_path, new_path)
                except Exception as e:
                    errors.append(f'Could not rename {old_filename}: {e}')
                    new_filename = old_filename

        final_chapters.append({'filename': new_filename, 'name': new_name or new_filename, 'type': ch_type})

    # 3. Update meta.json
    with open(meta_path) as f:
        meta = json.load(f)
    meta['chapters'] = final_chapters
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    # 4. Update build_config.json
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        chapter_entries = [{'filename': c['filename'], 'name': c['name'], 'type': c['type'], 'enabled': True}
                           for c in final_chapters]
        for profile in ('digital', 'print'):
            if profile in bc:
                bc[profile]['chapters'] = chapter_entries
        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=2)

    return jsonify({'ok': True, 'chapters': final_chapters, 'errors': errors})


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


@split_bp.route('/api/projects/<project_id>/styles', methods=['GET'])
def list_css_files(project_id):
    """List CSS files in the project styles dir."""
    styles_dir = os.path.join(PROJECTS_DIR, project_id, 'styles')
    if not os.path.exists(styles_dir):
        return jsonify([])
    files = sorted(f for f in os.listdir(styles_dir) if f.endswith('.css'))
    return jsonify(files)


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


@split_bp.route('/api/projects/<project_id>/chapters', methods=['POST'])
def create_chapter(project_id):
    """Create a new blank chapter file and add it to meta.json."""
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404

    data     = request.json or {}
    filename = data.get('filename', '').strip()
    name     = data.get('name', '').strip()
    ch_type  = data.get('type', 'chapter').strip()

    if not filename or not filename.endswith('.xhtml') or '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400

    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if os.path.exists(path):
        return jsonify({'error': 'File already exists'}), 409

    with open(meta_path) as f:
        meta = json.load(f)

    title = meta.get('title', 'Untitled')
    content = BLANK_XHTML_TEMPLATE.format(title=f"{title} — {name or filename}")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    chapter_entry = {'filename': filename, 'type': ch_type, 'name': name or filename}
    meta.setdefault('chapters', []).append(chapter_entry)
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    return jsonify({'ok': True, 'chapter': chapter_entry})


@split_bp.route('/api/projects/<project_id>/chapters/<old_filename>/rename', methods=['PUT'])
def rename_chapter(project_id, old_filename):
    """Rename a chapter file on disk and update meta.json and build_config.json."""
    if not old_filename.endswith('.xhtml') or '/' in old_filename or '..' in old_filename:
        return jsonify({'error': 'Invalid filename'}), 400

    data         = request.json or {}
    new_filename = data.get('new_filename', '').strip()
    new_name     = data.get('new_name', '').strip()

    if not new_filename or not new_filename.endswith('.xhtml') or '/' in new_filename or '..' in new_filename:
        return jsonify({'error': 'Invalid new filename'}), 400

    project_dir = os.path.join(PROJECTS_DIR, project_id)
    xhtml_dir   = os.path.join(project_dir, 'xhtml')
    old_path    = os.path.join(xhtml_dir, old_filename)
    new_path    = os.path.join(xhtml_dir, new_filename)

    if not os.path.exists(old_path):
        return jsonify({'error': 'File not found'}), 404
    if os.path.exists(new_path) and old_filename != new_filename:
        return jsonify({'error': 'Target filename already exists'}), 409

    os.rename(old_path, new_path)

    # Update meta.json
    meta_path = os.path.join(project_dir, 'meta.json')
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        for ch in meta.get('chapters', []):
            if ch.get('filename') == old_filename:
                ch['filename'] = new_filename
                if new_name:
                    ch['name'] = new_name
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)

    # Update build_config.json
    bc_path = os.path.join(project_dir, 'build_config.json')
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            if profile not in bc:
                continue
            for ch in bc[profile].get('chapters', []):
                if ch.get('filename') == old_filename:
                    ch['filename'] = new_filename
                    if new_name:
                        ch['name'] = new_name
        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=2)

    return jsonify({'ok': True, 'old_filename': old_filename, 'new_filename': new_filename})