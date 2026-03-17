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
    for profile, sections in TEMPLATE_SUBFOLDERS.items():
        build_config[profile] = {'front_matter': [], 'chapters': [], 'back_matter': []}
        for section, subfolder in sections.items():
            folder = os.path.join(GLOBAL_TEMPLATES, subfolder)
            if not os.path.exists(folder):
                continue
            for fname in sorted(os.listdir(folder)):
                if not fname.endswith('.xhtml'):
                    continue
                shutil.copy2(os.path.join(folder, fname), os.path.join(xhtml_dir, fname))
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
    meta['status'] = 'converted'
    meta['chapters'] = []
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

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
    for section, subfolder in TEMPLATE_SUBFOLDERS[profile].items():
        folder = os.path.join(GLOBAL_TEMPLATES, subfolder)
        if not os.path.exists(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith('.xhtml'):
                continue
            shutil.copy2(os.path.join(folder, fname), os.path.join(xhtml_dir, fname))
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