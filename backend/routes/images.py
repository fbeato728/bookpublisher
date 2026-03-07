import os
import json
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

images_bp = Blueprint('images', __name__)

from config import PROJECTS_DIR
ALLOWED_EXTS   = {'jpg', 'jpeg', 'png', 'gif', 'svg', 'webp'}

def _images_dir(project_id):
    return os.path.join(PROJECTS_DIR, project_id, 'images')

def _meta_path(project_id):
    return os.path.join(PROJECTS_DIR, project_id, 'meta.json')

def _load_meta(project_id):
    path = _meta_path(project_id)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)

def _save_meta(project_id, meta):
    with open(_meta_path(project_id), 'w') as f:
        json.dump(meta, f, indent=2)


@images_bp.route('/api/projects/<project_id>/images', methods=['GET'])
def list_images(project_id):
    """List all images in the project images dir."""
    images_dir = _images_dir(project_id)
    if not os.path.exists(images_dir):
        return jsonify({'images': [], 'cover_image': None, 'digital_inside_cover': None, 'print_inside_cover': None})
    meta = _load_meta(project_id)
    files = sorted(
        f for f in os.listdir(images_dir)
        if f.rsplit('.', 1)[-1].lower() in ALLOWED_EXTS
    )
    return jsonify({
        'images':               files,
        'cover_image':          meta.get('cover_image', None),
        'digital_inside_cover': meta.get('digital_inside_cover', None),
        'print_inside_cover':   meta.get('print_inside_cover', None),
    })


@images_bp.route('/api/projects/<project_id>/images', methods=['POST'])
def upload_image(project_id):
    """Upload an image to the project images dir."""
    images_dir = _images_dir(project_id)
    os.makedirs(images_dir, exist_ok=True)
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Empty filename'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXTS:
        return jsonify({'error': f'File type .{ext} not allowed'}), 400
    filename = secure_filename(f.filename)
    dest = os.path.join(images_dir, filename)
    f.save(dest)
    return jsonify({'ok': True, 'filename': filename})


@images_bp.route('/api/projects/<project_id>/images/<filename>', methods=['GET'])
def serve_image(project_id, filename):
    """Serve an image file from the project images dir."""
    from flask import send_from_directory
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    images_dir = _images_dir(project_id)
    if not os.path.exists(os.path.join(images_dir, filename)):
        return jsonify({'error': 'File not found'}), 404
    return send_from_directory(images_dir, filename)


@images_bp.route('/api/projects/<project_id>/images/<filename>', methods=['DELETE'])
def delete_image(project_id, filename):
    """Delete an image from the project images dir."""
    if '/' in filename or '..' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    path = os.path.join(_images_dir(project_id), filename)
    if not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    os.remove(path)
    # Clear any cover assignment that referenced this file
    meta = _load_meta(project_id)
    changed = False
    for field in ('cover_image', 'digital_inside_cover', 'print_inside_cover'):
        if meta.get(field) == filename:
            meta[field] = None
            changed = True
    if changed:
        _save_meta(project_id, meta)
    return jsonify({'ok': True})


@images_bp.route('/api/projects/<project_id>/cover-image', methods=['PUT'])
def set_cover_image(project_id):
    """Assign an image to a cover role. field: cover_image | digital_inside_cover | print_inside_cover."""
    data     = request.json or {}
    filename = data.get('filename')   # None to unset
    field    = data.get('field', 'cover_image')
    if field not in ('cover_image', 'digital_inside_cover', 'print_inside_cover'):
        return jsonify({'error': 'Invalid field'}), 400
    meta = _load_meta(project_id)
    meta[field] = filename
    _save_meta(project_id, meta)
    return jsonify({'ok': True, field: filename})