import os
import shutil
import json
import re
import zipfile
from flask import Blueprint, request, jsonify
from lxml import etree

epub_bp = Blueprint('epub', __name__)

PROJECTS_DIR = '/srv/bookpublisher/projects'

NAMESPACES = {
    'opf':      'http://www.idpf.org/2007/opf',
    'dc':       'http://purl.org/dc/elements/1.1/',
    'container':'urn:oasis:names:tc:opendocument:xmlns:container',
    'xhtml':    'http://www.w3.org/1999/xhtml',
}

# Files that are structural/front/back matter — not chapters
KNOWN_FRONT = {'titlepage', 'credits_1', 'credits', 'title_only', 'titlePageContent', 'taula', 'ded', 'dedication', 'prologue'}
KNOWN_BACK  = {'biblioThanks', 'bibliography', 'epilogue', 'lesDonesFamilia', 'thanks', 'nav'}
BLANK_RE    = re.compile(r'^blank', re.IGNORECASE)


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text[:60]


@epub_bp.route('/api/projects/import-epub', methods=['POST'])
def import_epub():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file       = request.files['file']
    title      = request.form.get('title', '').strip()
    author     = request.form.get('author', '').strip()
    project_id = request.form.get('project_id', '').strip()

    if not file.filename.endswith('.epub'):
        return jsonify({'error': 'Only .epub files accepted here'}), 400

    if not title:
        return jsonify({'error': 'Book title is required'}), 400

    project_id = re.sub(r'[^\w-]', '', project_id).lower()
    if not project_id:
        project_id = slugify(title) or 'epub-import'

    project_dir = os.path.join(PROJECTS_DIR, project_id)
    if os.path.exists(project_dir):
        return jsonify({'error': f'Project "{project_id}" already exists'}), 400

    for subdir in ['original', 'xhtml', 'images', 'styles', 'fonts', 'epub', 'print', 'pdf']:
        os.makedirs(os.path.join(project_dir, subdir), exist_ok=True)

    # Copy global CSS files into project so they can be edited per-project
    styles_dir = os.path.join(project_dir, 'styles')
    for css_file in ['digital.css', 'print.css', 'digital-credits.css', 'print-credits.css',
                       'book_big_title.css', 'taula.css']:
        global_css = os.path.join(GLOBAL_DIR, 'styles', css_file)
        project_css = os.path.join(styles_dir, css_file)
        if os.path.exists(global_css) and not os.path.exists(project_css):
            shutil.copy2(global_css, project_css)

    original_path = os.path.join(project_dir, 'original', file.filename)
    file.save(original_path)

    try:
        chapters, all_files = _extract_epub(original_path, project_dir)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to parse EPUB: {str(e)}'}), 500

    meta = {
        'id':            project_id,
        'title':         title,
        'author':        author,
        'original_file': file.filename,
        'source':        'epub',
        'status':        'split',
        'chapters':      chapters,
        'all_xhtml':     all_files,   # full spine for build config
    }
    with open(os.path.join(project_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"Imported EPUB as project: {project_id} — {len(chapters)} chapters, {len(all_files)} total xhtml files")
    return jsonify(meta), 201


def _classify(name):
    """Classify a file by its base name (without extension)."""
    if BLANK_RE.match(name):
        return 'blank'
    if name in KNOWN_FRONT:
        return 'front'
    if name in KNOWN_BACK:
        return 'back'
    if name == 'nav':
        return 'nav'
    # numbered files are chapters/parts/records
    return 'chapter'


def _extract_epub(epub_path, project_dir):
    xhtml_dir  = os.path.join(project_dir, 'xhtml')
    styles_dir = os.path.join(project_dir, 'styles')
    fonts_dir  = os.path.join(project_dir, 'fonts')
    images_dir = os.path.join(project_dir, 'images')

    with zipfile.ZipFile(epub_path, 'r') as z:
        names = z.namelist()

        # 1. Find content.opf
        container_xml = z.read('META-INF/container.xml')
        cont_tree     = etree.fromstring(container_xml)
        rootfile_el   = cont_tree.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
        if rootfile_el is None:
            raise ValueError('Could not find rootfile in container.xml')
        opf_path = rootfile_el.get('full-path')
        opf_dir  = os.path.dirname(opf_path)

        # 2. Parse content.opf
        opf_data = z.read(opf_path)
        opf_tree = etree.fromstring(opf_data)

        manifest = {}
        for item in opf_tree.findall('.//{http://www.idpf.org/2007/opf}item'):
            manifest[item.get('id')] = {
                'href':       item.get('href'),
                'media_type': item.get('media-type', ''),
                'properties': item.get('properties', ''),
            }

        spine_idrefs = [
            itemref.get('idref')
            for itemref in opf_tree.findall('.//{http://www.idpf.org/2007/opf}itemref')
        ]

        # 3. Extract XHTML files — keeping original filenames
        chapters   = []   # chapter-type files for the editor
        all_files  = []   # everything in spine order for build config

        for idref in spine_idrefs:
            if idref not in manifest:
                continue
            item = manifest[idref]
            href = item['href']

            # Resolve path inside zip
            epub_file_path = os.path.join(opf_dir, href).lstrip('/')
            if epub_file_path not in names:
                epub_file_path = href
            if epub_file_path not in names:
                print(f"  Warning: {href} not found in zip")
                continue

            try:
                content = z.read(epub_file_path).decode('utf-8')
            except Exception as e:
                print(f"  Warning: could not read {epub_file_path}: {e}")
                continue

            # Preserve the original filename exactly
            filename = os.path.basename(href)
            base     = os.path.splitext(filename)[0]
            kind     = _classify(base)

            # Skip blanks and nav — we regenerate those at build time
            if kind in ('blank', 'nav'):
                continue

            content = _rewrite_paths(content)
            content = _strip_redundant_ns(content)

            out_path = os.path.join(xhtml_dir, filename)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Human-readable name
            display_name = _extract_display_name(content, base)

            entry = {
                'filename': filename,
                'name':     display_name,
                'type':     kind,
            }

            all_files.append(entry)
            if kind == 'chapter':
                chapters.append(entry)

            print(f"  Extracted [{kind}]: {filename}")

        # 4. Extract CSS
        for item in manifest.values():
            if 'css' in item['media_type']:
                _extract_asset(z, opf_dir, names, item['href'], styles_dir, 'CSS')

        # 5. Extract fonts
        for item in manifest.values():
            if any(x in item['media_type'] for x in ['font', 'otf', 'ttf', 'woff']):
                _extract_asset(z, opf_dir, names, item['href'], fonts_dir, 'Font', binary=True)

        # 6. Extract images
        for item in manifest.values():
            if 'image' in item['media_type']:
                _extract_asset(z, opf_dir, names, item['href'], images_dir, 'Image', binary=True)

    return chapters, all_files


def _extract_asset(z, opf_dir, names, href, dest_dir, label, binary=False):
    epub_path = os.path.join(opf_dir, href).lstrip('/')
    if epub_path not in names:
        epub_path = href
    if epub_path not in names:
        return
    try:
        data     = z.read(epub_path)
        out_name = os.path.basename(href)
        out_path = os.path.join(dest_dir, out_name)
        mode = 'wb' if binary else 'w'
        with open(out_path, mode) as f:
            f.write(data if binary else data.decode('utf-8'))
        print(f"  {label}: {out_name}")
    except Exception as e:
        print(f"  Warning: could not extract {label} {href}: {e}")


def _extract_display_name(content, fallback):
    try:
        doc     = etree.fromstring(content.encode('utf-8'))
        h1      = doc.find('.//{http://www.w3.org/1999/xhtml}h1')
        title_el = doc.find('.//{http://www.w3.org/1999/xhtml}title')
        if h1 is not None:
            text = ''.join(h1.itertext()).strip()
            if text:
                return text
        if title_el is not None and title_el.text:
            return title_el.text.strip()
    except Exception:
        pass
    return fallback


def _rewrite_paths(xhtml_content):
    xhtml_content = re.sub(
        r'href="(?:\.\.\/)*(?:styles?\/)?([^"]+\.css)"',
        r'href="../styles/\1"',
        xhtml_content
    )
    xhtml_content = re.sub(
        r'src="(?:\.\.\/)*(?:images?\/)?([^"]+\.(jpg|jpeg|png|gif|svg|webp))"',
        r'src="../images/\1"',
        xhtml_content,
        flags=re.IGNORECASE
    )
    return xhtml_content


_NS_ATTRS = re.compile(r'\s+xmlns(?::\w+)?="[^"]*"')

def _strip_redundant_ns(content):
    """Strip xmlns declarations from individual elements (keep only on <html>)."""
    lines = content.split('\n')
    result = []
    found_html = False
    for line in lines:
        if not found_html:
            if '<html' in line:
                found_html = True
            result.append(line)
        else:
            result.append(_NS_ATTRS.sub('', line))
    return '\n'.join(result)