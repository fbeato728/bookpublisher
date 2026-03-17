import re
import zipfile
from typing import Dict, List
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"

NS = {
    "w": W_NS,
    "xhtml": XHTML_NS,
    "epub": EPUB_NS,
}


# ── Public entry points────────────────────────────────────────────────────────

def detect_footnotes(docx_path: str) -> dict:
    """
    Extract footnotes from a DOCX file and return a footnotes_map dict
    ready to be saved as footnotes_map.json.
    Does not touch full.xhtml.
    """
    result = extract_docx_footnotes_robust(docx_path)

    if not result['detected']:
        return {
            'detected': False,
            'total':    0,
            'footnotes': []
        }

    footnotes     = result['footnotes']
    paragraphs    = result['paragraphs']
    id_to_display = result['id_to_display']

    fn_list = []
    for fn_id, display_num in sorted(id_to_display.items(), key=lambda x: x[1]):
        fn = footnotes.get(fn_id, {})
        para_index   = None
        para_preview = ''
        for p in paragraphs:
            for ref in p.get('references', []):
                if ref['id'] == fn_id:
                    para_index   = p['paragraph_index']
                    para_preview = p['plain_text'][:80]
                    break
            if para_index is not None:
                break

        fn_list.append({
            'id':                fn_id,
            'display_num':       display_num,
            'content':           fn.get('content_text', ''),
            'paragraph_index':   para_index,
            'paragraph_preview': para_preview,
            'injected':          False,
            'status':            'pending'
        })

    return {
            'detected':      True,
            'total':         len(fn_list),
            'footnotes':     fn_list,
            'paragraphs':    paragraphs,
            'id_to_display': id_to_display,
        }


def match_footnotes(paragraphs: list, xhtml_path: str) -> list:
    with open(xhtml_path, 'rb') as f:
        root = etree.parse(f).getroot()
    xhtml_paragraphs = extract_xhtml_paragraphs(root)
    # print(f'[matcher] xhtml paragraphs parsed: {len(xhtml_paragraphs)}', flush=True)
    # print(f'[matcher] docx paragraphs with references: {sum(1 for p in paragraphs if p["references"])}', flush=True)
    # for p in paragraphs:
    #     if p["references"]:
    #         print(f'[matcher] docx ref para: {p["text_with_markers"][:80]}', flush=True)
    # print('hello',paragraphs['footnote_matches'])
    return match_docx_paragraphs_to_xhtml(paragraphs, xhtml_paragraphs)


# ── Notebook functions for docx footnotes detection (verbatim) ─────────────────────────────────────────────

def extract_docx_footnotes_robust(docx_path: str) -> Dict:
    empty = {
        'detected':      False,
        'footnotes':     {},
        'paragraphs':    [],
        'id_to_display': {},
    }

    try:
        with zipfile.ZipFile(docx_path) as z:
            with z.open('word/document.xml') as f:
                doc_tree = etree.parse(f)
            try:
                with z.open('word/footnotes.xml') as f:
                    footnotes_tree = etree.parse(f)
            except KeyError:
                return empty
    except Exception as e:
        print(f'Error reading DOCX: {e}')
        return empty

    footnotes = _extract_footnote_bodies(footnotes_tree)
    if not footnotes:
        return empty

    paragraphs    = _extract_document_paragraphs(doc_tree)
    id_to_display = _build_display_order_from_references(paragraphs)

    for p in paragraphs:
        for ref in p['references']:
            ref['display_number'] = id_to_display.get(ref['id'])

    for fn_id, fn in footnotes.items():
        fn['display_number'] = id_to_display.get(fn_id)

    return {
        'detected':      bool(id_to_display),
        'footnotes':     footnotes,
        'paragraphs':    paragraphs,
        'id_to_display': id_to_display,
    }


def _extract_footnote_bodies(footnotes_tree) -> Dict[str, Dict]:
    result = {}
    footnote_nodes = footnotes_tree.xpath('//w:footnote', namespaces=NS)

    for fn in footnote_nodes:
        fn_id   = fn.get(f'{{{W_NS}}}id')
        fn_type = fn.get(f'{{{W_NS}}}type')

        if fn_type in {'separator', 'continuationSeparator', 'continuationNotice'}:
            continue
        if fn_id in {'-1', '0', '1'}:
            continue

        paragraph_texts = []
        for p in fn.xpath('./w:p', namespaces=NS):
            text = _collect_visible_text_from_word_container(p).strip()
            if text:
                paragraph_texts.append(text)

        content_text = '\n'.join(paragraph_texts).strip()
        if fn_id and content_text:
            result[fn_id] = {
                'id':           fn_id,
                'content_text': content_text,
                'paragraphs':   paragraph_texts,
            }

    return result


