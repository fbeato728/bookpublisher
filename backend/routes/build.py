import os
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
    path = os.path.join(PROJECTS_DIR, project_id, 'build_config.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default_build_config(project_id)

def default_build_config(project_id):
    """Generate a sensible default build config from the project's chapters."""
    meta = load_meta(project_id)
    chapters = meta.get('chapters', [])
    return {
        'digital': {
            'front_matter': [
                {'id': 'cover_digital',  'label': 'Cover (digital)', 'type': 'titlepage',  'enabled': True},
                {'id': 'credits_digital', 'label': 'Credits',     'type': 'credits',    'enabled': True},
            ],
            'chapters': [{'filename': c['filename'], 'name': c['name'], 'type': c['type']} for c in chapters],
            'back_matter': [],
        },
        'print': {
            'front_matter': [
                {'id': 'title_only',        'label': 'Title only page',   'type': 'title_only',   'enabled': True},
                {'id': 'credits_print',   'label': 'Credits',           'type': 'credits',      'enabled': True},
                {'id': 'inside_cover_print',  'label': 'Inside cover (print)', 'type': 'titlepage',  'enabled': True},
                {'id': 'taula',             'label': 'Table of contents', 'type': 'taula',        'enabled': True},
            ],
            'chapters': [{'filename': c['filename'], 'name': c['name'], 'type': c['type']} for c in chapters],
            'back_matter': [],
        },
    }

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


# ── Routes ────────────────────────────────────────────────────────────────────

@build_bp.route('/api/projects/<project_id>/build-config', methods=['GET'])
def get_build_config(project_id):
    return jsonify(load_build_config(project_id))

@build_bp.route('/api/projects/<project_id>/build-config', methods=['POST'])
def save_build_config_route(project_id):
    config = request.json
    save_build_config(project_id, config)
    return jsonify({'ok': True})

@build_bp.route('/api/projects/<project_id>/build/epub', methods=['POST'])
def build_epub(project_id):
    """
    Assemble and return an EPUB for the given profile.
    Body: { "profile": "digital" | "print" }
    """
    profile = request.json.get('profile', 'digital')
    if profile not in ('digital', 'print'):
        return jsonify({'error': 'Invalid profile'}), 400

    meta   = load_meta(project_id)
    config = load_build_config(project_id)

    try:
        epub_path = assemble_epub(project_id, meta, config, profile)
        filename  = f"{project_id}_{profile}.epub"
        return send_file(epub_path, as_attachment=True, download_name=filename,
                         mimetype='application/epub+zip')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@build_bp.route('/api/projects/<project_id>/build/hyphenate', methods=['POST'])
def hyphenate(project_id):
    """Stub — hyphenation coming once calibre-debug setup is confirmed."""
    return jsonify({'error': 'Hyphenation not yet implemented'}), 501

@build_bp.route('/api/projects/<project_id>/build/convert-pdf', methods=['POST'])
def convert_pdf(project_id):
    """Stub — PDF conversion coming once Prince/ebook-convert setup is confirmed."""
    return jsonify({'error': 'PDF conversion not yet implemented'}), 501


# ── EPUB assembler ────────────────────────────────────────────────────────────

def assemble_epub(project_id, meta, config, profile):
    os.makedirs(BUILDS_DIR, exist_ok=True)

    title     = meta.get('title', 'Untitled')
    author    = meta.get('author', '')
    language  = meta.get('language', 'ca')
    book_uuid = str(uuid.uuid4()).upper()
    book_id   = f"UUID:{book_uuid}"
    now       = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    prof_config  = config[profile]
    front_matter = [f for f in prof_config.get('front_matter', []) if f.get('enabled', True)]
    chapters     = prof_config.get('chapters', [])
    back_matter  = [f for f in prof_config.get('back_matter',  []) if f.get('enabled', True)]

    is_print = (profile == 'print')

    # Build spine item list: each entry is (epub_id, href, media_type, properties, content)
    # content is the raw bytes/string to write into the zip
    spine_items   = []   # ordered list of ids for spine
    manifest_items = []  # all items for manifest
    images_needed  = {}  # basename -> source path
    styles_needed  = {}  # basename -> source path
    fonts_needed   = {}  # basename -> source path

    xhtml_dir = os.path.join(PROJECTS_DIR, project_id, 'xhtml')

    # ── Determine CSS set ─────────────────────────────────────────────────────
    # main.css inside the EPUB always maps to either digital.css or print.css
    # (XHTML files link to ../styles/main.css — name is fixed inside EPUB)
    main_css_name = 'print.css' if is_print else 'digital.css'
    main_css_src  = get_project_file(project_id, 'styles', main_css_name)
    if main_css_src:
        styles_needed['main.css'] = main_css_src   # packaged as main.css inside EPUB

    # credits.css — same pattern as main.css, pick profile version, package as credits.css
    credits_css_name = 'print-credits.css' if is_print else 'digital-credits.css'
    credits_css_src  = get_project_file(project_id, 'styles', credits_css_name)
    if credits_css_src:
        styles_needed['credits.css'] = credits_css_src

    # Print-only extras
    if is_print:
        for css in ['book_big_title.css', 'taula.css']:
            src = get_project_file(project_id, 'styles', css)
            if src:
                styles_needed[css] = src

    # ── Determine font set (print only) ───────────────────────────────────────
    # Scan global/fonts then project/fonts — project file wins over global for same name.
    if is_print:
        font_exts = {'.ttf', '.otf', '.woff', '.woff2'}
        for fonts_dir in [GLOBAL_FONTS,
                          os.path.join(PROJECTS_DIR, project_id, 'fonts')]:
            if not os.path.isdir(fonts_dir):
                continue
            for fname in sorted(os.listdir(fonts_dir)):
                if os.path.splitext(fname)[1].lower() in font_exts:
                    fonts_needed[fname] = os.path.join(fonts_dir, fname)

    # ── Collect cover image (from meta.json, EPUB only) ─────────────────────
    cover_img = meta.get('cover_image', '') if not is_print else ''
    # ── Load footnotes ────────────────────────────────────────────────────────
    import json as _json
    _fn_path = os.path.join(PROJECTS_DIR, project_id, 'footnotes.json')
    footnotes = {}  # {int: str}
    if os.path.exists(_fn_path):
        with open(_fn_path, encoding='utf-8') as _f:
            footnotes = {int(k): v for k, v in _json.load(_f).items()}

    def apply_footnotes_print(content):
        """Replace <!--fn:N--> or <!--fn:N:variant--> with Prince inline span."""
        def _repl(m):
            n       = int(m.group(1))
            variant = m.group(2) if m.group(2) else 'def'
            text    = footnotes.get(n, '[footnote %d not found]' % n)
            return '<span class="fn %s">%s</span>' % (variant, text)
        return re.sub(r'<!--fn:(\d+)(?::(\w+))?-->', _repl, content)

    def apply_footnotes_digital(content):
        """Replace <!--fn:N--> or <!--fn:N:variant--> with EPUB noteref link."""
        def _repl(m):
            n = int(m.group(1))
            return ('<a epub:type="noteref" href="../text/footnotes.xhtml#fn%d">'
                    '<sup>%d</sup></a>') % (n, n)
        return re.sub(r'<!--fn:(\d+)(?::(\w+))?-->', _repl, content)


    # ── Collect inline images from all XHTML files ────────────────────────────
    def collect_images_from_xhtml(content):
        """Find any src="images/..." references and queue them."""
        import re
        for m in re.findall(r'src=["\'](?:\.\./)?images/([^"\']+)["\']', content):
            src = get_project_file(project_id, 'images', m)
            if src:
                images_needed[m] = src

    # ── Build spine entries ───────────────────────────────────────────────────
    item_counter = [1]

    def next_id(prefix='id'):
        i = item_counter[0]
        item_counter[0] += 1
        return f"{prefix}{i}"

    def add_xhtml_item(item_id, href_name, content, properties=None, in_spine=True):
        """Register an XHTML item in manifest + optionally spine."""
        props_str = f' properties="{properties}"' if properties else ''
        manifest_items.append({
            'id':         item_id,
            'href':       f'text/{href_name}',
            'media_type': 'application/xhtml+xml',
            'properties': properties,
        })
        if in_spine:
            spine_items.append(item_id)
        collect_images_from_xhtml(content)
        return content

    files_to_write = {}  # epub-internal path -> content (str or bytes)

    # ── Front matter ──────────────────────────────────────────────────────────
    blank_counter = [0]

    def add_blank(count=1):
        for _ in range(count):
            blank_counter[0] += 1
            bid = f"blank_{blank_counter[0]}"
            iid = next_id('blank')
            manifest_items.append({
                'id': iid, 'href': f'text/{bid}.xhtml',
                'media_type': 'application/xhtml+xml', 'properties': 'scripted',
            })
            spine_items.append(iid)
            files_to_write[f'text/{bid}.xhtml'] = BLANK_XHTML

    def add_xhtml_from_project(filename, epub_filename=None, properties=None):
        """Load xhtml file (project override → global template), fill tokens, add to spine."""
        if epub_filename is None:
            epub_filename = filename
        content = read_xhtml_file(project_id, filename)
        if content is None:
            content = f"""<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><link rel="stylesheet" href="../styles/main.css" type="text/css"/>
  <title>{filename}</title></head>
  <body><p class="normalText"></p></body>
</html>"""
        content = fill_template(content, meta, cover_img)
        iid = next_id()
        manifest_items.append({'id': iid, 'href': f'text/{epub_filename}',
                               'media_type': 'application/xhtml+xml', 'properties': properties})
        spine_items.append(iid)
        collect_images_from_xhtml(content)
        files_to_write[f'text/{epub_filename}'] = content
        return iid

    if is_print:
        add_blank(2)
        for fm in front_matter:
            ftype = fm.get('type')
            fid   = fm.get('id')
            if ftype == 'title_only':
                add_xhtml_from_project('title_only.xhtml')
            elif ftype == 'credits':
                add_xhtml_from_project(f"{fid}.xhtml")
            elif ftype == 'titlepage':
                add_xhtml_from_project('inside_cover_print.xhtml', properties='scripted')
                add_blank(1)
            elif ftype == 'taula':
                add_xhtml_from_project('taula.xhtml', properties='scripted')
            else:
                # custom / ded / prologue / etc
                add_xhtml_from_project(f"{fid}.xhtml")

    else:
        for fm in front_matter:
            ftype = fm.get('type')
            fid   = fm.get('id')
            if ftype == 'titlepage':
                add_xhtml_from_project('cover_digital.xhtml')
            elif ftype == 'credits':
                add_xhtml_from_project(f"{fid}.xhtml")
            else:
                add_xhtml_from_project(f"{fid}.xhtml")

    # ── Chapters ──────────────────────────────────────────────────────────────
    nav_entries = []  # (filename, name) for nav/toc
    digital_fn_refs = []  # ordered list of fn numbers referenced (digital only)

    for ch in chapters:
        fname   = ch['filename']
        ch_name = ch.get('name', fname)
        content = read_xhtml_file(project_id, fname)
        if content is None:
            continue
        if is_print:
            content = apply_footnotes_print(content)
        else:
            for m in re.finditer(r'<!--fn:(\d+)(?::(\w+))?-->', content):
                n = int(m.group(1))
                if n not in digital_fn_refs:
                    digital_fn_refs.append(n)
            content = apply_footnotes_digital(content)
        iid = next_id()
        manifest_items.append({'id': iid, 'href': f'text/{fname}',
                                'media_type': 'application/xhtml+xml', 'properties': None})
        spine_items.append(iid)
        files_to_write[f'text/{fname}'] = content
        collect_images_from_xhtml(content)
        nav_entries.append((fname, ch_name))

    # ── footnotes.xhtml (digital only) ───────────────────────────────────────
    if not is_print and digital_fn_refs and footnotes:
        fn_items = ''
        for n in digital_fn_refs:
            text = footnotes.get(n, '')
            fn_items += (
                '      <li id="fn%d" epub:type="footnote">\n'
                '        <p class="note"><a href="#fn%d-ref">%d.</a> %s</p>\n'
                '      </li>\n'
            ) % (n, n, n, text)
        fn_xhtml = (
            "<?xml version='1.0' encoding='UTF-8'?>\n"
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            '  <head>\n'
            '    <link rel="stylesheet" href="../styles/main.css" type="text/css"/>\n'
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
        fn_iid = next_id()
        manifest_items.append({'id': fn_iid, 'href': 'text/footnotes.xhtml',
                                'media_type': 'application/xhtml+xml', 'properties': None})
        spine_items.append(fn_iid)
        files_to_write['text/footnotes.xhtml'] = fn_xhtml

    # ── Back matter ───────────────────────────────────────────────────────────
    for bm in back_matter:
        fid = bm.get('id')
        if fid:
            add_xhtml_from_project('back', fid, fid)

    # For print, add closing blanks around back matter
    if is_print and back_matter:
        # wrap back matter with blanks (handled above by add_blank calls if needed)
        pass

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
    css_ids = {'main.css': 'style001.css'}
    for css in css_files:
        cid = css_ids.get(css, css.replace('.', '_').replace('-', '_'))
        if css in styles_needed:
            manifest_items.append({'id': cid, 'href': f'styles/{css}',
                                   'media_type': 'text/css', 'properties': None})

    # ── Font manifest entries ─────────────────────────────────────────────────
    font_mime = {'ttf': 'application/vnd.ms-opentype', 'otf': 'application/vnd.ms-opentype'}
    for i, font in enumerate(fonts_needed):
        ext = font.rsplit('.', 1)[-1].lower()
        manifest_items.append({'id': f'font{i}', 'href': f'fonts/{font}',
                               'media_type': font_mime.get(ext, 'application/octet-stream'),
                               'properties': None})

    # ── Image manifest entries ────────────────────────────────────────────────
    img_mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif'}
    for i, img in enumerate(images_needed):
        ext  = img.rsplit('.', 1)[-1].lower()
        mime = img_mime.get(ext, 'image/jpeg')
        props = 'cover-image' if (not is_print and cover_img and img == cover_img) else None
        iid   = 'cover' if (not is_print and img == cover_img) else f'img{i}'
        manifest_items.append({'id': iid, 'href': f'images/{img}',
                               'media_type': mime, 'properties': props})

    # ── content.opf ──────────────────────────────────────────────────────────
    opf = _build_opf(book_id, title, author, language, now, manifest_items, spine_items, is_print)
    files_to_write['content.opf'] = opf

    # ── Write EPUB zip ────────────────────────────────────────────────────────
    epub_path = os.path.join(BUILDS_DIR, f"{project_id}_{profile}.epub")
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
        # CSS files
        for css, src_path in styles_needed.items():
            with open(src_path, 'rb') as f:
                zf.writestr(f'OEBPS/styles/{css}', f.read())
        # Font files
        for font, src_path in fonts_needed.items():
            with open(src_path, 'rb') as f:
                zf.writestr(f'OEBPS/fonts/{font}', f.read())
        # Images
        for img, src_path in images_needed.items():
            with open(src_path, 'rb') as f:
                zf.writestr(f'OEBPS/images/{img}', f.read())

    return epub_path


# ── OPF / container builders ──────────────────────────────────────────────────

def _build_opf(book_id, title, author, language, modified, manifest_items, spine_items, is_print):
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
    return """<?xml version='1.0' encoding='UTF-8'?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

def _esc(s):
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')