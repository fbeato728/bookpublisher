import os
from flask import Blueprint, jsonify
from flask import send_from_directory

fonts_bp = Blueprint('fonts', __name__)

PROJECTS_DIR = '/srv/bookpublisher/projects'
GLOBAL_FONTS = '/srv/bookpublisher/global/fonts'
ALLOWED_EXTS = {'ttf', 'otf', 'woff', 'woff2'}


def _resolve_font(project_id, filename):
    """Return path to font file — project override first, then global."""
    project_path = os.path.join(PROJECTS_DIR, project_id, 'fonts', filename)
    if os.path.exists(project_path):
        return project_path
    global_path = os.path.join(GLOBAL_FONTS, filename)
    if os.path.exists(global_path):
        return global_path
    return None


@fonts_bp.route('/api/projects/<project_id>/fonts', methods=['GET'])
def list_fonts(project_id):
    """List all fonts available for the project (project overrides + global)."""
    seen  = {}
    for fonts_dir, source in [
        (os.path.join(PROJECTS_DIR, project_id, 'fonts'), 'project'),
        (GLOBAL_FONTS, 'global'),
    ]:
        if not os.path.isdir(fonts_dir):
            continue
        for fname in sorted(os.listdir(fonts_dir)):
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext in ALLOWED_EXTS and fname not in seen:
                seen[fname] = source
    fonts = [{'filename': f, 'source': s} for f, s in seen.items()]
    return jsonify({'fonts': fonts})


@fonts_bp.route('/api/projects/<project_id>/fonts/<filename>', methods=['GET'])
def serve_font(project_id, filename):
    """Serve a font file — project override first, then global."""
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_EXTS:
        return jsonify({'error': 'File type not allowed'}), 400
    path = _resolve_font(project_id, filename)
    if not path:
        return jsonify({'error': 'Font not found'}), 404
    return send_from_directory(os.path.dirname(path), filename)