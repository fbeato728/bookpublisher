import os
import re
import json
import uuid
import zipfile
import shutil
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from lxml import etree

build_bp = Blueprint('build', __name__)

from config import PROJECTS_DIR, GLOBAL_DIR, BUILDS_DIR
from routes.utils import fill_tokens as _fill_tokens_util

# ── Global asset paths ────────────────────────────────────────────────────────
GLOBAL_STYLES = os.path.join(GLOBAL_DIR, 'styles')
GLOBAL_FONTS  = os.path.join(GLOBAL_DIR, 'fonts')
GLOBAL_TEMPLATES = os.path.join(GLOBAL_DIR, 'templates')  # blank04, title_only, nav, toc
GLOBAL_CONFIG = os.path.join(GLOBAL_DIR, 'config')
GLOBAL_JSON   = os.path.join(GLOBAL_CONFIG, 'global.json')
TOKENS_PATH   = os.path.join(GLOBAL_CONFIG, 'tokens.json')
BUILD_JSON    = os.path.join(GLOBAL_CONFIG, 'build.json')

# ── XHTML templates ───────────────────────────────────────────────────────────
BLANK_XHTML = """<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <link rel="stylesheet" href="../styles/main.css" type="text/css"/>
    <title></title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>
    <p class="blank"> </p>
  </body>
</html>"""

TITLEPAGE_XHTML = """<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <link rel="stylesheet" href="../styles/main.css" type="text/css"/>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>
    <div class="body">
      <div class="divImage">
        <img src="../images/{cover_image}" alt="{title}" class="fifty"/>
      </div>
    </div>
  </body>
</html>"""

NAV_XHTML = """<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
    <title>Navigation</title>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>Table of Contents</h1>
      <ol>
{nav_items}
      </ol>
    </nav>
  </body>
</html>"""

