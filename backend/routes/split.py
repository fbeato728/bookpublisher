import os
import json
import re
from flask import Blueprint, request, jsonify
from lxml import etree

split_bp = Blueprint('split', __name__)

from config import PROJECTS_DIR, GLOBAL_DIR

GLOBAL_TEMPLATES = os.path.join(GLOBAL_DIR, 'templates')

# Load config from global config file
CONFIG_PATH = os.path.join(GLOBAL_DIR, 'config', 'split.json')


def load_config():
    """Load split.py config from JSON file."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}")

CONFIG = load_config()

# Compile regex patterns from config
CHAPTER_RE = re.compile(CONFIG['chapters']['naming']['pattern'])
_NS_ATTRS = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"', re.IGNORECASE)

SKIP_FILES = {'full.xhtml', 'nav.xhtml'}


def build_xhtml_template(title, body, counter):
    """Build XHTML chapter template from config."""
    xhtml_cfg = CONFIG['xhtml']
    ns_html = xhtml_cfg['namespaces']['html']
    ns_epub = xhtml_cfg['namespaces']['epub']
    stylesheet = xhtml_cfg['stylesheet']
    body_class = xhtml_cfg['templates']['chapter'].get('body_class', '')
    body_attr = f' class="{body_class}"' if body_class else ''

    autopaging = xhtml_cfg.get('autopaging', True)
    div_id = f' id="ch{counter:02d}"' if autopaging else ''    

    return (
        f"{xhtml_cfg['declaration']}\n"
        f"<html xmlns=\"{ns_html}\" xmlns:epub=\"{ns_epub}\">\n"
        f"  <head>\n"
        f"    <link rel=\"{stylesheet['rel']}\" href=\"{stylesheet['href']}\" type=\"{stylesheet['type']}\"/>\n"
        f"    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"/>\n"
        f"    <title>{title}</title>\n"
        f"    <meta http-equiv=\"Content-Type\" content=\"{xhtml_cfg['meta']['content_type']}\"/>\n"
        f"  </head>\n"
        f"  <body{body_attr}>\n"
        f"      <div class=\"chapterBody\"{div_id}>\n"
        f"{body}\n"
        f"      </div>\n"
        f"  </body>\n"
        f"</html>"
    )

def build_blank_xhtml_template(title):
    """Build blank XHTML template from config."""
    xhtml_cfg = CONFIG['xhtml']
    blank_cfg = xhtml_cfg['templates']['blank']
    ns_html = xhtml_cfg['namespaces']['html']
    ns_epub = xhtml_cfg['namespaces']['epub']
    stylesheet = xhtml_cfg['stylesheet']
    
    return (
        f"{xhtml_cfg['declaration']}\n"
        f"<html xmlns=\"{ns_html}\" xmlns:epub=\"{ns_epub}\">\n"
        f"  <head>\n"
        f"    <link rel=\"{stylesheet['rel']}\" href=\"{stylesheet['href']}\" type=\"{stylesheet['type']}\"/>\n"
        f"    <title>{title}</title>\n"
        f"    <meta http-equiv=\"Content-Type\" content=\"{xhtml_cfg['meta']['content_type']}\"/>\n"
        f"  </head>\n"
        f"  <body>\n"
        f"    {blank_cfg['body_content']}\n"
        f"  </body>\n"
        f"</html>"
    )


def is_safe_filename(filename):
    """Check if filename is safe (no path traversal, valid extensions)."""
    unsafe_chars = CONFIG['files']['unsafe_path_chars']
    for char in unsafe_chars:
        if char in filename:
            return False
    return True


def get_error_message(error_key, **kwargs):
    """Get error message from config, with optional substitutions."""
    msg = CONFIG['messages']['errors'].get(error_key, error_key)
    if kwargs:
        msg = msg.format(**kwargs)
    return msg


from routes.utils import fill_tokens

def _flatten_meta(meta):
    """Normalize meta.json — handles both old flat and new nested format."""
    if 'metadata' not in meta:
        return meta
    flat = {k: v for k, v in meta.items() if k != 'metadata'}
    flat.update(meta.get('metadata', {}))
    return flat

def _nest_meta(flat):
    """Write meta.json in nested format."""
    _TOP = {'id', 'status', 'chapters', 'original_file', 'xhtml_file',
            'cover_image', 'digital_inside_cover', 'print_inside_cover'}
    top  = {k: v for k, v in flat.items() if k in _TOP}
    book = {k: v for k, v in flat.items() if k not in _TOP}
    top['metadata'] = book
    return top


def _serialize_element(el):
    """Serialize a body element to string, stripping redundant namespace declarations.
    Forces explicit closing tags on empty elements to prevent self-closing span issues.
    """
    # Force explicit closing tags on empty elements
    for node in el.iter():
        if node.text is None and len(node) == 0:
            node.text = ''
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
    meta_path   = os.path.join(project_dir, CONFIG['paths']['files']['meta'])
    bc_path     = os.path.join(project_dir, CONFIG['paths']['files']['build_config'])
    full_path   = os.path.join(project_dir, CONFIG['paths']['subdirs']['xhtml'], CONFIG['paths']['files']['full_xhtml'])
    xhtml_dir   = os.path.join(project_dir, CONFIG['paths']['subdirs']['xhtml'])

    if not os.path.exists(full_path):
        return jsonify({'error': get_error_message('full_xhtml_not_found')}), 404

    with open(meta_path) as f:
        _raw_meta = json.load(f)
    meta = _flatten_meta(_raw_meta)
    book_title = meta.get('title', CONFIG['metadata']['defaults']['title'])

    data   = request.json
    splits = data.get('splits', [])

    if not splits:
        return jsonify({'error': get_error_message('no_splits_provided')}), 400

    # Parse the full XHTML
    parser = etree.XMLParser(recover=True, encoding='utf-8')
    with open(full_path, 'rb') as f:
        tree = etree.parse(f, parser)

    ns = {'x': CONFIG['xhtml']['namespaces']['html']}
    body = tree.find('.//x:body', ns)
    if body is None:
        body = tree.find('.//body')
    if body is None:
        return jsonify({'error': get_error_message('parse_error')}), 500

    # Get all direct children of body as a list
    elements = list(body)
    total = len(elements)

    # Sort splits by before_index
    splits_sorted = sorted(splits, key=lambda s: s['before_index'])

    # Chapter 0: content before the first split marker (only if non-empty)
    # Build chunks — discard content before first split marker
    chunks = []
    for i, split in enumerate(splits_sorted):
        start   = split['before_index']
        end     = splits_sorted[i+1]['before_index'] if i+1 < len(splits_sorted) else total
        ch_type = split.get('type', 'chapter').strip()
        name    = split.get('name', '').strip()
        slug    = re.sub(r'_+', '_', re.sub(r'[^a-z0-9]', '_', name.lower())).strip('_') or 'untitled'
        if ch_type in ('front_matter', 'back_matter'):
            filename = slug + CONFIG['files']['allowed_extensions']['xhtml']
        else:
            filename = f"{ch_type}_{slug}" + CONFIG['files']['allowed_extensions']['xhtml']
        chunks.append({
            'type':         ch_type,
            'name':         name,
            'filename':     filename,
            'elements':     elements[start:end],
            'before_index': split['before_index'],
        })

    # Write XHTML files and collect entries by destination
    chapter_entries      = []
    front_matter_entries = []
    back_matter_entries  = []
    chapter_counter = 0

    for chunk in chunks:
        body_content = '\n'.join(_serialize_element(el) for el in chunk['elements'])

        counter = None
        if chunk['type'] == 'chapter':
            chapter_counter += 1
            counter = chapter_counter

        xhtml = build_xhtml_template(f"{book_title} \u2014 {chunk['name']}", body_content, counter)
        filepath = os.path.join(xhtml_dir, chunk['filename'])
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(xhtml)
        print(CONFIG['messages']['info']['saved'].format(filename=chunk['filename']))

        entry = {'filename': chunk['filename'], 'enabled': True}
        if chunk['type'] == 'front_matter':
            front_matter_entries.append(entry)
        elif chunk['type'] == 'back_matter':
            back_matter_entries.append(entry)
        else:
            chapter_entries.append({'filename': chunk['filename'], 'type': chunk['type'], 'name': chunk['name'], 'before_index': chunk['before_index']})

    # Update meta.json — only body chapters
    meta['chapters'] = chapter_entries
    meta['status']   = CONFIG['metadata']['status_values']['split']
    out = _nest_meta(meta) if 'metadata' in _raw_meta else meta
    with open(meta_path, 'w') as f:
        json.dump(out, f, indent=CONFIG['files']['json_indent'])

    # Update build_config.json
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            if profile not in bc:
                bc[profile] = {'front_matter': [], 'chapters': [], 'back_matter': []}

            # Front matter from splits — nav:False for digital, toc:False for print
            fm_entries = []
            for e in front_matter_entries:
                entry = dict(e)
                if profile == 'digital':
                    entry['nav'] = False
                if profile == 'print':
                    entry['toc'] = False
                fm_entries.append(entry)
            bc[profile]['front_matter'] = bc[profile].get('front_matter', []) + fm_entries

            # Chapters — nav:True for digital, pag:True for print
            ch_list = []
            for c in chapter_entries:
                entry = {'filename': c['filename'], 'type': c['type'], 'name': c['name'], 'enabled': True}
                if profile == 'digital':
                    entry['nav'] = True
                if profile == 'print':
                    entry['pag'] = True
                ch_list.append(entry)
            bc[profile]['chapters'] = ch_list

            # Back matter from splits — nav:False for digital
            bm_entries = []
            for e in back_matter_entries:
                entry = dict(e)
                if profile == 'digital':
                    entry['nav'] = False
                bm_entries.append(entry)
            bc[profile]['back_matter'] = bm_entries + bc[profile].get('back_matter', [])

        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=CONFIG['files']['json_indent'])

    return jsonify({'saved': chapter_entries + front_matter_entries + back_matter_entries})


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
    meta_path   = os.path.join(project_dir, CONFIG['paths']['files']['meta'])
    bc_path     = os.path.join(project_dir, CONFIG['paths']['files']['build_config'])
    xhtml_dir   = os.path.join(project_dir, CONFIG['paths']['subdirs']['xhtml'])

    if not os.path.exists(meta_path):
        return jsonify({'error': get_error_message('project_not_found')}), 404

    data     = request.json or {}
    desired  = data.get('chapters', [])    # [{filename, name, type}, ...]
    to_delete = data.get('delete', [])     # [filename, ...]

    errors = []

    # 1. Delete files
    for fname in to_delete:
        if not is_safe_filename(fname):
            continue
        fpath = os.path.join(xhtml_dir, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception as e:
                errors.append(get_error_message('delete_error', filename=fname, error=str(e)))

    # 2. Rename files where name changed → new slug filename
    #    We keep the 4-digit prefix and type, regenerate slug from new name
    final_chapters = []
    for ch in desired:
        old_filename = ch.get('filename', '')
        new_name     = ch.get('name', '').strip()
        ch_type      = ch.get('type', CONFIG['chapters']['defaults']['type'])

        if not old_filename or not is_safe_filename(old_filename):
            continue

        # Regenerate filename from new name
        parts = re.match(r'^(\w+)_(.*?)\.xhtml$', old_filename)
        if parts and new_name:
            ch_type  = parts.group(1)
            slug     = re.sub(r'-+', '-', re.sub(r'[^a-z0-9]', '-', new_name.lower())).strip('-')
            new_filename = f"{ch_type}_{slug}{CONFIG['files']['allowed_extensions']['xhtml']}"
        else:
            new_filename = old_filename

        old_path = os.path.join(xhtml_dir, old_filename)
        new_path = os.path.join(xhtml_dir, new_filename)

        if old_filename != new_filename and os.path.exists(old_path):
            if os.path.exists(new_path):
                errors.append(get_error_message('target_exists'))
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
        _raw_meta = json.load(f)
    meta = _flatten_meta(_raw_meta)
    meta['chapters'] = final_chapters
    out = _nest_meta(meta) if 'metadata' in _raw_meta else meta
    with open(meta_path, 'w') as f:
        json.dump(out, f, indent=CONFIG['files']['json_indent'])

    # 4. Update build_config.json
    # Note: build_config.json maintains spine order as front_matter → chapters → back_matter
    # We update the chapters list while preserving the front/back matter structure.
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        chapter_entries = [{'filename': c['filename'], 'name': c['name'], 'type': c['type'], 'enabled': True}
                           for c in final_chapters]
        for profile in ('digital', 'print'):
            if profile in bc:
                bc[profile]['chapters'] = chapter_entries
        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=CONFIG['files']['json_indent'])

    return jsonify({'ok': True, 'chapters': final_chapters, 'errors': errors})

@split_bp.route('/api/projects/<project_id>/chapters/delete-all', methods=['POST'])
def delete_all_chapters(project_id):
    """
    Delete all chapter xhtml files from disk, clear chapters from
    build_config.json, and reset meta.json status to 'converted'.
    Front/back matter files and full.xhtml are never touched.
    Called by the Split panel "Delete chapters" button.
    """
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    meta_path   = os.path.join(project_dir, CONFIG['paths']['files']['meta'])
    bc_path     = os.path.join(project_dir, CONFIG['paths']['files']['build_config'])
    xhtml_dir   = os.path.join(project_dir, CONFIG['paths']['subdirs']['xhtml'])

    if not os.path.exists(meta_path):
        return jsonify({'error': get_error_message('project_not_found')}), 404

    errors  = []
    deleted = []

    # 1. Identify and delete chapter files only — files matching the chapter
    #    naming pattern (NNNN_type_name.xhtml). Never touches full.xhtml or matter files.
    if os.path.exists(xhtml_dir):
        for fname in os.listdir(xhtml_dir):
            if CHAPTER_RE.match(fname):
                fpath = os.path.join(xhtml_dir, fname)
                try:
                    os.remove(fpath)
                    deleted.append(fname)
                except Exception as e:
                    errors.append(get_error_message('delete_error', filename=fname, error=str(e)))

    # 2. Clear chapters list from build_config.json, preserve front/back matter untouched
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            if profile in bc:
                bc[profile]['chapters'] = []
        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=CONFIG['files']['json_indent'])

    # 3. Reset meta.json: clear chapters array and set status back to 'converted'
    with open(meta_path) as f:
        _raw_meta = json.load(f)
    meta = _flatten_meta(_raw_meta)
    meta['chapters'] = []
    meta['status']   = 'converted'
    out = _nest_meta(meta) if 'metadata' in _raw_meta else meta
    with open(meta_path, 'w') as f:
        json.dump(out, f, indent=CONFIG['files']['json_indent'])

    return jsonify({'ok': True, 'deleted': deleted, 'errors': errors})