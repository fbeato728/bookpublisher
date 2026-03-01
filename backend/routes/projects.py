import os
import uuid
import json
import re
import shutil
from flask import Blueprint, request, jsonify
from scripts.docx_converter import convert_docx, save_full_xhtml

projects_bp = Blueprint('projects', __name__)

PROJECTS_DIR     = '/srv/bookpublisher/projects'
GLOBAL_TEMPLATES = '/srv/bookpublisher/global/templates'

# Front matter files to copy from global/templates into every new project
FRONT_MATTER_FILES = [
    'cover_digital.xhtml',
    'credits_digital.xhtml',
    'credits_print.xhtml',
    'inside_cover_print.xhtml',
    'taula.xhtml',
    'title_only.xhtml',
]

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text

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
    for subdir in ['original', 'xhtml', 'assets/images', 'assets/fonts', 'assets/styles', 'epub', 'print', 'pdf']:
        os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

    # Save original file
    original_path = os.path.join(project_dir, 'original', file.filename)
    file.save(original_path)

    # Convert DOCX to single XHTML
    images_dir = os.path.join(project_dir, 'images')
    xhtml = convert_docx(original_path, title, images_dir=images_dir)
    save_full_xhtml(xhtml, os.path.join(project_dir, 'xhtml'), title)

    # Copy global front matter templates into the project xhtml dir
    xhtml_dir = os.path.join(project_dir, 'xhtml')
    for fname in FRONT_MATTER_FILES:
        src = os.path.join(GLOBAL_TEMPLATES, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(xhtml_dir, fname))

    # Save metadata
    meta = {
        'id': project_id,
        'title': title,
        'author': author,
        'original_file': file.filename,
        'status': 'converted',
        'xhtml_file': 'xhtml/full.xhtml'
    }
    with open(os.path.join(project_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"Created project: {project_id}")
    return jsonify(meta), 201

@projects_bp.route('/api/projects/<project_id>', methods=['GET'])
def get_project(project_id):
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404
    with open(meta_path) as f:
        return jsonify(json.load(f))

@projects_bp.route('/api/projects/<project_id>', methods=['PATCH'])
def update_project_meta(project_id):
    """Update editable metadata fields in meta.json."""
    meta_path = os.path.join(PROJECTS_DIR, project_id, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404
    with open(meta_path) as f:
        meta = json.load(f)
    allowed = {'title', 'author', 'language', 'publisher', 'isbn', 'translator',
               'depot_legal', 'first_edition', 'original_title', 'original_year',
               'original_author', 'translation_year'}
    data = request.json or {}
    for key, value in data.items():
        if key in allowed:
            meta[key] = value
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    return jsonify({'ok': True, 'meta': meta})

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
    import shutil
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404

    # Keep: original/ and xhtml/full.xhtml
    # Delete everything else inside the project folder

    keep_dirs  = {'original'}
    keep_files = {os.path.join('xhtml', 'full.xhtml')}

    for entry in os.listdir(project_dir):
        entry_path = os.path.join(project_dir, entry)
        if entry == 'meta.json':
            continue  # preserve meta
        if entry in keep_dirs:
            continue  # preserve original/
        if entry == 'xhtml':
            # Remove all xhtml files except full.xhtml
            for f in os.listdir(entry_path):
                if f != 'full.xhtml':
                    os.remove(os.path.join(entry_path, f))
            continue
        if os.path.isdir(entry_path):
            shutil.rmtree(entry_path)
        else:
            os.remove(entry_path)

    # Reset meta.json status and chapters
    meta_path = os.path.join(project_dir, 'meta.json')
    with open(meta_path) as f:
        meta = json.load(f)
    meta['status'] = 'converted'
    meta['chapters'] = []
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    return jsonify({'ok': True})