import os
import uuid
import json
import re
import shutil
from flask import Blueprint, request, jsonify
from scripts.docx_converter import convert_docx, save_full_xhtml
from utils import slugify

projects_bp = Blueprint('projects', __name__)

from config import PROJECTS_DIR, GLOBAL_DIR

GLOBAL_TEMPLATES = os.path.join(GLOBAL_DIR, 'templates')
TOKENS_PATH      = os.path.join(GLOBAL_DIR, 'config', 'tokens.json')

# ── meta.json helpers ─────────────────────────────────────────────────────────

# Metadata fields that live at top level (not under 'metadata' key)
_TOP_LEVEL_KEYS = {'id', 'status', 'chapters', 'original_file', 'xhtml_file',
                   'cover_image', 'digital_inside_cover', 'print_inside_cover'}

def _flatten_meta(meta):
    """Normalize meta.json to a flat dict regardless of old/new format.
    New format has a 'metadata' subkey; old format is flat.
    Always returns a flat dict safe for API responses and build-time reads."""
    if 'metadata' not in meta:
        return meta  # old flat format — return as-is
    flat = {k: v for k, v in meta.items() if k != 'metadata'}
    flat.update(meta.get('metadata', {}))
    return flat

def _nest_meta(flat):
    """Convert a flat meta dict to nested format for writing to disk.
    Top-level keys stay at top level; all other fields go under 'metadata'."""
    top  = {k: v for k, v in flat.items() if k in _TOP_LEVEL_KEYS}
    book = {k: v for k, v in flat.items() if k not in _TOP_LEVEL_KEYS}
    result = top
    result['metadata'] = book
    return result

def _load_allowed_fields():
    """Return allowed metadata field names from tokens.json + OPF fields."""
    opf = {'title', 'author', 'language', 'publisher'}
    try:
        with open(TOKENS_PATH, encoding='utf-8') as f:
            tokens = json.load(f)
        for token_def in tokens.values():
            if token_def.get('ui') is False:
                continue
            if 'meta_field' in token_def:
                opf.add(token_def['meta_field'])
            for field in token_def.get('meta_fields', []):
                opf.add(field)
    except Exception:
        pass
    return opf

# Subfolders in global/templates that define front/back matter per profile
TEMPLATE_SUBFOLDERS = {
    'digital': {
        'front_matter': 'front_digital',
        'back_matter':  'back_digital',
    },
    'print': {
        'front_matter': 'front_print',
        'back_matter':  'back_print',
    },
}

# Common subfolders shared by both profiles
TEMPLATE_COMMON = {
    'front_matter': 'front_common',
    'back_matter':  'back_common',
}

# Order files at global/templates level — define combined order per profile+section
# e.g. order_front_digital.json, order_front_print.json, order_back_digital.json, order_back_print.json
ORDER_FILE_PATTERN = 'order_{section}_{profile}.json'


def _get_ordered_templates(profile, section):
    """Return ordered list of (filename, source_folder) for a profile+section.

    Reads order_{section}_{profile}.json from GLOBAL_TEMPLATES if present.
    That file lists filenames drawn from either the profile subfolder or the
    common subfolder. Falls back to profile-specific files then common files,
    both alphabetical, if no order file exists.
    """
    section_key = section.replace('_matter', '')  # 'front' or 'back'
    order_filename = f'order_{section_key}_{profile}.json'
    order_path = os.path.join(GLOBAL_TEMPLATES, order_filename)

    profile_folder = TEMPLATE_SUBFOLDERS[profile][section]
    common_folder  = TEMPLATE_COMMON[section]
    profile_dir = os.path.join(GLOBAL_TEMPLATES, profile_folder)
    common_dir  = os.path.join(GLOBAL_TEMPLATES, common_folder)

    # Build lookup: filename → source folder
    available = {}
    if os.path.isdir(profile_dir):
        for f in os.listdir(profile_dir):
            if f.endswith('.xhtml'):
                available[f] = profile_dir
    if os.path.isdir(common_dir):
        for f in os.listdir(common_dir):
            if f.endswith('.xhtml'):
                available[f] = common_dir

    if os.path.exists(order_path):
        try:
            with open(order_path, encoding='utf-8') as f:
                ordered_names = json.load(f)
            result = [(fname, available[fname]) for fname in ordered_names if fname in available]
            # Append any files not mentioned in order file
            mentioned = set(ordered_names)
            for fname, folder in sorted(available.items()):
                if fname not in mentioned:
                    result.append((fname, folder))
            return result
        except Exception:
            pass

    # Fallback: profile files first (alphabetical), then common (alphabetical)
    result = sorted((f, profile_dir) for f in available if available[f] == profile_dir)
    result += sorted((f, common_dir) for f in available if available[f] == common_dir)
    return result