def _extract_document_paragraphs(doc_tree) -> List[Dict]:
    paragraphs_out  = []
    paragraph_nodes = doc_tree.xpath('//w:body//w:p', namespaces=NS)

    for para_idx, para in enumerate(paragraph_nodes):
        plain_parts  = []
        marked_parts = []
        refs         = []

        for node in para.iter():
            tag = node.tag

            if tag == f'{{{W_NS}}}t':
                text = node.text or ''
                if text:
                    plain_parts.append(text)
                    marked_parts.append(text)

            elif tag == f'{{{W_NS}}}tab':
                plain_parts.append('\t')
                marked_parts.append('\t')

            elif tag in {f'{{{W_NS}}}br', f'{{{W_NS}}}cr'}:
                plain_parts.append('\n')
                marked_parts.append('\n')

            elif tag == f'{{{W_NS}}}noBreakHyphen':
                plain_parts.append('-')
                marked_parts.append('-')

            elif tag == f'{{{W_NS}}}softHyphen':
                plain_parts.append('\u00AD')
                marked_parts.append('\u00AD')

            elif tag == f'{{{W_NS}}}footnoteReference':
                fn_id  = node.get(f'{{{W_NS}}}id')
                marker = f'[[FN:{fn_id}]]'
                offset = len(''.join(plain_parts))
                refs.append({
                    'id':     fn_id,
                    'offset': offset,
                    'marker': marker,
                })
                marked_parts.append(marker)

        plain_text  = ''.join(plain_parts)
        marked_text = ''.join(marked_parts)

        if plain_text.strip() or refs:
            paragraphs_out.append({
                'paragraph_index':   para_idx,
                'plain_text':        plain_text,
                'text_with_markers': marked_text,
                'references':        refs,
            })

    return paragraphs_out


def _collect_visible_text_from_word_container(elem) -> str:
    parts = []
    for node in elem.iter():
        tag = node.tag
        if tag == f'{{{W_NS}}}t':
            if node.text:
                parts.append(node.text)
        elif tag == f'{{{W_NS}}}tab':
            parts.append('\t')
        elif tag in {f'{{{W_NS}}}br', f'{{{W_NS}}}cr'}:
            parts.append('\n')
        elif tag == f'{{{W_NS}}}noBreakHyphen':
            parts.append('-')
        elif tag == f'{{{W_NS}}}softHyphen':
            parts.append('\u00AD')
    return ''.join(parts)


def _build_display_order_from_references(paragraphs: List[Dict]) -> Dict[str, int]:
    seen     = []
    seen_set = set()
    for para in paragraphs:
        for ref in para['references']:
            if ref['id'] and ref['id'] not in seen_set:
                seen.append(ref['id'])
                seen_set.add(ref['id'])
    return {fn_id: i + 1 for i, fn_id in enumerate(seen)}

# ── Notebook functions for xhtml-docx matching (verbatim) ─────────────────────────────────────────────

def extract_xhtml_paragraphs(root) -> List[Dict]:
    xpath_expr = (
        "//xhtml:p | //xhtml:li | //xhtml:blockquote | "
        "//xhtml:dd | //xhtml:dt | "
        "//xhtml:h1 | //xhtml:h2 | //xhtml:h3 | //xhtml:h4 | //xhtml:h5 | //xhtml:h6"
    )

    nodes = root.xpath(xpath_expr, namespaces=NS)

    out = []
    for i, node in enumerate(nodes):
        text = "".join(node.itertext())
        out.append({
            "xhtml_index": i,
            "tag": etree.QName(node).localname,
            "text": text,
            "node": node,
        })

    return out


def _normalize_for_matching(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"\[\[FN:.*?\]\]", "", text)

    replacements = {
        "\u00A0": " ",
        "\u00AD": "",
        "\u2011": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201C": '"',
        "\u201D": '"',
        "\u2026": "...",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)

    return text.strip().lower()


def _significant_text(text: str, min_chars: int = 12) -> bool:
    return len(_normalize_for_matching(text)) >= min_chars


def _score_paragraph_match(docx_text: str, xhtml_text: str) -> float:
    a = _normalize_for_matching(docx_text)
    b = _normalize_for_matching(xhtml_text)

    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    if a in b or b in a:
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        return 0.92 * (shorter / longer)

    a_tokens = set(a.split())
    b_tokens = set(b.split())

    if not a_tokens or not b_tokens:
        return 0.0

    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    jaccard = inter / union if union else 0.0

    prefix = 0.0
    if a[:40] and b[:40] and a[:40] == b[:40]:
        prefix += 0.08
    if a[-40:] and b[-40:] and a[-40:] == b[-40:]:
        prefix += 0.08

    return min(0.95, jaccard + prefix)