TOC_NCX = """<?xml version='1.0' encoding='UTF-8'?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_meta(project_id):
    with open(os.path.join(PROJECTS_DIR, project_id, 'meta.json')) as f:
        return json.load(f)

def load_build_config(project_id):
    xhtml_dir = os.path.join(PROJECTS_DIR, project_id, 'xhtml')
    path = os.path.join(PROJECTS_DIR, project_id, 'build_config.json')
    if os.path.exists(path):
        with open(path) as f:
            config = json.load(f)
        # Filter out chapters whose files no longer exist on disk
        for profile in ('digital', 'print'):
            if profile in config:
                config[profile]['chapters'] = [
                    c for c in config[profile].get('chapters', [])
                    if os.path.exists(os.path.join(xhtml_dir, c['filename']))
                ]
        return config
    return default_build_config(project_id)

def default_build_config(project_id):
    """Generate default build config from JSON config + project chapters.
    
    Loads default profiles (digital/print front/back matter) from global/config/build.json,
    then populates chapters from project meta.json.
    """
    # Load JSON config
    if not os.path.exists(BUILD_CONFIG_FILE):
        raise ValueError(f"build.json not found at {BUILD_CONFIG_FILE}")
    
    with open(BUILD_CONFIG_FILE) as f:
        config_data = json.load(f)
    
    # Load chapters from project metadata
    meta = load_meta(project_id)
    chapters = meta.get('chapters', [])
    
    # Build config from defaults + chapters
    config = {}
    for profile in ('digital', 'print'):
        profile_defaults = config_data.get('profiles', {}).get(profile, {})
        config[profile] = {
            'front_matter': profile_defaults.get('front_matter', []),
            'chapters': [{'filename': c['filename'], 'name': c['name'], 'type': c['type']} for c in chapters],
            'back_matter': profile_defaults.get('back_matter', []),
        }
    
    return config

def save_build_config(project_id, config):
    path = os.path.join(PROJECTS_DIR, project_id, 'build_config.json')
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)

def get_project_file(project_id, subdir, filename):
    """Return project-level override if it exists, else global."""
    project_path = os.path.join(PROJECTS_DIR, project_id, subdir, filename)
    if os.path.exists(project_path):
        return project_path
    global_path = os.path.join(GLOBAL_DIR, subdir, filename)
    if os.path.exists(global_path):
        return global_path
    return None

def read_xhtml_file(project_id, filename):
    """Read xhtml file — project first, then global templates.
    Fallback: credits_digital/print.xhtml → credits.xhtml for existing projects."""
    path = os.path.join(PROJECTS_DIR, project_id, 'xhtml', filename)
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return f.read()
    tmpl = os.path.join(GLOBAL_TEMPLATES, filename)
    if os.path.exists(tmpl):
        with open(tmpl, encoding='utf-8') as f:
            return f.read()
    # Fallback for existing projects that only have credits.xhtml
    if filename in ('credits_digital.xhtml', 'credits_print.xhtml'):
        return read_xhtml_file(project_id, 'credits.xhtml')
    return None

def fill_template(content, meta):
    """Replace {{TOKEN}} placeholders with project metadata, driven by tokens.json."""
    return _fill_tokens_util(content, meta)


# ── Footnote transform ────────────────────────────────────────────────────────

def _load_build_config_json():
    """Load build.json pattern config."""
    try:
        with open(BUILD_JSON, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _nnnn(n):
    """Zero-pad display_num to 4 digits."""
    return str(n).zfill(4)


def _transform_footnote_markers(content, fn_map, chapter_filename, profile, patterns):
    """Replace fn-marker spans in XHTML content with profile-specific patterns.

    Returns (transformed_content, list_of_footnote_entries_used).
    footnote_entries_used is only populated for digital profile.

    Strategy: use lxml to find all marker spans and collect their data, then
    serialize to string and do pattern substitution at string level — avoids
    all namespace issues when inserting HTML fragments into the lxml tree.
    """
    marker_cfg   = patterns.get('marker', {})
    XHTML_NS     = marker_cfg.get('xhtml_ns', 'http://www.w3.org/1999/xhtml')
    marker_class = marker_cfg.get('class', 'fn-marker')
    attr_id      = marker_cfg.get('attr_id', 'data-fn')
    attr_display = marker_cfg.get('attr_display', 'data-display')

    parser = etree.XMLParser(recover=True, encoding='utf-8')
    try:
        root = etree.fromstring(content.encode('utf-8'), parser)
    except Exception:
        return content, []

    chapter_base = os.path.splitext(chapter_filename)[0]
    used_entries  = []
    replacements  = []  # list of (fn_id, display_num, content_text) in order

    print(f"DEBUG: before spans", flush=True)
    for span in root.iter(f'{{{XHTML_NS}}}span'):
        if span.get('class') != marker_class:
            continue
        fn_id       = span.get(attr_id)
        display_str = span.get(attr_display, '')
        try:
            display_num = int(display_str)
        except (ValueError, TypeError):
            continue

        fn = next((f for f in fn_map.get('footnotes', []) if f.get('id') == fn_id), None)
        if not fn:
            continue

        content_text = fn.get('content', '')
        nnnn         = _nnnn(display_num)
        replacements.append((fn_id, display_num, nnnn, content_text))

        if profile == 'digital':
            used_entries.append({
                'display_num':  display_num,
                'nnnn':         nnnn,
                'content':      content_text,
                'chapter_base': chapter_base,
            })

    # Serialize to string — pattern substitution happens here, no fragment parsing
    transformed = etree.tostring(root, encoding='unicode', xml_declaration=False)
    if not transformed.startswith('<?xml'):
        transformed = "<?xml version='1.0' encoding='utf-8'?>\n" + transformed

    for fn_id, display_num, nnnn, content_text in replacements:
        print(f"DEBUG: fn_id={fn_id!r}", flush=True)
        print(f"DEBUG: transformed snippet={transformed[max(0,transformed.find('fn-marker')-20):transformed.find('fn-marker')+80]!r}", flush=True)
        
        # Match the serialized marker span regardless of attribute order
        marker_re = re.compile(
            rf'<(?:[\w:]+:)?span[^>]*class="{marker_class}"[^>]*data-fn="'
            + re.escape(str(fn_id))
            + r'"[^>]*/?>(?:</(?:[\w:]+:)?span>)?'
        )
        if profile == 'digital':
            tpl = patterns['digital']['inline']
            replacement = tpl.replace('{NNNN}', nnnn).replace('{N}', str(display_num))
        elif profile == 'print':
            tpl = patterns['print']['inline']
            replacement = tpl.replace('{N}', str(display_num)).replace('{CONTENT}', _esc(content_text))
        else:
            continue
        print(f"DEBUG: {profile} replacement = {replacement}", flush=True)
        transformed = marker_re.sub(replacement, transformed, count=1)
        print(f"DEBUG: snippet after sub={transformed[max(0,transformed.find('fn-marker')-20):transformed.find('fn-marker')+80]!r}", flush=True)

    return transformed, used_entries


def _build_footnotes_xhtml(entries, title, patterns):
    """Build footnotes.xhtml content from collected entries."""
    head = patterns['digital']['footnotes_xhtml']['head'].replace('{TITLE}', _esc(title))
    foot = patterns['digital']['footnotes_xhtml']['foot']
    entry_tpl = patterns['digital']['footnotes_xhtml']['entry']

    parts = [head]
    for e in sorted(entries, key=lambda x: x['display_num']):
        entry = (entry_tpl
                 .replace('{NNNN}',    e['nnnn'])
                 .replace('{N}',       str(e['display_num']))
                 .replace('{CONTENT}', _esc(e['content']))
                 .replace('{CHAPTER}', e['chapter_base']))
        parts.append(entry)
    parts.append(foot)
    return '\n'.join(parts)


# ── XHTML Validation & CSS Extraction ─────────────────────────────────────────

def validate_xhtml(content, filename=''):
    """Validate that content is well-formed XHTML/XML.
    
    Args:
        content: XHTML string to validate
        filename: optional filename for error messages
        
    Raises:
        ValueError: if XHTML is not valid XML
    """
    try:
        etree.fromstring(content.encode('utf-8'), parser=etree.XMLParser(recover=False))
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Invalid XHTML in {filename}: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error parsing XHTML in {filename}: {str(e)}")


def extract_css_from_xhtml(content):
    """Extract stylesheet filenames from XHTML <link> tags.
    
    Parses XHTML (assuming it's valid) and returns filenames from:
    <link rel="stylesheet" href="../styles/filename.css" />
    
    Args:
        content: XHTML string
        
    Returns:
        set of CSS filenames (e.g., {'main.css', 'digital-credits.css'})
    """
    css_files = set()
    try:
        root = etree.fromstring(content.encode('utf-8'), parser=etree.XMLParser(recover=True))
        # Find all <link rel="stylesheet"> elements in <head>
        for link in root.findall('.//{http://www.w3.org/1999/xhtml}link[@rel="stylesheet"]'):
            href = link.get('href', '').strip()
            if href and '.css' in href:
                # Extract filename from path: "../styles/main.css" → "main.css"
                css_filename = href.split('/')[-1]
                if css_filename:
                    css_files.add(css_filename)
    except Exception:
        # If parsing fails, silently return empty set (validation already checked XHTML)
        pass
    return css_files


def collect_and_validate_css(project_id, xhtml_dict):
    """Scan all XHTML content for CSS refs, validate each exists in project.
    
    Args:
        project_id: project directory name
        xhtml_dict: dict of {filename: content} for all XHTML files that will be in EPUB
        
    Returns:
        dict of {css_filename: full_path_on_disk}
        
    Raises:
        ValueError: if any CSS file referenced but not found in project/styles/
    """
    # First, validate all XHTML
    for filename, content in xhtml_dict.items():
        validate_xhtml(content, filename)
    
    # Collect unique CSS filenames from all XHTML
    css_files = set()
    for content in xhtml_dict.values():
        css_files.update(extract_css_from_xhtml(content))
    
    # Validate each CSS file exists in PROJECT (not global fallback)
    styles_needed = {}
    for css in sorted(css_files):
        project_css_path = os.path.join(PROJECTS_DIR, project_id, 'styles', css)
        if not os.path.exists(project_css_path):
            raise ValueError(
                f"CSS file not found in project: {css}\n"
                f"Expected at: {project_css_path}"
            )
        styles_needed[css] = project_css_path
    
    return styles_needed


# ── Routes ────────────────────────────────────────────────────────────────────

@build_bp.route('/api/projects/<project_id>/build-config', methods=['GET'])
def get_build_config(project_id):
    return jsonify(load_build_config(project_id))

@build_bp.route('/api/projects/<project_id>/build-config', methods=['POST'])
def save_build_config_route(project_id):
    config = request.json
    save_build_config(project_id, config)
    return jsonify({'ok': True})

@build_bp.route('/api/projects/<project_id>/build/<profile>', methods=['POST'])
def build_epub_route(project_id, profile):
    """POST to build/{profile} triggers EPUB build and returns the file."""
    try:
        print('before build_epub call')
        epub_path = build_epub(project_id, profile)
        return send_file(epub_path, as_attachment=True, mimetype='application/epub+zip',
                        download_name=f"{project_id}_{profile}.epub")
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@build_bp.route('/api/projects/<project_id>/build-toc', methods=['POST'])
def build_toc_route(project_id):
    """Generate TOC entries in the toc:true front matter file for print profile.
    
    For every print chapter with pag:true, reads the XHTML to extract:
      - outermost div id inside <body> → used as anchor
      - h1 with class from docx_converter.json → fallback to first h1 → link text
    Clears existing <li> inside <ul> in the toc:true file, then inserts fresh entries.
    """
    try:
        xhtml_dir = os.path.join(PROJECTS_DIR, project_id, 'xhtml')
        bc_path   = os.path.join(PROJECTS_DIR, project_id, 'build_config.json')

        if not os.path.exists(bc_path):
            return jsonify({'ok': False, 'error': 'build_config.json not found'}), 400

        with open(bc_path) as f:
            bc = json.load(f)

        print_cfg = bc.get('print', {})

        # Find toc:true front matter file
        toc_file = None
        for fm in print_cfg.get('front_matter', []):
            if fm.get('toc'):
                toc_file = fm.get('filename')
                break
        if not toc_file:
            return jsonify({'ok': False, 'error': 'No front matter item with toc:true found in print profile'}), 400

        toc_path = os.path.join(xhtml_dir, toc_file)
        if not os.path.exists(toc_path):
            return jsonify({'ok': False, 'error': f'TOC file not found: {toc_file}'}), 400

        # Read h1 class from docx_converter.json
        converter_json = os.path.join(GLOBAL_CONFIG, 'docx_converter.json')
        h1_class = None
        try:
            with open(converter_json) as f:
                conv = json.load(f)
            h1_class = conv.get('heading_map', {}).get('Heading 1', {}).get('class')
        except Exception:
            pass

        NS = 'http://www.w3.org/1999/xhtml'

        def get_div_id_and_text(filename):
            """Extract outermost div id and h1 text from a chapter XHTML file."""
            fpath = os.path.join(xhtml_dir, filename)
            if not os.path.exists(fpath):
                return None, None
            with open(fpath, encoding='utf-8') as f:
                content = f.read()
            try:
                root = etree.fromstring(content.encode('utf-8'),
                                        parser=etree.XMLParser(recover=True))
                body = root.find(f'{{{NS}}}body')
                if body is None:
                    body = root.find('body')
                if body is None:
                    return None, None

                # Outermost div inside body
                div_id = None
                for child in body:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if tag == 'div':
                        div_id = child.get('id')
                        break

                # h1 with specific class, fallback to first h1
                h1_text = None
                if h1_class:
                    for el in root.iter(f'{{{NS}}}h1'):
                        if h1_class in (el.get('class') or '').split():
                            h1_text = ''.join(el.itertext()).strip()
                            break
                if not h1_text:
                    for el in root.iter(f'{{{NS}}}h1'):
                        h1_text = ''.join(el.itertext()).strip()
                        if h1_text:
                            break

                return div_id, h1_text
            except Exception:
                return None, None

        # Collect li lines for pag:true chapters
        li_lines = []
        for ch in print_cfg.get('chapters', []):
            if not ch.get('pag', True):
                continue
            filename = ch.get('filename', '')
            if not filename:
                continue
            div_id, h1_text = get_div_id_and_text(filename)
            href = f"{filename}#{div_id}" if div_id else filename
            text = h1_text or ch.get('name', filename)
            li_lines.append(f'<li><a class="tocitem" href="{href}">{_esc(text)}</a></li>')

        # Read TOC file, clear existing <li> inside <ul>, insert new lines
        with open(toc_path, encoding='utf-8') as f:
            toc_content = f.read()

        try:
            toc_root = etree.fromstring(toc_content.encode('utf-8'),
                                        parser=etree.XMLParser(recover=True))
            # Find <ul> anywhere in the document
            ul = None
            for el in toc_root.iter(f'{{{NS}}}ul'):
                ul = el
                break
            if ul is None:
                for el in toc_root.iter('ul'):
                    ul = el
                    break
            if ul is None:
                return jsonify({'ok': False, 'error': 'No <ul> found in TOC file'}), 400

            # Clear existing <li> children
            for li in list(ul):
                ul.remove(li)

            # Insert new <li> elements
            for i, line in enumerate(li_lines):
                li_el = etree.fromstring(
                    f'<li xmlns="http://www.w3.org/1999/xhtml">{line[4:-5]}</li>'
                )
                if i > 0:
                    # Add a newline and 4 spaces of indentation
                    # We apply this to the 'tail' of the PREVIOUS element
                    ul[-1].tail = "\n    "
                ul.append(li_el)
            li_el.tail = "\n"

            updated = etree.tostring(toc_root, encoding='unicode', pretty_print=True)
            # Ensure XML declaration uses single quotes to match XHTML convention
            if not updated.startswith('<?xml'):
                updated = "<?xml version='1.0' encoding='UTF-8'?>\n" + updated

        except Exception as e:
            return jsonify({'ok': False, 'error': f'Failed to parse TOC file: {e}'}), 400

        with open(toc_path, 'w', encoding='utf-8') as f:
            f.write(updated)

        return jsonify({'ok': True, 'entries': len(li_lines)})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@build_bp.route('/api/projects/<project_id>/download/<filename>', methods=['GET'])
def download_epub(project_id, filename):
    """Download an EPUB file."""
    builds_dir = os.path.join(PROJECTS_DIR, project_id, 'epub')
    if os.path.exists(os.path.join(builds_dir, filename)):
        return send_file(os.path.join(builds_dir, filename), as_attachment=True)
    # Try global builds dir
    if os.path.exists(os.path.join(BUILDS_DIR, filename)):
        return send_file(os.path.join(BUILDS_DIR, filename), as_attachment=True)
    return jsonify({'ok': False}), 404


# ── EPUB Build Logic ──────────────────────────────────────────────────────────

def next_id():
    """Generate unique EPUB-compliant ID for manifest items.
    
    IDs must start with a letter [A-Za-z] per EPUB spec.
    Returns: "id" + 6 hex chars (e.g., "id94aa4a")
    """
    return 'id' + str(uuid.uuid4()).replace('-', '')[:6]

def build_epub(project_id, profile):
    """Build EPUB for the given project and profile (digital or print).
    
    Process:
    1. Load build config
    2. Collect XHTML files (front matter, chapters, back matter, footnotes, nav)
    3. Validate all XHTML is well-formed
    4. Extract and validate CSS references from XHTML
    5. Collect images and fonts
    6. Assemble EPUB with manifest, spine, content.opf
    
    Args:
        project_id: project directory name
        profile: 'digital' or 'print'
        
    Returns:
        path to built EPUB file
        
    Raises:
        ValueError: if XHTML invalid, CSS missing, or config error
    """
    if profile not in ('digital', 'print'):
        raise ValueError("Profile must be 'digital' or 'print'")
    
    is_print = profile == 'print'
    is_digital = profile == 'digital'
    
    # Load config & metadata
    meta = load_meta(project_id)
    build_config = load_build_config(project_id)
    prof = build_config.get(profile, {})

    # Load footnotes_map if available
    fn_map_path = os.path.join(PROJECTS_DIR, project_id, 'footnotes_map.json')
    fn_map      = {}
    if os.path.exists(fn_map_path):
        with open(fn_map_path, encoding='utf-8') as f:
            fn_map = json.load(f)

    # Load build patterns from build.json
    build_patterns = _load_build_config_json()
    fn_patterns    = build_patterns.get('footnotes', {})
    has_footnotes  = bool(fn_map.get('footnotes')) and bool(fn_map.get('footnotes_injected'))

    # Collected digital footnote entries across all chapters
    all_fn_entries = []
    
    title    = meta.get('title', 'Untitled')
    author   = meta.get('author', 'Unknown')
    language = meta.get('language', 'ca')
    cover_img = meta.get('cover_image')
    if (not cover_img) and is_digital:
        raise ValueError('Digital profile. No cover image set for this project. Please assign a cover image in the Build panel before building.')
    
    # Prepare manifest & spine tracking
    manifest_items = []
    spine_items = []
    files_to_write = {}  # path → content
    styles_needed = {}   # css_filename → src_path
    fonts_needed = {}    # font_filename → src_path
    images_needed = {}   # img_filename → src_path
    nav_entries = []     # (filename, display_name) tuples
    
    book_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    print('before Collect all XHTML that will be in the build')
    # ── Collect all XHTML that will be in the build ────────────────────────────
    all_xhtml_for_validation = {}  # {filename: content}
    
    def add_xhtml_from_project(section, item_id, section_name):
        """Load XHTML and add to tracking."""
        xhtml_file = f"{item_id}.xhtml"
        xhtml = read_xhtml_file(project_id, xhtml_file)
        if not xhtml:
            raise ValueError(f"XHTML not found: {xhtml_file}")
        filled = fill_template(xhtml, meta)
        all_xhtml_for_validation[xhtml_file] = filled
        return xhtml_file, filled
    
    def add_xhtml_to_spine(xhtml_file, content, display_name, include_in_nav=True):
        """Add XHTML to spine and manifest."""
        iid = next_id()
        manifest_items.append({'id': iid, 'href': f'text/{xhtml_file}',
                                'media_type': 'application/xhtml+xml', 'properties': None})
        spine_items.append(iid)
        files_to_write[f'text/{xhtml_file}'] = content
        if include_in_nav:
            nav_entries.append((xhtml_file, display_name))
        return iid
    
    # ── Blank page helper ─────────────────────────────────────────────────────
    def _blank_xhtml(n):
        """Return list of (filename, content) for n blank XHTML pages."""
        pages = []
        content = (
            "<?xml version='1.0' encoding='utf-8'?>\n"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\" "
            "xmlns:epub=\"http://www.idpf.org/2007/ops\" xml:lang=\"ca\">\n"
            "<head><title> </title></head>\n"
            "<body class=\"blankPage\"><p> </p></body>\n"
            "</html>"
        )
        for i in range(n):
            uid   = next_id()
            fname = f"blank_{uid}.xhtml"
            pages.append((fname, content))
        return pages

    def inject_blanks(count):
        for fname, content in _blank_xhtml(count):
            iid = next_id()
            manifest_items.append({'id': iid, 'href': f'text/{fname}',
                                   'media_type': 'application/xhtml+xml', 'properties': None})
            spine_items.append(iid)
            files_to_write[f'text/{fname}'] = content

    # ── Blank pages: before front matter ────────────────────────────────────
    if is_print:
        n = prof.get('blanks_before_front', 0)
        if n: inject_blanks(n)

    
    print('before add front matter')
    # Add front matter
    front_matter = prof.get('front_matter', [])
    for fm in front_matter:
        fid = fm.get('filename') or fm.get('id')
        if fid:
            fname, content = add_xhtml_from_project('front', fid.replace('.xhtml', ''), fid)
            add_xhtml_to_spine(fname, content, fm.get('label', fid),
                               include_in_nav=True if is_print else fm.get('nav', False))
    
    # ── Blank pages: after front matter ─────────────────────────────────────
    if is_print:
        n = prof.get('blanks_after_front', 0)
        if n: inject_blanks(n)

    print('before add Chapters')
    # Add chapters
    chapters = prof.get('chapters', [])
    for ch in chapters:
        fname, content = add_xhtml_from_project('chapter', ch['filename'].replace('.xhtml', ''), ch['filename'])
        # Transform fn-marker spans if footnotes are injected
        if has_footnotes and fn_patterns:
            content, entries = _transform_footnote_markers(content, fn_map, fname, profile, fn_patterns)
            all_fn_entries.extend(entries)
            all_xhtml_for_validation[fname] = content  # keep in sync with files_to_write
        add_xhtml_to_spine(fname, content, ch.get('name', fname),
                           include_in_nav=True if is_print else ch.get('nav', True))
    
    # ── OLD footnotes.json path — commented out, superseded by footnotes_map.json ──
    # footnotes = meta.get('footnotes', {})
    # if footnotes:
    #     fn_css_path = os.path.join(PROJECTS_DIR, project_id, 'styles', 'footnotes.css')
    #     if not os.path.exists(fn_css_path):
    #         raise ValueError(
    #             f"Footnotes exist but footnotes.css not found in project.\n"
    #             f"Expected at: {fn_css_path}"
    #         )
    #     all_xhtml_for_validation['footnotes.xhtml'] = (
    #         '<?xml version="1.0"?>'
    #         '<html xmlns="http://www.w3.org/1999/xhtml">'
    #         '<head><link rel="stylesheet" href="../styles/footnotes.css"/></head>'
    #         '<body></body></html>'
    #     )
    #     fn_items = '\n'.join(f'      <li id="fn{n}">{_esc(text)}</li>' for n, text in footnotes.items())
    #     fn_xhtml = (
    #         '<?xml version="1.0" encoding="UTF-8"?>\n'
    #         '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
    #         '  <head>\n'
    #         '    <link rel="stylesheet" href="../styles/footnotes.css" type="text/css"/>\n'
    #         '    <title>Notes</title>\n'
    #         '    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
    #         '  </head>\n'
    #         '  <body>\n'
    #         '    <p class="notesTitle">Notes</p>\n'
    #         '    <ol>\n'
    #         + fn_items +
    #         '    </ol>\n'
    #         '  </body>\n'
    #         '</html>'
    #     )
    #     all_xhtml_for_validation['footnotes.xhtml'] = fn_xhtml
    #     fn_iid = next_id()
    #     manifest_items.append({'id': fn_iid, 'href': 'text/footnotes.xhtml',
    #                             'media_type': 'application/xhtml+xml', 'properties': None})
    #     spine_items.append(fn_iid)
    #     files_to_write['text/footnotes.xhtml'] = fn_xhtml


    print('after chapters loop')
    # ── New footnotes.xhtml for digital (from footnotes_map.json) ─────────────
    if is_digital and all_fn_entries:
        title = meta.get('title', 'Notes')
        try:
            fn_xhtml = _build_footnotes_xhtml(all_fn_entries, title, fn_patterns)
        except Exception as e:
            raise ValueError(f"Could not build footnotes.xhtml: {e}")
        all_xhtml_for_validation['footnotes.xhtml'] = fn_xhtml
        fn_iid = next_id()
        manifest_items.append({'id': fn_iid, 'href': 'text/footnotes.xhtml',
                                'media_type': 'application/xhtml+xml', 'properties': None})
        spine_items.append(fn_iid)
        files_to_write['text/footnotes.xhtml'] = fn_xhtml
    
    # ── Blank pages: before back matter ─────────────────────────────────────
    if is_print:
        n = prof.get('blanks_before_back', 0)
        if n: inject_blanks(n)

    # Add back matter
    back_matter = prof.get('back_matter', [])
    for bm in back_matter:
        bid = bm.get('filename') or bm.get('id')
        if bid:
            fname, content = add_xhtml_from_project('back', bid.replace('.xhtml', ''), bid)
            add_xhtml_to_spine(fname, content, bm.get('label', bid),
                               include_in_nav=True if is_print else bm.get('nav', False))

    # ── Blank pages: after back matter ──────────────────────────────────────
    if is_print:
        n = prof.get('blanks_after_back', 0)
        if n: inject_blanks(n)
    
    # ── Inject override CSS for digital builds ───────────────────────────────
    if not is_print:
        try:
            with open(GLOBAL_JSON) as _f:
                _global = json.load(_f)
            override_css = _global.get('override_css', {}).get('digital', 'digital-overrides.css')
        except Exception:
            override_css = 'digital-overrides.css'
        override_css_path = os.path.join(PROJECTS_DIR, project_id, 'styles', override_css)

        print("BEFORE INDEX AND RFIND IN DIGITAL")

        if os.path.exists(override_css_path):
            _link_tag = f'<link rel="stylesheet" type="text/css" href="../styles/{override_css}"/>'
            _injected = {}
            for _fname, _xcontent in all_xhtml_for_validation.items():
                if '<link rel="stylesheet"' in _xcontent and _link_tag not in _xcontent:
                    # Insert after last existing <link rel="stylesheet".../>
                    _last = _xcontent.rfind('<link rel="stylesheet"')
                    _end  = _xcontent.index('/>', _last) + 2
                    _xcontent = _xcontent[:_end] + '\n    ' + _link_tag + _xcontent[_end:]
                _injected[_fname] = _xcontent
            all_xhtml_for_validation = _injected
            # Sync back to files_to_write
            for _fname, _xcontent in _injected.items():
                if f'text/{_fname}' in files_to_write:
                    files_to_write[f'text/{_fname}'] = _xcontent

    # ── Inject override CSS for print builds ─────────────────────────────────
    else:
        try:
            with open(GLOBAL_JSON) as _f:
                _global = json.load(_f)
            override_css = _global.get('override_css', {}).get('print', 'print-overrides.css')
        except Exception:
            override_css = 'print-overrides.css'
        override_css_path = os.path.join(PROJECTS_DIR, project_id, 'styles', override_css)
        if os.path.exists(override_css_path):
            _link_tag = f'<link rel="stylesheet" type="text/css" href="../styles/{override_css}" media="print"/>'
            _injected = {}
            for _fname, _xcontent in all_xhtml_for_validation.items():
                if '<link rel="stylesheet"' in _xcontent and _link_tag not in _xcontent:
                    _last = _xcontent.rfind('<link rel="stylesheet"')
                    _end  = _xcontent.index('/>', _last) + 2
                    _xcontent = _xcontent[:_end] + '\n    ' + _link_tag + _xcontent[_end:]
                _injected[_fname] = _xcontent
            all_xhtml_for_validation = _injected
            # Sync back to files_to_write
            for _fname, _xcontent in _injected.items():
                if f'text/{_fname}' in files_to_write:
                    files_to_write[f'text/{_fname}'] = _xcontent

    # ── Validate all XHTML and extract CSS ──────────────────────────────────────
    styles_needed = collect_and_validate_css(project_id, all_xhtml_for_validation)
    
    # ── nav.xhtml ─────────────────────────────────────────────────────────────
    nav_items_str = '\n'.join(
        f'        <li><a href="{fname}">{_esc(name)}</a></li>'
        for fname, name in nav_entries
    )
    nav_content = NAV_XHTML.format(nav_items=nav_items_str)
    manifest_items.append({'id': 'nav', 'href': 'text/nav.xhtml',
                           'media_type': 'application/xhtml+xml', 'properties': 'nav'})
    files_to_write['text/nav.xhtml'] = nav_content
    
    # ── toc.ncx ───────────────────────────────────────────────────────────────
    nav_points_str = ''
    for i, (fname, name) in enumerate(nav_entries, 1):
        nav_points_str += f"""    <navPoint id="np{i}" playOrder="{i}">
      <navLabel><text>{_esc(name)}</text></navLabel>
      <content src="text/{fname}"/>
    </navPoint>\n"""
    toc_content = TOC_NCX.format(book_id=book_id, title=_esc(title),
                                  nav_points=nav_points_str)
    manifest_items.append({'id': 'ncx', 'href': 'toc.ncx',
                           'media_type': 'application/x-dtbncx+xml', 'properties': None})
    files_to_write['toc.ncx'] = toc_content
    
    # ── CSS manifest entries ──────────────────────────────────────────────────
    for css in sorted(styles_needed.keys()):
        cid = css.replace('.', '_').replace('-', '_')
        manifest_items.append({'id': cid, 'href': f'styles/{css}',
                               'media_type': 'text/css', 'properties': None})
    
    # ── Collect images from XHTML ─────────────────────────────────────────────
    for content in all_xhtml_for_validation.values():
        try:
            root = etree.fromstring(content.encode('utf-8'), parser=etree.XMLParser(recover=True))
            for img in root.findall('.//{http://www.w3.org/1999/xhtml}img'):
                src = img.get('src', '').strip()
                if src and '..' in src:
                    # Extract filename: "../images/image.jpg" → "image.jpg"
                    img_filename = src.split('/')[-1]
                    if img_filename:
                        img_src = get_project_file(project_id, 'images', img_filename)
                        if img_src:
                            images_needed[img_filename] = img_src
        except Exception:
            pass
    
    if is_print:
        # ── Collect fonts from project, fall back to global ──────────────────────
        project_fonts_dir = os.path.join(PROJECTS_DIR, project_id, 'fonts')
        if os.path.isdir(project_fonts_dir):
            for font in os.listdir(project_fonts_dir):
                if font.endswith(('.ttf', '.otf', '.woff', '.woff2')):
                    fonts_needed[font] = os.path.join(project_fonts_dir, font)

        # Global fonts fallback — add any not already provided by project
        if os.path.isdir(GLOBAL_FONTS):
            for font in os.listdir(GLOBAL_FONTS):
                if font.endswith(('.ttf', '.otf', '.woff', '.woff2')) and font not in fonts_needed:
                    fonts_needed[font] = os.path.join(GLOBAL_FONTS, font)
        
        # ── Font manifest entries ─────────────────────────────────────────────────
        font_mime = {'ttf': 'application/vnd.ms-opentype', 'otf': 'application/vnd.ms-opentype',
                    'woff': 'application/font-woff', 'woff2': 'application/font-woff2'}
        for i, font in enumerate(sorted(fonts_needed.keys())):
            ext = font.rsplit('.', 1)[-1].lower()
            manifest_items.append({'id': f'font{i}', 'href': f'fonts/{font}',
                                'media_type': font_mime.get(ext, 'application/octet-stream'),
                                'properties': None})
    
    # ── Image manifest entries ────────────────────────────────────────────────
    img_mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif'}
    
    # Cover image (with cover-image property, never in spine)
    if cover_img:
        cover_src = get_project_file(project_id, 'images', cover_img)
        if cover_src:
            ext  = cover_img.rsplit('.', 1)[-1].lower()
            mime = img_mime.get(ext, 'image/jpeg')
            manifest_items.append({'id': 'cover', 'href': f'images/{cover_img}',
                                   'media_type': mime, 'properties': 'cover-image'})
            images_needed[cover_img] = cover_src
    
    # Other images
    for i, img in enumerate(sorted(images_needed.keys())):
        if cover_img and img == cover_img:
            continue
        ext  = img.rsplit('.', 1)[-1].lower()
        mime = img_mime.get(ext, 'image/jpeg')
        manifest_items.append({'id': f'img{i}', 'href': f'images/{img}',
                               'media_type': mime, 'properties': None})
    
    # ── content.opf ──────────────────────────────────────────────────────────
    opf = _build_opf(book_id, title, author, language, now, manifest_items, spine_items, is_print, cover_img)
    files_to_write['content.opf'] = opf
    
    # ── Write EPUB zip ────────────────────────────────────────────────────────
    if is_print:
        epub_dir = os.path.join(PROJECTS_DIR, project_id, 'epub')
        os.makedirs(epub_dir, exist_ok=True)
        # Find next version number
        existing = [f for f in os.listdir(epub_dir) if f.endswith('_print.epub') or '_print_v' in f]
        max_v = 0
        for fname in existing:
            m = re.search(r'_print_v(\d+)\.epub$', fname)
            if m:
                max_v = max(max_v, int(m.group(1)))
        next_v    = max_v + 1
        epub_path = os.path.join(epub_dir, f"{project_id}_print_v{next_v}.epub")
    else:
        os.makedirs(BUILDS_DIR, exist_ok=True)
        epub_path = os.path.join(BUILDS_DIR, f"{project_id}_digital.epub")
    
    with zipfile.ZipFile(epub_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be first and uncompressed
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                    compress_type=zipfile.ZIP_STORED)
        # META-INF/container.xml
        zf.writestr('META-INF/container.xml', _container_xml())
        # content.opf
        zf.writestr('OEBPS/content.opf', files_to_write.pop('content.opf'))
        # toc.ncx
        if 'toc.ncx' in files_to_write:
            zf.writestr('OEBPS/toc.ncx', files_to_write.pop('toc.ncx'))
        # XHTML files
        for path, content in files_to_write.items():
            if isinstance(content, str):
                zf.writestr(f'OEBPS/{path}', content.encode('utf-8'))
            else:
                zf.writestr(f'OEBPS/{path}', content)
        # CSS files (original names, no mapping)
        for css, src_path in styles_needed.items():
            with open(src_path, 'rb') as f:
                zf.writestr(f'OEBPS/styles/{css}', f.read())
        # Font files
        for font, src_path in sorted(fonts_needed.items()):
            with open(src_path, 'rb') as f:
                zf.writestr(f'OEBPS/fonts/{font}', f.read())
        # Images
        for img, src_path in sorted(images_needed.items()):
            with open(src_path, 'rb') as f:
                zf.writestr(f'OEBPS/images/{img}', f.read())
    
    return epub_path


# ── OPF / container builders ──────────────────────────────────────────────────

def _build_opf(book_id, title, author, language, modified, manifest_items, spine_items, is_print, cover_img=None):
    """Build content.opf manifest and spine."""
    manifest_lines = []
    for item in manifest_items:
        props = f' properties="{item["properties"]}"' if item.get('properties') else ''
        manifest_lines.append(
            f'    <item id="{item["id"]}" href="{item["href"]}" '
            f'media-type="{item["media_type"]}"{props}/>'
        )

    spine_lines = [f'    <itemref idref="{sid}"/>' for sid in spine_items]
    
    # Format timestamp: CCYY-MM-DDThh:mm:ssZ (remove microseconds, add Z for UTC)
    # Input: 2026-03-06T23:37:51.927718 → Output: 2026-03-06T23:37:51Z
    if '.' in modified:
        timestamp = modified.split('.')[0] + 'Z'
    else:
        timestamp = modified.rstrip('Z') + 'Z'
    
    # Cover metadata (if cover image exists)
    cover_meta = '    <meta name="cover" content="cover"/>\n' if cover_img else ''

    return f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title id="id-1">{_esc(title)}</dc:title>
    <dc:creator id="id-2">{_esc(author)}</dc:creator>
    <dc:identifier id="BookID">{book_id}</dc:identifier>
    <dc:date>{modified[:10]}</dc:date>
    <dc:language>{language}</dc:language>
    <dc:publisher>BonPort</dc:publisher>
    <meta refines="#id-1" property="title-type">main</meta>
    <meta refines="#id-2" property="role" scheme="marc:relators">aut</meta>
    <meta property="dcterms:modified" scheme="dcterms:W3CDTF">{timestamp}</meta>
{cover_meta}  </metadata>
  <manifest>
{chr(10).join(manifest_lines)}
  </manifest>
  <spine toc="ncx">
{chr(10).join(spine_lines)}
  </spine>
</package>"""

def _container_xml():
    """Build META-INF/container.xml."""
    return """<?xml version='1.0' encoding='UTF-8'?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

def _esc(s):
    """XML escape helper."""
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')