@projects_bp.route('/api/projects', methods=['GET'])
def list_projects():
    projects = []
    if not os.path.exists(PROJECTS_DIR):
        return jsonify([])
    for pid in os.listdir(PROJECTS_DIR):
        meta_path = os.path.join(PROJECTS_DIR, pid, 'meta.json')
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                projects.append(json.load(f))
    projects = [_flatten_meta(p) for p in projects]
    projects.sort(key=lambda p: p.get('title', ''))
    return jsonify(projects)

@projects_bp.route('/api/projects', methods=['POST'])
def create_project():
    # Log everything received
    print("=== FORM DATA ===")
    print("form keys:", list(request.form.keys()))
    print("files keys:", list(request.files.keys()))
    for k, v in request.form.items():
        print(f"  {k} = '{v}'")
    print("=================")

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    title      = request.form.get('title', '').strip()
    author     = request.form.get('author', '').strip()
    project_id = request.form.get('project_id', '').strip()

    print(f"project_id='{project_id}' title='{title}' author='{author}'")

    if not title:
        return jsonify({'error': 'Book title is required'}), 400

    if not file.filename.endswith(('.docx', '.odt')):
        return jsonify({'error': 'Only DOCX or ODT files accepted'}), 400

    # Sanitize project_id — strip everything except letters, digits, hyphens
    project_id = re.sub(r'[^\w-]', '', project_id).lower()

    # Fall back to slugified title if still empty
    if not project_id:
        project_id = slugify(title) or str(uuid.uuid4())[:8]

    # Check duplicate
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if os.path.exists(project_dir):
        return jsonify({'error': f'Project "{project_id}" already exists'}), 400

    # Create folders
    for subdir in ['original', 'xhtml', 'images', 'styles', 'fonts', 'builds']:
        os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

    # Save original file
    original_path = os.path.join(project_dir, 'original', file.filename)
    file.save(original_path)

    # Convert DOCX to single XHTML
    images_dir = os.path.join(project_dir, 'images')
    xhtml = convert_docx(original_path, title, images_dir=images_dir)
    save_full_xhtml(xhtml, os.path.join(project_dir, 'xhtml'), title)

    # Copy global templates into project xhtml dir and build build_config.json
    xhtml_dir  = os.path.join(project_dir, 'xhtml')
    build_config = {'digital': {}, 'print': {}}
    for profile in ('digital', 'print'):
        build_config[profile] = {'front_matter': [], 'chapters': [], 'back_matter': []}
        for section in ('front_matter', 'back_matter'):
            for fname, src_dir in _get_ordered_templates(profile, section):
                shutil.copy2(os.path.join(src_dir, fname), os.path.join(xhtml_dir, fname))
                entry = {'filename': fname, 'enabled': True}
                if profile == 'digital':
                    entry['nav'] = False
                if profile == 'print' and section == 'front_matter':
                    entry['toc'] = False
                build_config[profile][section].append(entry)
    bc_path = os.path.join(project_dir, 'build_config.json')
    with open(bc_path, 'w') as f:
        json.dump(build_config, f, indent=2)

    # Copy all CSS files from global/styles into the project styles dir
    styles_dir = os.path.join(project_dir, 'styles')
    global_styles_dir = os.path.join(GLOBAL_DIR, 'styles')
    if os.path.exists(global_styles_dir):
        for css_file in os.listdir(global_styles_dir):
            if css_file.endswith('.css'):
                src = os.path.join(global_styles_dir, css_file)
                shutil.copy2(src, os.path.join(styles_dir, css_file))

    # Save metadata — nested format
    flat_meta = {
        'id': project_id,
        'title': title,
        'author': author,
        'language': 'ca',
        'publisher': 'BonPort',
        'original_file': file.filename,
        'status': 'converted',
        'xhtml_file': 'xhtml/full.xhtml',
    }
    meta = _nest_meta(flat_meta)
    with open(os.path.join(project_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"Created project: {project_id}")
    # Scan CSS files and build css_tokens_active.json immediately at creation
    # so the tokens panel is ready without requiring a manual sync first.
    try:
        sync_css_tokens(project_id)
    except Exception as e:
        print(f"Warning: css token sync failed at project creation: {e}")

    return jsonify(meta), 201

@projects_bp.route('/api/projects/<project_id>', methods=['GET'])
def get_project(project_id):
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404
    with open(meta_path) as f:
        return jsonify(_flatten_meta(json.load(f)))

@projects_bp.route('/api/projects/<project_id>', methods=['PATCH'])
def update_project_meta(project_id):
    """Update editable metadata fields in meta.json."""
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404
    with open(meta_path) as f:
        meta = json.load(f)
    allowed = _load_allowed_fields()
    flat = _flatten_meta(meta)
    data = request.json or {}
    for key, value in data.items():
        if key in allowed:
            flat[key] = value
    # Write back in same format as found on disk
    if 'metadata' in meta:
        out = _nest_meta(flat)
    else:
        out = flat
    with open(meta_path, 'w') as f:
        json.dump(out, f, indent=2)
    return jsonify({'ok': True, 'meta': flat})

@projects_bp.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    import shutil
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404
    shutil.rmtree(project_dir)
    return jsonify({'ok': True})

@projects_bp.route('/api/projects/<project_id>/reset', methods=['POST'])
def reset_project(project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404

    xhtml_dir = os.path.join(project_dir, 'xhtml')
    bc_path   = os.path.join(project_dir, 'build_config.json')
    meta_path = os.path.join(project_dir, 'meta.json')

    # Collect filenames referenced in front/back matter across both profiles
    keep_xhtml = {'full.xhtml', 'full_original.xhtml'}
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            for section in ('front_matter', 'back_matter'):
                for item in bc.get(profile, {}).get(section, []):
                    fname = item.get('filename') or item.get('id', '')
                    if fname:
                        keep_xhtml.add(fname)

    # Delete all xhtml files not in the keep set
    if os.path.exists(xhtml_dir):
        for fname in os.listdir(xhtml_dir):
            if fname not in keep_xhtml:
                os.remove(os.path.join(xhtml_dir, fname))

    # Clear chapters from build_config.json, keep front/back matter
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            if profile in bc:
                bc[profile]['chapters'] = []
        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=2)

    # Reset meta.json: clear chapters, set status
    with open(meta_path) as f:
        meta = json.load(f)
    flat = _flatten_meta(meta)
    flat['status'] = 'converted'
    flat['chapters'] = []
    out = _nest_meta(flat) if 'metadata' in meta else flat
    with open(meta_path, 'w') as f:
        json.dump(out, f, indent=2)

    return jsonify({'ok': True})

@projects_bp.route('/api/projects/<project_id>/reset_matter', methods=['POST'])
def reset_matter(project_id):
    """Delete front/back matter files for a profile and restore from global templates."""
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404

    data    = request.json or {}
    profile = data.get('profile', 'digital')
    if profile not in ('digital', 'print'):
        return jsonify({'error': 'Invalid profile'}), 400

    other   = 'print' if profile == 'digital' else 'digital'
    xhtml_dir = os.path.join(project_dir, 'xhtml')
    bc_path   = os.path.join(project_dir, 'build_config.json')

    with open(bc_path) as f:
        bc = json.load(f)

    # Collect filenames used by the OTHER profile's front/back matter
    other_files = set()
    for section in ('front_matter', 'back_matter'):
        for item in bc.get(other, {}).get(section, []):
            fname = item.get('filename', '')
            if fname:
                other_files.add(fname)

    # Delete files used only by this profile (not shared with other)
    for section in ('front_matter', 'back_matter'):
        for item in bc.get(profile, {}).get(section, []):
            fname = item.get('filename', '')
            if fname and fname not in other_files:
                fpath = os.path.join(xhtml_dir, fname)
                if os.path.exists(fpath):
                    os.remove(fpath)

    # Re-copy from global templates and rebuild config for this profile
    bc[profile]['front_matter'] = []
    bc[profile]['back_matter']  = []
    for section in ('front_matter', 'back_matter'):
        for fname, src_dir in _get_ordered_templates(profile, section):
            shutil.copy2(os.path.join(src_dir, fname), os.path.join(xhtml_dir, fname))
            entry = {'filename': fname, 'enabled': True}
            if profile == 'digital':
                entry['nav'] = False
            if profile == 'print' and section == 'front_matter':
                entry['toc'] = False
            bc[profile][section].append(entry)

    with open(bc_path, 'w') as f:
        json.dump(bc, f, indent=2)

    return jsonify({'ok': True, 'build_config': bc[profile]})

@projects_bp.route('/api/global/styles', methods=['GET'])
def list_global_styles():
    """List CSS files in global/styles/."""
    styles_dir = os.path.join(GLOBAL_DIR, 'styles')
    if not os.path.exists(styles_dir):
        return jsonify([])
    files = sorted(f for f in os.listdir(styles_dir) if f.endswith('.css'))
    return jsonify(files)

# ── Config endpoints ──────────────────────────────────────────────────────────

@projects_bp.route('/api/config/tokens', methods=['GET'])
def get_tokens_config():
    """Serve global/config/tokens.json to the frontend."""
    tokens_path = os.path.join(GLOBAL_DIR, 'config', 'tokens.json')
    if not os.path.exists(tokens_path):
        return jsonify({}), 404
    with open(tokens_path, encoding='utf-8') as f:
        return jsonify(json.load(f))


@projects_bp.route('/api/projects/<project_id>/used-tokens', methods=['GET'])
def get_used_tokens(project_id):
    """Scan all XHTML files referenced in build_config.json + xhtml dir and
    return the unique set of {{TOKEN}} placeholders found across them."""
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    xhtml_dir   = os.path.join(project_dir, 'xhtml')
    bc_path     = os.path.join(project_dir, 'build_config.json')

    filenames = set()

    # Collect from build_config.json (front + back matter for both profiles)
    if os.path.exists(bc_path):
        with open(bc_path, encoding='utf-8') as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            prof = bc.get(profile, {})
            for section in ('front_matter', 'back_matter', 'chapters'):
                for item in prof.get(section, []):
                    fname = item.get('filename') or (item.get('id', '') + '.xhtml')
                    if fname:
                        filenames.add(fname)

    # Also scan all xhtml files directly in the xhtml dir
    if os.path.isdir(xhtml_dir):
        for f in os.listdir(xhtml_dir):
            if f.endswith('.xhtml'):
                filenames.add(f)

    token_re = re.compile(r'\{\{[A-Z_]+\}\}')
    found = set()

    for fname in filenames:
        fpath = os.path.join(xhtml_dir, fname)
        if not os.path.exists(fpath):
            fpath = os.path.join(GLOBAL_TEMPLATES, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, encoding='utf-8') as f:
                content_file = f.read()
            found.update(token_re.findall(content_file))
        except Exception:
            pass

    return jsonify(sorted(found))

CSS_TOKENS_GLOBAL = os.path.join(GLOBAL_DIR, 'config', 'css_tokens.json')

@projects_bp.route('/api/projects/<project_id>/css-tokens', methods=['GET'])
def get_css_tokens(project_id):
    """Return active CSS tokens for this project from css_tokens_active.json.
    Falls back to global css_tokens.json if active file not yet generated."""
    active_path = os.path.join(PROJECTS_DIR, project_id, 'css_tokens_active.json')
    if os.path.exists(active_path):
        with open(active_path, encoding='utf-8') as f:
            return jsonify(json.load(f))

    # Fallback — active file not generated yet, return from global + project overrides
    if not os.path.exists(CSS_TOKENS_GLOBAL):
        return jsonify({'error': 'css_tokens.json not found'}), 404
    with open(CSS_TOKENS_GLOBAL, encoding='utf-8') as f:
        global_cfg = json.load(f)
    token_defs = global_cfg.get('tokens', global_cfg)  # support both old and new format

    project_overrides = {}
    project_tokens_path = os.path.join(PROJECTS_DIR, project_id, 'css_tokens.json')
    if os.path.exists(project_tokens_path):
        with open(project_tokens_path, encoding='utf-8') as f:
            project_overrides = json.load(f)

    merged = {}
    for token, cfg in token_defs.items():
        merged[token] = {
            'label':   cfg.get('label', token),
            'default': cfg.get('default', ''),
            'value':   project_overrides.get(token, cfg.get('default', '')),
            'profile': 'both',
            'classes': [],
        }
    return jsonify(merged)


@projects_bp.route('/api/projects/<project_id>/css-tokens', methods=['PUT'])
def save_css_tokens(project_id):
    """Save project CSS token overrides — updates both css_tokens.json and css_tokens_active.json."""
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404

    data = request.json or {}
    project_tokens_path = os.path.join(project_dir, 'css_tokens.json')

    # Load existing overrides, update with new values
    existing = {}
    if os.path.exists(project_tokens_path):
        with open(project_tokens_path, encoding='utf-8') as f:
            existing = json.load(f)
    existing.update(data)
    with open(project_tokens_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # Also update values in css_tokens_active.json if it exists
    active_path = os.path.join(project_dir, 'css_tokens_active.json')
    if os.path.exists(active_path):
        with open(active_path, encoding='utf-8') as f:
            active = json.load(f)
        for token, value in data.items():
            if token in active:
                active[token]['value'] = value
        with open(active_path, 'w', encoding='utf-8') as f:
            json.dump(active, f, ensure_ascii=False, indent=2)

    return jsonify({'ok': True})

# ── CSS token scanner ─────────────────────────────────────────────────────────

_CSS_TOKEN_RE = re.compile(r'\{\{[A-Z_]+\}\}')
_CSS_CLASS_RE = re.compile(r'\.([a-zA-Z_-][a-zA-Z0-9_-]*)')

def _scan_css_file(css_path):
    """Scan a CSS file for {{TOKEN}} occurrences using innermost-block matching.
    Returns {token: [classes]} where classes are extracted from the selector
    of the innermost block containing each token."""
    result = {}
    try:
        with open(css_path, encoding='utf-8') as f:
            raw = f.read()
        stripped = re.sub(r'/\*[\s\S]*?\*/', '', raw)

        # Build list of (start, end, selector) for all blocks
        blocks = []
        i = 0
        while i < len(stripped):
            brace = stripped.find('{', i)
            if brace == -1:
                break
            # Find matching close brace
            depth = 1
            j = brace + 1
            while j < len(stripped) and depth > 0:
                if stripped[j] == '{': depth += 1
                elif stripped[j] == '}': depth -= 1
                j += 1
            selector = stripped[i:brace].strip()
            blocks.append((brace + 1, j - 1, selector))
            i = brace + 1  # advance by 1 so inner blocks are also found

        # For each token find innermost block containing it
        for m in _CSS_TOKEN_RE.finditer(stripped):
            pos = m.start()
            best_selector = None
            best_size = float('inf')
            for start, end, selector in blocks:
                if start <= pos <= end:
                    size = end - start
                    if size < best_size:
                        best_size = size
                        best_selector = selector
            classes = list({c for c in _CSS_CLASS_RE.findall(best_selector or '')})
            token = m.group()
            if token not in result:
                result[token] = set()
            result[token].update(classes)
    except Exception:
        pass
    return {k: list(v) for k, v in result.items()}

def _get_css_file_profile(css_filename, explicit_profiles, xhtml_profiles):
    """Return 'print', 'digital', or 'both' for a CSS file."""
    if css_filename in explicit_profiles:
        return explicit_profiles[css_filename]
    profiles_used = set()
    for profile, filenames in xhtml_profiles.items():
        if css_filename in filenames:
            profiles_used.add(profile)
    if profiles_used == {'digital'}:  return 'digital'
    if profiles_used == {'print'}:    return 'print'
    return 'both'

@projects_bp.route('/api/projects/<project_id>/css-tokens/sync', methods=['POST'])
def sync_css_tokens(project_id):
    """Scan project CSS files and build css_tokens_active.json."""
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404

    # Load global css_tokens.json
    css_tokens_global_path = CSS_TOKENS_GLOBAL
    if not os.path.exists(css_tokens_global_path):
        return jsonify({'error': 'css_tokens.json not found'}), 404
    with open(css_tokens_global_path, encoding='utf-8') as f:
        global_cfg = json.load(f)
    token_defs      = global_cfg.get('tokens', {})
    explicit_profiles = global_cfg.get('css_files', {})

    # Load project overrides
    project_overrides = {}
    overrides_path = os.path.join(project_dir, 'css_tokens.json')
    if os.path.exists(overrides_path):
        with open(overrides_path, encoding='utf-8') as f:
            project_overrides = json.load(f)

    # Load build_config to derive CSS file profiles from XHTML link tags
    xhtml_dir    = os.path.join(project_dir, 'xhtml')
    styles_dir   = os.path.join(project_dir, 'styles')
    global_styles = os.path.join(GLOBAL_DIR, 'styles')
    bc_path      = os.path.join(project_dir, 'build_config.json')
    xhtml_profiles = {'digital': set(), 'print': set()}  # css_filename → profiles

    if os.path.exists(bc_path):
        with open(bc_path, encoding='utf-8') as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            items = (bc.get(profile, {}).get('front_matter', []) +
                     bc.get(profile, {}).get('back_matter', []) +
                     bc.get(profile, {}).get('chapters', []))
            for item in items:
                fname = item.get('filename', '')
                xhtml_path = os.path.join(xhtml_dir, fname)
                if not os.path.exists(xhtml_path):
                    continue
                with open(xhtml_path, encoding='utf-8') as f:
                    xhtml_content = f.read()
                for link_match in re.finditer(r'<link[^>]+href=["\']([^"\']+\.css)["\']', xhtml_content):
                    css_ref = link_match.group(1).split('/')[-1]
                    xhtml_profiles[profile].add(css_ref)

    # Scan all CSS files in project styles dir (fallback to global)
    css_files_to_scan = {}
    styles_source = styles_dir if os.path.exists(styles_dir) else global_styles
    if os.path.exists(styles_source):
        for fname in os.listdir(styles_source):
            if fname.endswith('.css'):
                css_files_to_scan[fname] = os.path.join(styles_source, fname)

    # Build active tokens
    active = {}
    for css_filename, css_path in sorted(css_files_to_scan.items()):
        profile = _get_css_file_profile(css_filename, explicit_profiles, xhtml_profiles)
        tokens_in_file = _scan_css_file(css_path)
        for token, classes in tokens_in_file.items():
            if token not in token_defs:
                continue  # not in global definitions — skip
            if token not in active:
                cfg = token_defs[token]
                active[token] = {
                    'label':   cfg.get('label', token),
                    'default': cfg.get('default', ''),
                    'value':   project_overrides.get(token, cfg.get('default', '')),
                    'profile': profile,
                    'classes': classes,
                    'css_file': css_filename,
                    'step':    cfg.get('step', None),
                }
            else:
                # Token appears in multiple files — merge classes, broaden profile
                existing = active[token]
                existing['classes'] = list(set(existing['classes']) | set(classes))
                if existing['profile'] != profile:
                    existing['profile'] = 'both'

    # Write css_tokens_active.json
    active_path = os.path.join(project_dir, 'css_tokens_active.json')
    with open(active_path, 'w', encoding='utf-8') as f:
        json.dump(active, f, ensure_ascii=False, indent=2)

    return jsonify({'ok': True, 'tokens_found': len(active)})