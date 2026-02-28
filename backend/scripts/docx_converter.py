import os
import uuid
import io
from PIL import Image  # requires: pip install Pillow
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

HEADING_MAP = {
    'Heading 1': ('h1', 'heading1'),
    'Heading 2': ('h2', 'heading2'),
    'Heading 3': ('h3', 'heading3'),
}

def convert_runs(para, images_dir):
    result = ''
    for r in para.runs:
        text = r.text
        if text:
            text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if r.italic and r.bold:
                text = f"<i><b>{text}</b></i>"
            elif r.italic:
                text = f"<i>{text}</i>"
            elif r.bold:
                text = f"<b>{text}</b>"
            result += text

        drawing_elements = r.element.xpath('.//w:drawing')
        for drawing in drawing_elements:
            blip_elements = drawing.xpath('.//a:blip/@r:embed')
            if blip_elements:
                rel_id = blip_elements[0]
                image_part = para.part.related_parts[rel_id]
                image_bytes = image_part.blob
                try:
                    img = Image.open(io.BytesIO(image_bytes))
                    ext = f".{img.format.lower()}"
                    if img.format not in ['PNG', 'JPEG', 'GIF', 'WEBP']:
                        ext = '.png'
                    image_filename = f"img_{uuid.uuid4().hex[:8]}{ext}"
                    image_filepath = os.path.join(images_dir, image_filename)
                    if ext == '.png' and img.format != 'PNG':
                        img.save(image_filepath, 'PNG')
                    else:
                        with open(image_filepath, 'wb') as f:
                            f.write(image_bytes)
                    result += f'\n\t<img src="../images/{image_filename}" alt="image" />\n'
                except Exception as e:
                    print(f"Warning: Could not process an image: {e}")
    return result


def _convert_runs_text_only(para):
    result = ''
    for r in para.runs:
        text = r.text
        if not text:
            continue
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        if r.italic and r.bold:
            text = f"<i><b>{text}</b></i>"
        elif r.italic:
            text = f"<i>{text}</i>"
        elif r.bold:
            text = f"<b>{text}</b>"
        result += text
    return result


def convert_docx(docx_path, book_title="Untitled", images_dir=None):
    """
    Convert a DOCX to a single XHTML string.
    images_dir: absolute path where extracted images should be saved.
                If None, images are skipped.
    Returns the full XHTML string.
    """
    if images_dir:
        os.makedirs(images_dir, exist_ok=True)

    document = Document(docx_path)
    body = ''

    for para in document.paragraphs:
        if not para.text.strip() and not para.runs:
            continue

        para_content = convert_runs(para, images_dir) if images_dir else _convert_runs_text_only(para)
        if not para_content.strip():
            continue

        style_name = para.style.name
        if style_name in HEADING_MAP:
            tag, css_class = HEADING_MAP[style_name]
            body += f'\n\t<{tag} class="{css_class}">{para_content.strip()}</{tag}>'
        elif style_name.startswith('Heading'):
            level = style_name.split()[-1]
            tag = f"h{level}" if level.isdigit() else "h1"
            body += f'\n\t<{tag}>{para_content.strip()}</{tag}>'
        else:
            body += f'\n\t<p class="normalText">{para_content}</p>'

    return XHTML_START.format(title=book_title) + body + XHTML_END


def save_full_xhtml(xhtml, output_dir, book_title="Untitled"):
    """Save the full XHTML to output_dir/full.xhtml."""
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

    docx_path  = sys.argv[1]
    output_dir = sys.argv[2]
    title      = sys.argv[3] if len(sys.argv) > 3 else "Untitled"
    images_dir = os.path.join(os.path.dirname(output_dir), 'images')

    xhtml = convert_docx(docx_path, title, images_dir=images_dir)
    save_full_xhtml(xhtml, output_dir, title)
    print(f"Done. XHTML saved to {output_dir}/full.xhtml")