import os
from docx import Document

XHTML_START = """<?xml version='1.0' encoding='UTF-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <link rel="stylesheet" href="../styles/main.css" type="text/css"/>
    <title>{title}</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  </head>
  <body>"""

XHTML_END = "\n</body>\n</html>"

def convert_runs(para):
    result = ''
    for r in para.runs:
        if not r.text:
            continue
        text = r.text
        if r.italic and r.bold:
            result += f"<i><b>{text}</b></i>"
        elif r.italic:
            result += f"<i>{text}</i>"
        elif r.bold:
            result += f"<b>{text}</b>"
        else:
            result += text
    return result

def clean_inline(text):
    text = text.replace('</i><i>', '')
    text = text.replace('<i>.</i>', '.')
    text = text.replace('&', '&amp;')
    return text

def convert_docx(docx_path, book_title="Untitled"):
    """
    Convert a DOCX to a single XHTML string.
    Headings are preserved as h1/h2/h3.
    Returns the full XHTML string.
    """
    document = Document(docx_path)
    paragraphs = [p for p in document.paragraphs if p.text.strip()]

    HEADING_MAP = {
        'Heading 1': ('h1', 'heading1'),
        'Heading 2': ('h2', 'heading2'),
        'Heading 3': ('h3', 'heading3'),
    }

    body = ''
    for para in paragraphs:
        style_name = para.style.name
        para_text = convert_runs(para)

        if style_name in HEADING_MAP:
            tag, css_class = HEADING_MAP[style_name]
            para_text = para_text.strip()
            body += f'\n\t<{tag} class="{css_class}">{para_text}</{tag}>'
        else:
            para_text = clean_inline(para_text)
            if para_text.strip():
                body += f'\n\t<p class="normalText">{para_text}</p>'

    return XHTML_START.format(title=book_title) + body + XHTML_END


def save_full_xhtml(xhtml, output_dir, book_title="Untitled"):
    """Save the full XHTML to a single file."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, 'full.xhtml')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(xhtml.strip())
    return filepath


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python3 docx_converter.py input.docx output_dir [title]")
        sys.exit(1)

    docx_path = sys.argv[1]
    output_dir = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else "Untitled"

    xhtml = convert_docx(docx_path, title)
    filepath = save_full_xhtml(xhtml, output_dir, title)
    print(f"Saved: {filepath}")
