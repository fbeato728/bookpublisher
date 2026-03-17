import os
import json
from flask import Blueprint, request, jsonify

xhtml_bp = Blueprint('xhtml', __name__)

from config import PROJECTS_DIR, GLOBAL_DIR
from routes.split import CONFIG, is_safe_filename, get_error_message, build_blank_xhtml_template, SKIP_FILES, CHAPTER_RE
from routes.utils import fill_tokens

GLOBAL_TEMPLATES = os.path.join(GLOBAL_DIR, 'templates')


@xhtml_bp.route('/api/projects/<project_id>/xhtml', methods=['GET'])
def list_xhtml_files(project_id):
    """List structural (non-chapter) XHTML files in the project xhtml dir."""
    xhtml_dir = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'])
    if not os.path.exists(xhtml_dir):
        return jsonify([])
    files = sorted(
        f for f in os.listdir(xhtml_dir)
        if f.endswith(CONFIG['files']['allowed_extensions']['xhtml'])
        and f not in SKIP_FILES
        and not CHAPTER_RE.match(f)
    )
    return jsonify(files)


@xhtml_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['POST'])
def create_xhtml_file(project_id, filename):
    """Create a new blank XHTML file in the project xhtml dir."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    if os.path.exists(path):
        return jsonify({'error': get_error_message('file_already_exists')}), 409
    title   = os.path.splitext(filename)[0]
    content = build_blank_xhtml_template(title)
    with open(path, 'w', encoding=CONFIG['files']['encoding']) as f:
        f.write(content)
    return jsonify({'ok': True, 'filename': filename, 'content': content})


@xhtml_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['GET'])
def get_xhtml_file(project_id, filename):
    """Get any XHTML file — project file first, then global template fallback."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400

    content = None
    source  = None

    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    if os.path.exists(path):
        with open(path, encoding=CONFIG['files']['encoding']) as f:
            content = f.read()
        source = 'project'
    else:
        tmpl = os.path.join(GLOBAL_TEMPLATES, filename)
        if os.path.exists(tmpl):
            with open(tmpl, encoding=CONFIG['files']['encoding']) as f:
                content = f.read()
            source = 'global'

    if content is None:
        return jsonify({'error': get_error_message('file_not_found')}), 404

    if request.args.get('preview') == 'true':
        meta_path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['files']['meta'])
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            content = fill_tokens(content, meta)

    return jsonify({'content': content, 'filename': filename, 'source': source})


@xhtml_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['PUT'])
def save_xhtml_file(project_id, filename):
    """Save any XHTML file to the project xhtml dir."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    content = request.json.get('content', '')
    with open(path, 'w', encoding=CONFIG['files']['encoding']) as f:
        f.write(content)
    return jsonify({'ok': True, 'source': 'project'})


@xhtml_bp.route('/api/projects/<project_id>/xhtml/<filename>', methods=['DELETE'])
def delete_xhtml(project_id, filename):
    """Delete any xhtml file from disk."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    filepath    = os.path.join(project_dir, CONFIG['paths']['subdirs']['xhtml'], filename)
    if not os.path.exists(filepath):
        return jsonify({'error': get_error_message('file_not_found')}), 404
    os.remove(filepath)
    return jsonify({'ok': True, 'filename': filename})


