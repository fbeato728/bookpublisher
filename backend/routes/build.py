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

PROJECTS_DIR  = '/srv/bookpublisher/projects'
GLOBAL_DIR    = '/srv/bookpublisher/global'   # global CSS, fonts, templates
BUILDS_DIR    = '/srv/bookpublisher/builds'   # output EPUBs

# ── Global asset paths ────────────────────────────────────────────────────────
GLOBAL_STYLES = os.path.join(GLOBAL_DIR, 'styles')
GLOBAL_FONTS  = os.path.join(GLOBAL_DIR, 'fonts')
GLOBAL_TEMPLATES = os.path.join(GLOBAL_DIR, 'templates')  # blank04, title_only, nav, toc
GLOBAL_CONFIG = os.path.join(GLOBAL_DIR, 'config')
BUILD_CONFIG_FILE = os.path.join(GLOBAL_CONFIG, 'build.json')  # default build profiles

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

def fill_template(content, meta, cover_img=''):
    """Replace {{TOKEN}} placeholders with project metadata."""
    replacements = {
        '{{TITLE}}':          meta.get('title', ''),
        '{{AUTHOR}}':         meta.get('author', ''),
        '{{COVER_IMAGE}}':    cover_img,
        '{{FIRST_EDITION}}':  meta.get('first_edition', ''),
        '{{ORIGINAL_TITLE}}': meta.get('original_title', meta.get('title', '')),
        '{{ORIGINAL_YEAR}}':  meta.get('original_year', ''),
        '{{ORIGINAL_AUTHOR}}':meta.get('original_author', meta.get('author', '')),
        '{{TRANSLATOR}}':     meta.get('translator', ''),
        '{{TRANSLATION_YEAR}}': meta.get('translation_year', ''),
        '{{ISBN}}':           meta.get('isbn', ''),
        '{{DEPOT_LEGAL}}':    meta.get('depot_legal', ''),
    }
    for token, value in replacements.items():
        content = content.replace(token, value)
    return content


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
        epub_path = build_epub(project_id, profile)
        return send_file(epub_path, as_attachment=True, mimetype='application/epub+zip',
                        download_name=f"{project_id}_{profile}.epub")
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
    
    # Load config & metadata
    meta = load_meta(project_id)
    build_config = load_build_config(project_id)
    prof = build_config.get(profile, {})
    
    title    = meta.get('title', 'Untitled')
    author   = meta.get('author', 'Unknown')
    language = meta.get('language', 'ca')
    cover_img = meta.get('cover_image')
    
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
    
    # ── Collect all XHTML that will be in the build ────────────────────────────
    all_xhtml_for_validation = {}  # {filename: content}
    
    def add_xhtml_from_project(section, item_id, section_name):
        """Load XHTML and add to tracking."""
        xhtml_file = f"{item_id}.xhtml"
        xhtml = read_xhtml_file(project_id, xhtml_file)
        if not xhtml:
            raise ValueError(f"XHTML not found: {xhtml_file}")
        filled = fill_template(xhtml, meta, cover_img)
        all_xhtml_for_validation[xhtml_file] = filled
        return xhtml_file, filled
    
    def add_xhtml_to_spine(xhtml_file, content, display_name):
        """Add XHTML to spine and manifest."""
        iid = next_id()
        manifest_items.append({'id': iid, 'href': f'text/{xhtml_file}',
                                'media_type': 'application/xhtml+xml', 'properties': None})
        spine_items.append(iid)
        files_to_write[f'text/{xhtml_file}'] = content
        nav_entries.append((xhtml_file, display_name))
        return iid
    
    # Add front matter
    front_matter = prof.get('front_matter', [])
    for fm in front_matter:
        fid = fm.get('filename') or fm.get('id')
        if fid:
            fname, content = add_xhtml_from_project('front', fid.replace('.xhtml', ''), fid)
            add_xhtml_to_spine(fname, content, fm.get('label', fid))
    
    # Add chapters
    chapters = prof.get('chapters', [])
    for ch in chapters:
        fname, content = add_xhtml_from_project('chapter', ch['filename'].replace('.xhtml', ''), ch['filename'])
        add_xhtml_to_spine(fname, content, ch.get('name', fname))
    
    # Add footnotes if any
    footnotes = meta.get('footnotes', {})
    if footnotes:
        # Validate footnotes.css exists in project
        fn_css_path = os.path.join(PROJECTS_DIR, project_id, 'styles', 'footnotes.css')
        if not os.path.exists(fn_css_path):
            raise ValueError(
                f"Footnotes exist but footnotes.css not found in project.\n"
                f"Expected at: {fn_css_path}"
            )
        all_xhtml_for_validation['footnotes.xhtml'] = (
            '<?xml version="1.0"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            '<head><link rel="stylesheet" href="../styles/footnotes.css"/></head>'
            '<body></body></html>'
        )
        fn_items = '\n'.join(f'      <li id="fn{n}">{_esc(text)}</li>' for n, text in footnotes.items())
        fn_xhtml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            '  <head>\n'
            '    <link rel="stylesheet" href="../styles/footnotes.css" type="text/css"/>\n'
            '    <title>Notes</title>\n'
            '    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
            '  </head>\n'
            '  <body>\n'
            '    <p class="notesTitle">Notes</p>\n'
            '    <ol>\n'
            + fn_items +
            '    </ol>\n'
            '  </body>\n'
            '</html>'
        )
        all_xhtml_for_validation['footnotes.xhtml'] = fn_xhtml
        fn_iid = next_id()
        manifest_items.append({'id': fn_iid, 'href': 'text/footnotes.xhtml',
                                'media_type': 'application/xhtml+xml', 'properties': None})
        spine_items.append(fn_iid)
        files_to_write['text/footnotes.xhtml'] = fn_xhtml
    
    # Add back matter
    back_matter = prof.get('back_matter', [])
    for bm in back_matter:
        bid = bm.get('filename') or bm.get('id')
        if bid:
            fname, content = add_xhtml_from_project('back', bid.replace('.xhtml', ''), bid)
            add_xhtml_to_spine(fname, content, bm.get('label', bid))
    
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
    
    # ── Collect fonts from project ────────────────────────────────────────────
    project_fonts_dir = os.path.join(PROJECTS_DIR, project_id, 'fonts')
    if os.path.isdir(project_fonts_dir):
        for font in os.listdir(project_fonts_dir):
            if font.endswith(('.ttf', '.otf', '.woff', '.woff2')):
                fonts_needed[font] = os.path.join(project_fonts_dir, font)
    
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
    opf = _build_opf(book_id, title, author, language, now, manifest_items, spine_items, is_print)
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

def _build_opf(book_id, title, author, language, modified, manifest_items, spine_items, is_print):
    """Build content.opf manifest and spine."""
    manifest_lines = []
    for item in manifest_items:
        props = f' properties="{item["properties"]}"' if item.get('properties') else ''
        manifest_lines.append(
            f'    <item id="{item["id"]}" href="{item["href"]}" '
            f'media-type="{item["media_type"]}"{props}/>'
        )

    spine_lines = [f'    <itemref idref="{sid}"/>' for sid in spine_items]

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
    <meta property="dcterms:modified" scheme="dcterms:W3CDTF">{modified}</meta>
  </metadata>
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