import os
import re
import json
from flask import Blueprint, request, jsonify

footnotes_bp = Blueprint('footnotes', __name__)

from config import PROJECTS_DIR
from routes.footnote_detector import detect_footnotes, match_footnotes, inject_footnotes


def _footnotes_path(project_id):
    return os.path.join(PROJECTS_DIR, project_id, 'footnotes.json')


def _parse_footnote_file(text):
    """Parse footnote file with format: (N) text"""
    footnotes = {}
    pattern = re.compile(r'^\((\d+)\)\s+(.+?)(?=^\(\d+\)|\Z)', re.MULTILINE | re.DOTALL)
    for m in pattern.finditer(text):
        num  = int(m.group(1))
        note = m.group(2).strip()
        footnotes[num] = note
    return footnotes


@footnotes_bp.route('/api/projects/<project_id>/footnotes', methods=['POST'])
def upload_footnotes(project_id):
    """Upload and parse a footnote text file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    text = f.read().decode('utf-8')
    footnotes = _parse_footnote_file(text)
    if not footnotes:
        return jsonify({'error': 'No footnotes found — expected format: (1) text'}), 400
    with open(_footnotes_path(project_id), 'w', encoding='utf-8') as fp:
        json.dump(footnotes, fp, ensure_ascii=False, indent=2)
    items = [{'n': k, 'text': v} for k, v in sorted(footnotes.items(), key=lambda x: x[0])]
    return jsonify({'ok': True, 'count': len(footnotes), 'footnotes': items})


@footnotes_bp.route('/api/projects/<project_id>/footnotes', methods=['GET'])
def get_footnotes(project_id):
    """Return parsed footnotes as a sorted list."""
    path = _footnotes_path(project_id)
    if not os.path.exists(path):
        return jsonify({'footnotes': [], 'count': 0})
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    items = [{'n': int(k), 'text': v} for k, v in data.items()]
    items.sort(key=lambda x: x['n'])
    return jsonify({'footnotes': items, 'count': len(items)})


@footnotes_bp.route('/api/projects/<project_id>/footnotes', methods=['DELETE'])
def delete_footnotes(project_id):
    """Remove the footnote file for this project."""
    path = _footnotes_path(project_id)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'ok': True})


@footnotes_bp.route('/api/projects/<project_id>/footnotes/detect', methods=['POST'])
def detect_project_footnotes(project_id):
    """Run footnote detection on the original DOCX, write footnotes_map.json."""
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    meta_path   = os.path.join(project_dir, 'meta.json')

    if not os.path.exists(meta_path):
        return jsonify({'error': 'Project not found'}), 404

    with open(meta_path, encoding='utf-8') as f:
        meta = json.load(f)

    original_file = meta.get('original_file', '')
    if not original_file:
        return jsonify({'error': 'No original file recorded in meta.json'}), 400

    docx_path  = os.path.join(project_dir, 'original', original_file)
    xhtml_path = os.path.join(project_dir, 'xhtml', 'full.xhtml')

    if not os.path.exists(docx_path):
        return jsonify({'error': f'Original file not found: {original_file}'}), 404

    if not os.path.exists(xhtml_path):
        return jsonify({'error': 'full.xhtml not found'}), 404

    try:
        fn_map        = detect_footnotes(docx_path)
        paragraphs    = fn_map.pop('paragraphs', [])
        id_to_display = fn_map.pop('id_to_display', {})
        matches       = match_footnotes(paragraphs, xhtml_path)
        print(f'[debug] first match: {matches[0] if matches else "empty"}', flush=True)
       
        # Enrich footnote entries with matched xhtml position
        for m in matches:
            for ref in m['references']:
                for fn in fn_map['footnotes']:
                    if fn['id'] == ref['id']:
                        fn['matched_xhtml_index'] = m['xhtml_index']
                        fn['matched_score']        = m['score']

        # Strip only xhtml_text — keep docx_text_with_markers for injection
        for m in matches:
            m.pop('xhtml_text', None)

        fn_map['id_to_display']            = id_to_display
        fn_map['paragraph_matches']        = matches
        fn_map['total_paragraph_matches']  = len(matches)
        fn_map['total_footnote_matches']   = sum(1 for fn in fn_map['footnotes'] if 'matched_xhtml_index' in fn)

    except Exception as e:
        print(f'[debug] error: {str(e)}', flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Detection failed: {str(e)}'}), 500

    fn_map_path = os.path.join(project_dir, 'footnotes_map.json')
    with open(fn_map_path, 'w', encoding='utf-8') as f:
        json.dump(fn_map, f, ensure_ascii=False, indent=2)

    print(f'[detect] footnotes: {fn_map["total"]} — paragraph matches: {fn_map["total_paragraph_matches"]} — footnote matches: {fn_map["total_footnote_matches"]}', flush=True)
    
    # print('**************************************************')
    # print(fn_map)
    # print('**************************************************')
    
    
    return jsonify({
        'ok':                    True,
        'detected':              fn_map['detected'],
        'total':                 fn_map['total'],
        'total_paragraph_matches': fn_map['total_paragraph_matches'],
        'total_footnote_matches':  fn_map['total_footnote_matches'],
    })

@footnotes_bp.route('/api/projects/<project_id>/footnotes/map', methods=['GET'])
def get_footnotes_map(project_id):
    """Return footnotes_map.json for a project."""
    fn_map_path = os.path.join(PROJECTS_DIR, project_id, 'footnotes_map.json')
    if not os.path.exists(fn_map_path):
        return jsonify({'error': 'No footnotes map found'}), 404
    with open(fn_map_path, encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)


@footnotes_bp.route('/api/projects/<project_id>/footnotes/map', methods=['DELETE'])
def delete_footnotes_map(project_id):
    """Delete footnotes_map.json and restore full_original.xhtml if injection was done."""
    project_dir   = os.path.join(PROJECTS_DIR, project_id)
    fn_map_path   = os.path.join(project_dir, 'footnotes_map.json')
    xhtml_path    = os.path.join(project_dir, 'xhtml', 'full.xhtml')
    original_path = os.path.join(project_dir, 'xhtml', 'full_original.xhtml')

    if os.path.exists(original_path):
        if os.path.exists(xhtml_path):
            os.remove(xhtml_path)
        os.rename(original_path, xhtml_path)

    if os.path.exists(fn_map_path):
        os.remove(fn_map_path)

    return jsonify({'ok': True})

@footnotes_bp.route('/api/projects/<project_id>/footnotes/<int:display_num>', methods=['PATCH'])
def update_footnote(project_id, display_num):
    """Update content of a single footnote entry in footnotes_map.json."""
    fn_map_path = os.path.join(PROJECTS_DIR, project_id, 'footnotes_map.json')
    if not os.path.exists(fn_map_path):
        return jsonify({'error': 'No footnotes map found'}), 404
    with open(fn_map_path, encoding='utf-8') as f:
        fn_map = json.load(f)
    data = request.json or {}
    footnote = next((fn for fn in fn_map.get('footnotes', []) if fn.get('display_num') == display_num), None)
    if not footnote:
        return jsonify({'error': f'Footnote #{display_num} not found'}), 404
    if 'content' in data:
        footnote['content'] = data['content']
        footnote['status']  = 'edited'
    with open(fn_map_path, 'w', encoding='utf-8') as f:
        json.dump(fn_map, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True, 'footnote': footnote})


@footnotes_bp.route('/api/projects/<project_id>/footnotes/<int:display_num>', methods=['DELETE'])
def delete_footnote(project_id, display_num):
    """Remove a footnote: delete span from full.xhtml, renumber remaining, update data-display."""
    from lxml import etree
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    fn_map_path = os.path.join(project_dir, 'footnotes_map.json')
    xhtml_path  = os.path.join(project_dir, 'xhtml', 'full.xhtml')

    if not os.path.exists(fn_map_path):
        return jsonify({'error': 'No footnotes map found'}), 404

    with open(fn_map_path, encoding='utf-8') as f:
        fn_map = json.load(f)

    footnote = next((fn for fn in fn_map.get('footnotes', []) if fn.get('display_num') == display_num), None)
    if not footnote:
        return jsonify({'error': f'Footnote #{display_num} not found'}), 404

    fn_id = footnote['id']

    # Remove span from full.xhtml and update data-display on remaining spans
    if os.path.exists(xhtml_path):
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        with open(xhtml_path, 'rb') as f:
            tree = etree.parse(f, parser)
        root = tree.getroot()
        XHTML_NS = 'http://www.w3.org/1999/xhtml'

        # Remove the deleted span
        for span in root.iter(f'{{{XHTML_NS}}}span'):
            if span.get('data-fn') == str(fn_id):
                parent = span.getparent()
                if parent is not None:
                    # Merge tail text back into previous sibling or parent
                    tail = span.tail or ''
                    idx  = list(parent).index(span)
                    if idx > 0:
                        prev = list(parent)[idx - 1]
                        prev.tail = (prev.tail or '') + tail
                    else:
                        parent.text = (parent.text or '') + tail
                    parent.remove(span)
                break

        # Remove from JSON
        fn_map['footnotes'] = [fn for fn in fn_map['footnotes'] if fn.get('display_num') != display_num]
        fn_map['paragraph_matches'] = [m for m in fn_map.get('paragraph_matches', [])
                                        if not any(r['id'] == fn_id for r in m.get('references', []))]

        # Renumber remaining footnotes
        for i, fn in enumerate(fn_map['footnotes'], start=1):
            fn['display_num'] = i

        # Update data-display on remaining spans
        id_to_new_display = {fn['id']: fn['display_num'] for fn in fn_map['footnotes']}
        for span in root.iter(f'{{{XHTML_NS}}}span'):
            if span.get('class') == 'fn-marker':
                sid = span.get('data-fn')
                if sid in id_to_new_display:
                    span.set('data-display', str(id_to_new_display[sid]))

        tree.write(xhtml_path, encoding='utf-8', xml_declaration=True, pretty_print=True)

    fn_map['total'] = len(fn_map['footnotes'])
    fn_map['total_footnote_matches'] = sum(1 for fn in fn_map['footnotes'] if 'matched_xhtml_index' in fn)

    with open(fn_map_path, 'w', encoding='utf-8') as f:
        json.dump(fn_map, f, ensure_ascii=False, indent=2)

    return jsonify({'ok': True, 'footnotes': fn_map['footnotes']})

@footnotes_bp.route('/api/projects/<project_id>/footnotes/inject', methods=['POST'])
def inject_project_footnotes(project_id):
    """Inject footnote markers into full.xhtml, backup original as full_original.xhtml."""
    project_dir   = os.path.join(PROJECTS_DIR, project_id)
    fn_map_path   = os.path.join(project_dir, 'footnotes_map.json')
    xhtml_path    = os.path.join(project_dir, 'xhtml', 'full.xhtml')
    original_path = os.path.join(project_dir, 'xhtml', 'full_original.xhtml')

    if not os.path.exists(fn_map_path):
        return jsonify({'error': 'No footnotes map found — run detection first'}), 404

    with open(fn_map_path, encoding='utf-8') as f:
        fn_map = json.load(f)

    if fn_map.get('footnotes_injected'):
        return jsonify({'error': 'Footnotes already injected — reset first to re-inject'}), 400

    if not os.path.exists(xhtml_path):
        return jsonify({'error': 'full.xhtml not found'}), 404

    try:
        os.rename(xhtml_path, original_path)
        injected_count = inject_footnotes(fn_map, original_path, xhtml_path)
        fn_map['footnotes_injected'] = True
        for fn in fn_map.get('footnotes', []):
            fn['injected'] = True
        with open(fn_map_path, 'w', encoding='utf-8') as f:
            json.dump(fn_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        if os.path.exists(original_path) and not os.path.exists(xhtml_path):
            os.rename(original_path, xhtml_path)
        print(f'[inject] error: {str(e)}', flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Injection failed: {str(e)}'}), 500

    print(f'[inject] injected_count: {injected_count}', flush=True)
    return jsonify({'ok': True, 'injected_count': injected_count})

def _inject_span_at_offset(root, xhtml_index, char_offset, fn_id, display_num):
    """Insert a fn-marker span at exact char_offset within the paragraph at xhtml_index."""
    from lxml import etree
    XHTML_NS = 'http://www.w3.org/1999/xhtml'
    NS = {'xhtml': XHTML_NS}

    xpath_expr = (
        "//xhtml:p | //xhtml:li | //xhtml:blockquote | "
        "//xhtml:dd | //xhtml:dt | "
        "//xhtml:h1 | //xhtml:h2 | //xhtml:h3 | //xhtml:h4 | //xhtml:h5 | //xhtml:h6"
    )
    nodes = root.xpath(xpath_expr, namespaces=NS)
    if xhtml_index >= len(nodes):
        return False

    node = nodes[xhtml_index]

    def make_span():
        span = etree.Element(f'{{{XHTML_NS}}}span')
        span.set('class', 'fn-marker')
        span.set('data-fn', str(fn_id))
        span.set('data-display', str(display_num))
        span.text = ""  # forces explicit closing tag
        return span

    def collect_slots(elem):
        slots = []
        def walk(e):
            if e.text:
                slots.append(('text', e, e.text))
            for child in e:
                walk(child)
                if child.tail:
                    slots.append(('tail', child, child.tail))
        walk(elem)
        return slots

    slots = collect_slots(node)
    pos   = 0

    for kind, owner, txt in slots:
        next_pos = pos + len(txt)
        if char_offset <= next_pos:
            local = char_offset - pos
            span  = make_span()
            if kind == 'text':
                elem         = owner
                before       = txt[:local]
                after        = txt[local:]
                elem.text    = before
                if len(elem):
                    elem.insert(0, span)
                else:
                    elem.append(span)
                span.tail = after
            else:
                child  = owner
                parent = child.getparent()
                idx    = list(parent).index(child)
                before = txt[:local]
                after  = txt[local:]
                child.tail = before
                parent.insert(idx + 1, span)
                span.tail = after
            return True
        pos = next_pos

    # Append at end if offset is at or beyond end
    node.append(make_span())
    return True


@footnotes_bp.route('/api/projects/<project_id>/footnotes/add', methods=['POST'])
def add_footnote(project_id):
    """Add a new footnote at a precise position in full.xhtml."""
    from lxml import etree
    project_dir = os.path.join(PROJECTS_DIR, project_id)
    fn_map_path = os.path.join(project_dir, 'footnotes_map.json')
    xhtml_path  = os.path.join(project_dir, 'xhtml', 'full.xhtml')

    if not os.path.exists(fn_map_path):
        return jsonify({'error': 'No footnotes map found'}), 404
    if not os.path.exists(xhtml_path):
        return jsonify({'error': 'full.xhtml not found'}), 404

    data             = request.json or {}
    xhtml_index      = data.get('xhtml_index')
    char_offset      = data.get('char_offset')
    content          = data.get('content', '').strip()
    insert_after_num = data.get('insert_after_num', 0)

    if xhtml_index is None or char_offset is None or not content:
        return jsonify({'error': 'xhtml_index, char_offset and content are required'}), 400

    with open(fn_map_path, encoding='utf-8') as f:
        fn_map = json.load(f)

    # Generate new manual id
    existing_ids = {fn['id'] for fn in fn_map.get('footnotes', [])}
    manual_n = 1
    while f'm{manual_n}' in existing_ids:
        manual_n += 1
    fn_id = f'm{manual_n}'

    # Insert position is after insert_after_num
    insert_pos = insert_after_num  # 0-based index into list

    # Temporarily assign display_num — will renumber after insertion
    new_display = insert_after_num + 1

    # Parse and modify XHTML
    parser = etree.XMLParser(recover=True, encoding='utf-8')
    with open(xhtml_path, 'rb') as f:
        tree = etree.parse(f, parser)
    root = tree.getroot()

    ok = _inject_span_at_offset(root, xhtml_index, char_offset, fn_id, new_display)
    if not ok:
        return jsonify({'error': 'Could not find paragraph at given xhtml_index'}), 400

    # Insert new footnote entry at correct position
    new_fn = {
        'id':                fn_id,
        'display_num':       new_display,
        'content':           content,
        'paragraph_index':   None,
        'paragraph_preview': '',
        'matched_xhtml_index': xhtml_index,
        'matched_score':     1.0,
        'injected':          True,
        'status':            'pending',
    }
    fn_map['footnotes'].insert(insert_pos, new_fn)

    # Renumber all footnotes
    for i, fn in enumerate(fn_map['footnotes'], start=1):
        fn['display_num'] = i

    # Update data-display on all spans
    XHTML_NS = 'http://www.w3.org/1999/xhtml'
    id_to_display = {fn['id']: fn['display_num'] for fn in fn_map['footnotes']}
    for span in root.iter(f'{{{XHTML_NS}}}span'):
        if span.get('class') == 'fn-marker':
            sid = span.get('data-fn')
            if sid in id_to_display:
                span.set('data-display', str(id_to_display[sid]))

    tree.write(xhtml_path, encoding='utf-8', xml_declaration=True, pretty_print=True)

    fn_map['total'] = len(fn_map['footnotes'])
    fn_map['total_footnote_matches'] = sum(1 for fn in fn_map['footnotes'] if 'matched_xhtml_index' in fn)

    with open(fn_map_path, 'w', encoding='utf-8') as f:
        json.dump(fn_map, f, ensure_ascii=False, indent=2)

    return jsonify({'ok': True, 'footnotes': fn_map['footnotes']})