@xhtml_bp.route('/api/projects/<project_id>/xhtml/<old_filename>/rename', methods=['PUT'])
def rename_xhtml(project_id, old_filename):
    """Rename any xhtml file on disk and update all references in build_config.json."""
    if not old_filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(old_filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400

    data         = request.json or {}
    new_filename = data.get('new_filename', '').strip()

    if not new_filename or not new_filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(new_filename):
        return jsonify({'error': get_error_message('invalid_new_filename')}), 400

    project_dir = os.path.join(PROJECTS_DIR, project_id)
    xhtml_dir   = os.path.join(project_dir, CONFIG['paths']['subdirs']['xhtml'])
    old_path    = os.path.join(xhtml_dir, old_filename)
    new_path    = os.path.join(xhtml_dir, new_filename)

    if not os.path.exists(old_path):
        return jsonify({'error': get_error_message('file_not_found')}), 404
    if os.path.exists(new_path) and old_filename != new_filename:
        return jsonify({'error': get_error_message('target_exists')}), 409

    os.rename(old_path, new_path)

    bc_path = os.path.join(project_dir, CONFIG['paths']['files']['build_config'])
    if os.path.exists(bc_path):
        with open(bc_path) as f:
            bc = json.load(f)
        for profile in ('digital', 'print'):
            if profile not in bc:
                continue
            for section in ('front_matter', 'chapters', 'back_matter'):
                for item in bc[profile].get(section, []):
                    if item.get('filename') == old_filename:
                        item['filename'] = new_filename
        with open(bc_path, 'w') as f:
            json.dump(bc, f, indent=CONFIG['files']['json_indent'])

    meta_path = os.path.join(project_dir, CONFIG['paths']['files']['meta'])
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        for ch in meta.get('chapters', []):
            if ch.get('filename') == old_filename:
                ch['filename'] = new_filename
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=CONFIG['files']['json_indent'])

    return jsonify({'ok': True, 'old_filename': old_filename, 'new_filename': new_filename})


@xhtml_bp.route('/api/projects/<project_id>/styles', methods=['GET'])
def list_css_files(project_id):
    """List CSS files in the project styles dir."""
    styles_dir = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['styles'])
    if not os.path.exists(styles_dir):
        return jsonify([])
    files = sorted(f for f in os.listdir(styles_dir) if f.endswith(CONFIG['files']['allowed_extensions']['css']))
    return jsonify(files)


@xhtml_bp.route('/api/projects/<project_id>/styles', methods=['POST'])
def create_css_file(project_id):
    """Create a new blank CSS file in the project styles dir."""
    data     = request.json or {}
    filename = data.get('filename', '').strip()
    if not filename.endswith(CONFIG['files']['allowed_extensions']['css']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    styles_dir = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['styles'])
    os.makedirs(styles_dir, exist_ok=True)
    path = os.path.join(styles_dir, filename)
    if os.path.exists(path):
        return jsonify({'error': get_error_message('file_already_exists')}), 409
    content = "/* New stylesheet */\n"
    with open(path, 'w', encoding=CONFIG['files']['encoding']) as f:
        f.write(content)
    return jsonify({'ok': True, 'filename': filename, 'content': content, 'source': 'project'})


@xhtml_bp.route('/api/projects/<project_id>/styles/<filename>', methods=['GET'])
def get_css_file(project_id, filename):
    """Get a CSS file — project styles dir first, then global fallback."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['css']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400

    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['styles'], filename)
    if os.path.exists(path):
        with open(path, encoding=CONFIG['files']['encoding']) as f:
            content = f.read()
        return jsonify({'content': content, 'filename': filename, 'source': 'project'})

    global_path = os.path.join(GLOBAL_DIR, CONFIG['paths']['subdirs']['styles'], filename)
    if os.path.exists(global_path):
        with open(global_path, encoding=CONFIG['files']['encoding']) as f:
            content = f.read()
        return jsonify({'content': content, 'filename': filename, 'source': 'global'})

    return jsonify({'error': get_error_message('file_not_found')}), 404


@xhtml_bp.route('/api/projects/<project_id>/styles/<filename>', methods=['PUT'])
def save_css_file(project_id, filename):
    """Save a CSS file to the project styles dir."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['css']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    styles_dir = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['styles'])
    os.makedirs(styles_dir, exist_ok=True)
    path = os.path.join(styles_dir, filename)
    content = request.json.get('content', '')
    with open(path, 'w', encoding=CONFIG['files']['encoding']) as f:
        f.write(content)
    return jsonify({'ok': True, 'source': 'project'})