def match_docx_paragraphs_to_xhtml(
    docx_paragraphs: List[Dict],
    xhtml_paragraphs: List[Dict],
    min_score: float = 0.55,
    lookahead_window: int = 400,
) -> List[Dict]:
    matches = []
    x_start = 0

    for d in docx_paragraphs:
        d_text = d["text_with_markers"]

        if not d["references"]:
            continue
        if not _significant_text(d_text):
            continue

        best = None
        best_score = -1.0

        for xi in range(x_start, min(len(xhtml_paragraphs), x_start + lookahead_window)):
            x = xhtml_paragraphs[xi]
            score = _score_paragraph_match(d_text, x["text"])
            if score > best_score:
                best_score = score
                best = x

        if best and best_score >= min_score:
            matches.append({
                "docx_paragraph_index": d["paragraph_index"],
                "xhtml_index": best["xhtml_index"],
                "score": round(best_score, 4),
                "docx_text_with_markers": d["text_with_markers"],
                "xhtml_text": best["text"],
                "references": d["references"],
            })
            x_start = best["xhtml_index"] + 1

    return matches

# ── Injection helpers (verbatim from notebook) ────────────────────────────────

def inject_marker_based_sup_into_plain_paragraph(node, docx_text_with_markers, fn_id, display_num):
    marker = f"[[FN:{fn_id}]]"

    if marker not in docx_text_with_markers:
        return False

    before_text, after_text = docx_text_with_markers.split(marker, 1)
    target_offset = len(re.sub(r"\[\[FN:.*?\]\]", "", before_text))

    def make_marker():
        marker = etree.Element(f"{{{XHTML_NS}}}span")
        marker.set("class", "fn-marker")
        marker.set("data-fn", str(fn_id))
        marker.set("data-display", str(display_num))
        marker.text = ""  # forces explicit closing tag
        return marker

    def collect_slots(elem):
        slots = []

        def walk(e):
            if e.text:
                slots.append(("text", e, e.text))
            for child in e:
                walk(child)
                if child.tail:
                    slots.append(("tail", child, child.tail))

        walk(elem)
        return slots

    slots = collect_slots(node)
    pos = 0

    for kind, owner, txt in slots:
        next_pos = pos + len(txt)

        if target_offset <= next_pos:
            local = target_offset - pos
            marker = make_marker()

            if kind == "text":
                elem = owner
                before = txt[:local]
                after = txt[local:]
                elem.text = before
                if len(elem):
                    elem.insert(0, marker)
                else:
                    elem.append(marker)
                marker.tail = after
                return True

            else:  # tail
                child = owner
                parent = child.getparent()
                idx = parent.index(child)
                before = txt[:local]
                after = txt[local:]
                child.tail = before
                parent.insert(idx + 1, marker)
                marker.tail = after
                return True

        pos = next_pos

    if target_offset == pos:
        marker = make_marker()
        node.append(marker)
        return True

    return False


def inject_references_marker_based_plain(node, docx_text_with_markers, references, id_to_display):
    refs_sorted = sorted(references, key=lambda r: r["offset"], reverse=True)
    ok = True
    for ref in refs_sorted:
        fn_id       = ref["id"]
        display_num = id_to_display.get(fn_id, "?")
        inserted    = inject_marker_based_sup_into_plain_paragraph(
            node, docx_text_with_markers, fn_id, display_num,
        )
        if not inserted:
            ok = False
    return ok


# ── Public injection entry point ──────────────────────────────────────────────

def inject_footnotes(fn_map: dict, xhtml_in: str, xhtml_out: str) -> int:
    """
    Inject footnote span markers into xhtml_in, write result to xhtml_out.
    Returns count of successfully injected paragraph matches.
    Does not modify fn_map.
    """
    parser = etree.XMLParser(recover=True, encoding='utf-8')
    with open(xhtml_in, 'rb') as f:
        tree = etree.parse(f, parser)
    root = tree.getroot()

    xhtml_paras   = extract_xhtml_paragraphs(root)
    id_to_display = fn_map.get('id_to_display', {})
    matches       = fn_map.get('paragraph_matches', [])

    matched_count = 0
    for m in matches:
        xi   = m['xhtml_index']
        if xi >= len(xhtml_paras):
            continue
        node = xhtml_paras[xi]['node']
        ok   = inject_references_marker_based_plain(
            node,
            m['docx_text_with_markers'],
            m['references'],
            id_to_display,
        )
        if ok:
            matched_count += 1

    tree.write(
        xhtml_out,
        encoding='utf-8',
        xml_declaration=True,
        pretty_print=True,
    )

    return matched_count