import os
import json
import subprocess
import tempfile
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file

pdf_bp = Blueprint('pdf', __name__)

from config import PROJECTS_DIR, GLOBAL_DIR

GLOBAL_CONFIG        = os.path.join(GLOBAL_DIR, 'config')
GLOBAL_JSON          = os.path.join(GLOBAL_CONFIG, 'global.json')
PRINCE_TEMPLATE_CSS  = os.path.join(GLOBAL_CONFIG, 'prince_template.css')
PDF_CONFIG_FILENAME  = 'pdf_config.json'

PDF_CONFIG_DEFAULTS = {
    'page': {
        'width':           '128.524mm',
        'height':          '198.374mm',
        'margin_top':      '17mm',
        'margin_bottom':   '21mm',
        'margin_inside':   '20mm',
        'margin_outside':  '14mm',
    },
    'typography': {
        'font_size':            '12pt',
        'chapter_break':        'right',
        'page_counter_offset':  -2,
    },
    'conversion': {
        'trim':            True,
        'trim_start':      2,
        'trim_end':        1,
        'keep_prince_pdf': False,
        'extra_args':      '',
    },
    'history': [],
}

# ── Token map: template token → pdf_config key path ─────────────────────────
TOKEN_MAP = {
    '{{PAGE_WIDTH}}':          ('page', 'width'),
    '{{PAGE_HEIGHT}}':         ('page', 'height'),
    '{{MARGIN_TOP}}':          ('page', 'margin_top'),
    '{{MARGIN_BOTTOM}}':       ('page', 'margin_bottom'),
    '{{MARGIN_INSIDE}}':       ('page', 'margin_inside'),
    '{{MARGIN_OUTSIDE}}':      ('page', 'margin_outside'),
    '{{FONT_SIZE}}':           ('typography', 'font_size'),
    '{{CHAPTER_BREAK}}':       ('typography', 'chapter_break'),
    '{{PAGE_COUNTER_OFFSET}}': ('typography', 'page_counter_offset'),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pdf_config_path(project_id):
    return os.path.join(PROJECTS_DIR, project_id, PDF_CONFIG_FILENAME)

def _load_pdf_config(project_id):
    path = _pdf_config_path(project_id)
    if not os.path.exists(path):
        return dict(PDF_CONFIG_DEFAULTS)
    with open(path) as f:
        stored = json.load(f)
    # Deep merge with defaults so new keys are always present
    config = {}
    for section, defaults in PDF_CONFIG_DEFAULTS.items():
        if section == 'history':
            config['history'] = stored.get('history', [])
        else:
            config[section] = {**defaults, **stored.get(section, {})}
    return config

def _save_pdf_config(project_id, config):
    with open(_pdf_config_path(project_id), 'w') as f:
        json.dump(config, f, indent=2)

def _generate_css(config):
    """Fill prince_template.css tokens from pdf_config."""
    with open(PRINCE_TEMPLATE_CSS, encoding='utf-8') as f:
        css = f.read()
    for token, (section, key) in TOKEN_MAP.items():
        value = str(config.get(section, {}).get(key, ''))
        css = css.replace(token, value)
    return css

def _get_prince_cli():
    """Read prince_cli path from global.json."""
    try:
        with open(GLOBAL_JSON) as f:
            g = json.load(f)
        return g.get('prince_cli', '/srv/prince_pdf_app/prince_pdf/cli.py')
    except Exception:
        return '/srv/prince_pdf_app/prince_pdf/cli.py'

def _latest_print_epub(project_id):
    """Return path to the highest-versioned print EPUB for this project."""
    epub_dir = os.path.join(PROJECTS_DIR, project_id, 'epub')
    if not os.path.isdir(epub_dir):
        return None, None
    candidates = []
    for fname in os.listdir(epub_dir):
        if fname.endswith('_print.epub') or '_print_v' in fname:
            candidates.append(fname)
    if not candidates:
        return None, None
    # Sort by version number
    import re
    def _ver(name):
        m = re.search(r'_print_v(\d+)\.epub$', name)
        return int(m.group(1)) if m else 0
    candidates.sort(key=_ver)
    latest = candidates[-1]
    return os.path.join(epub_dir, latest), latest


# ── Routes ────────────────────────────────────────────────────────────────────

@pdf_bp.route('/api/projects/<project_id>/print-epubs', methods=['GET'])
def list_print_epubs(project_id):
    """List all versioned print EPUBs for a project, sorted oldest to newest."""
    epub_dir = os.path.join(PROJECTS_DIR, project_id, 'epub')
    if not os.path.isdir(epub_dir):
        return jsonify([])
    import re
    candidates = []
    for fname in os.listdir(epub_dir):
        if '_print' in fname and fname.endswith('.epub'):
            candidates.append(fname)
    def _ver(name):
        m = re.search(r'_print_v(\d+)\.epub$', name)
        return int(m.group(1)) if m else 0
    candidates.sort(key=_ver)
    return jsonify(candidates)


    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404
    return jsonify(_load_pdf_config(project_id))

@pdf_bp.route('/api/projects/<project_id>/pdf-config', methods=['GET'])
def get_pdf_config(project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404
    return jsonify(_load_pdf_config(project_id))

@pdf_bp.route('/api/projects/<project_id>/pdf-config', methods=['POST'])
def save_pdf_config_route(project_id):
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404
    data = request.json or {}
    config = _load_pdf_config(project_id)
    for section in ('page', 'typography', 'conversion'):
        if section in data:
            config[section].update(data[section])
    _save_pdf_config(project_id, config)
    return jsonify({'ok': True, 'config': config})

@pdf_bp.route('/api/projects/<project_id>/convert-pdf', methods=['POST'])
def convert_pdf(project_id):
    """Generate CSS from template, call calibre-debug CLI, update history."""
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if not os.path.exists(project_dir):
        return jsonify({'error': 'Project not found'}), 404

    config = _load_pdf_config(project_id)
    conv   = config['conversion']

    # Use epub_filename from request if provided, else fall back to latest
    req_data = request.json or {}
    req_epub = req_data.get('epub_filename')

    if req_epub:
        epub_filename = req_epub
        epub_path     = os.path.join(PROJECTS_DIR, project_id, 'epub', epub_filename)
        if not os.path.exists(epub_path):
            return jsonify({'error': f'EPUB not found: {epub_filename}'}), 400
    else:
        epub_path, epub_filename = _latest_print_epub(project_id)
        if not epub_path:
            return jsonify({'error': 'No print EPUB found. Build a print EPUB first.'}), 400

    # Output PDF path
    pdf_dir  = os.path.join(project_dir, 'pdf')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_stem = epub_filename.replace('.epub', '')
    pdf_filename = pdf_stem + '.pdf'
    pdf_path = os.path.join(pdf_dir, pdf_filename)

    # Generate CSS into a temp file
    try:
        css_content = _generate_css(config)
    except Exception as e:
        return jsonify({'error': f'CSS generation failed: {e}'}), 500

    prince_cli = _get_prince_cli()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.css', delete=False,
                                     encoding='utf-8') as tmp_css:
        tmp_css.write(css_content)
        tmp_css_path = tmp_css.name

    try:
        cmd = [
            'calibre-debug', '-e', prince_cli, '--',
            epub_path,
            '-o', pdf_path,
            '--css', tmp_css_path,
            '-v',
        ]

        if conv.get('trim'):
            cmd.append('--trim')
            trim_start = int(conv.get('trim_start', 0))
            trim_end   = int(conv.get('trim_end', 0))
            if trim_start: cmd += ['--trim-start', str(trim_start)]
            if trim_end:   cmd += ['--trim-end',   str(trim_end)]

        if conv.get('keep_prince_pdf'):
            cmd.append('--keep-prince-pdf')
        else:
            cmd.append('--no-keep-prince-pdf')

        if conv.get('extra_args'):
            import shlex
            cmd += shlex.split(conv['extra_args'])

        result = subprocess.run(
            cmd,
            cwd='/srv/prince_pdf_app',
            capture_output=True,
            text=True,
            timeout=300,
        )

        log = result.stdout + result.stderr
        success = result.returncode == 0 and os.path.exists(pdf_path)

        if not success:
            return jsonify({'ok': False, 'error': 'Conversion failed', 'log': log}), 500

        # Determine prince PDF filename if kept
        prince_pdf_filename = None
        if conv.get('keep_prince_pdf'):
            prince_suffix = pdf_stem + '.prince.pdf'
            if os.path.exists(os.path.join(pdf_dir, prince_suffix)):
                prince_pdf_filename = prince_suffix

        # Update history
        entry = {
            'epub_version':        epub_filename,
            'pdf_filename':        pdf_filename,
            'prince_pdf_filename': prince_pdf_filename,
            'timestamp':           datetime.now().isoformat(),
            'trim_start':          int(conv.get('trim_start', 0)),
            'trim_end':            int(conv.get('trim_end', 0)),
            'keep_prince_pdf':     bool(conv.get('keep_prince_pdf', False)),
        }
        config['history'].append(entry)
        _save_pdf_config(project_id, config)

        return jsonify({
            'ok':              True,
            'pdf_filename':    pdf_filename,
            'prince_pdf_filename': prince_pdf_filename,
            'log':             log,
            'history_entry':   entry,
        })

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Conversion timed out (300s)'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            os.unlink(tmp_css_path)
        except OSError:
            pass

@pdf_bp.route('/api/projects/<project_id>/pdf/<filename>', methods=['GET'])
def serve_pdf(project_id, filename):
    """Serve a PDF file from the project pdf/ folder."""
    # Safety: no path traversal
    if '..' in filename or '/' in filename:
        return jsonify({'error': 'Invalid filename'}), 400
    pdf_path = os.path.join(PROJECTS_DIR, project_id, 'pdf', filename)
    if not os.path.exists(pdf_path):
        return jsonify({'error': 'PDF not found'}), 404
    return send_file(pdf_path, mimetype='application/pdf')