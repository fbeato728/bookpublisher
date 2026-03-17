import os
import re
import json
from flask import Blueprint, request, jsonify

chapters_bp = Blueprint('chapters', __name__)

from config import PROJECTS_DIR, GLOBAL_DIR
from routes.split import CONFIG, is_safe_filename, get_error_message, build_blank_xhtml_template, SKIP_FILES, CHAPTER_RE

GLOBAL_TEMPLATES = os.path.join(GLOBAL_DIR, 'templates')


@chapters_bp.route('/api/projects/<project_id>/chapters', methods=['GET'])
def list_chapters(project_id):
    """List all chapter XHTML files for a project."""
    meta_path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['files']['meta'])
    if not os.path.exists(meta_path):
        return jsonify({'error': get_error_message('project_not_found')}), 404
    with open(meta_path) as f:
        meta = json.load(f)
    return jsonify(meta.get('chapters', []))


@chapters_bp.route('/api/projects/<project_id>/chapters/<filename>', methods=['GET'])
def get_chapter(project_id, filename):
    """Get content of a specific chapter file."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    if not os.path.exists(path):
        return jsonify({'error': get_error_message('file_not_found')}), 404
    with open(path, encoding=CONFIG['files']['encoding']) as f:
        content = f.read()
    return jsonify({'content': content, 'filename': filename})


@chapters_bp.route('/api/projects/<project_id>/chapters/<filename>', methods=['DELETE'])
def delete_chapter(project_id, filename):
    """Delete a chapter file and remove it from meta.json."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    if not os.path.exists(path):
        return jsonify({'error': get_error_message('file_not_found')}), 404
    os.remove(path)
    meta_path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['files']['meta'])
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        meta['chapters'] = [c for c in meta.get('chapters', []) if c.get('filename') != filename]
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=CONFIG['files']['json_indent'])
    return jsonify({'ok': True})


@chapters_bp.route('/api/projects/<project_id>/chapters/<filename>', methods=['PUT'])
def save_chapter(project_id, filename):
    """Save updated content of a chapter file."""
    if not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400
    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    if not os.path.exists(path):
        return jsonify({'error': get_error_message('file_not_found')}), 404
    content = request.json.get('content', '')
    with open(path, 'w', encoding=CONFIG['files']['encoding']) as f:
        f.write(content)
    return jsonify({'ok': True})


@chapters_bp.route('/api/projects/<project_id>/chapters', methods=['POST'])
def create_chapter(project_id):
    """Create a new blank chapter file and add it to meta.json."""
    meta_path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['files']['meta'])
    if not os.path.exists(meta_path):
        return jsonify({'error': get_error_message('project_not_found')}), 404

    data     = request.json or {}
    filename = data.get('filename', '').strip()
    name     = data.get('name', '').strip()
    ch_type  = data.get('type', CONFIG['chapters']['defaults']['type']).strip()

    if not filename or not filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400

    path = os.path.join(PROJECTS_DIR, project_id, CONFIG['paths']['subdirs']['xhtml'], filename)
    if os.path.exists(path):
        return jsonify({'error': get_error_message('file_already_exists')}), 409

    with open(meta_path) as f:
        meta = json.load(f)

    title   = meta.get('title', CONFIG['metadata']['defaults']['title'])
    content = build_blank_xhtml_template(f"{title}{CONFIG['chapters']['defaults']['title_separator']}{name or filename}")
    with open(path, 'w', encoding=CONFIG['files']['encoding']) as f:
        f.write(content)

    chapter_entry = {'filename': filename, 'type': ch_type, 'name': name or filename}
    meta.setdefault('chapters', []).append(chapter_entry)
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=CONFIG['files']['json_indent'])

    return jsonify({'ok': True, 'chapter': chapter_entry})


@chapters_bp.route('/api/projects/<project_id>/chapters/<old_filename>/rename', methods=['PUT'])
def rename_chapter(project_id, old_filename):
    """Rename a chapter file on disk and update meta.json and build_config.json."""
    if not old_filename.endswith(CONFIG['files']['allowed_extensions']['xhtml']) or not is_safe_filename(old_filename):
        return jsonify({'error': get_error_message('invalid_filename')}), 400

    data         = request.json or {}
    new_filename = data.get('new_filename', '').strip()
    new_name     = data.get('new_name', '').strip()

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

    meta_path = os.path.join(project_dir, CONFIG['paths']['files']['meta'])
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        for ch in meta.get('chapters', []):
            if ch.get('filename') == old_filename:
                ch['filename'] = new_filename
                if new_name:
                    ch['name'] = new_name
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=CONFIG['files']['json_indent'])

    bc_path = os.path.join(project_dir, CONFIG['paths']['files']['build_config'])
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
            json.dump(bc, f, indent=CONFIG['files']['json_indent'])

    return jsonify({'ok': True, 'old_filename': old_filename, 'new_filename': new_filename})