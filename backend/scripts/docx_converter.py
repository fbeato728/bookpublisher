import os
import json
import uuid
import io
from PIL import Image  # requires: pip install Pillow
from docx import Document
from config import GLOBAL_DIR

# Load config from global config file
CONFIG_PATH = os.path.join(GLOBAL_DIR, 'config', 'docx_converter.json')

def load_config():
    """Load DOCX converter config from JSON file."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}")

CONFIG = load_config()


def escape_xml(text):
    """Escape XML special characters based on config."""
    escaping = CONFIG['escaping']
    for char, escape_seq in escaping.items():
        text = text.replace(char, escape_seq)
    return text


def build_xhtml_start(title):
    """Build XHTML opening from config."""
    xhtml_cfg = CONFIG['xhtml']
    paths_cfg = CONFIG['paths']
    
    declaration = xhtml_cfg['declaration']
    html_ns = xhtml_cfg['namespaces']['html']
    epub_ns = xhtml_cfg['namespaces']['epub']
    content_type = xhtml_cfg['meta']['content_type']
    stylesheet_file = xhtml_cfg['stylesheet']['default_file']
    stylesheet_rel = xhtml_cfg['stylesheet']['rel']
    stylesheet_type = xhtml_cfg['stylesheet']['type']
    
    return (
        f"{declaration}\n"
        f"<html xmlns=\"{html_ns}\" xmlns:epub=\"{epub_ns}\">\n"
        f"  <head>\n"
        f"    <link rel=\"{stylesheet_rel}\" href=\"{paths_cfg['styles_relative']}{stylesheet_file}\" type=\"{stylesheet_type}\"/>\n"
        f"    <title>{escape_xml(title)}</title>\n"
        f"    <meta http-equiv=\"Content-Type\" content=\"{content_type}\"/>\n"
        f"  </head>\n"
        f"  <body>"
    )


def get_xhtml_end():
    """Get XHTML closing from config."""
    return CONFIG['xhtml']['closing_tags']


def get_heading_map():
    """Get heading style mapping from config."""
    return CONFIG['heading_map']


def convert_runs(para, images_dir=None):
    """
    Convert paragraph runs to HTML, handling text formatting and inline images.
    If images_dir is None, images are skipped.
    """
    images_cfg = CONFIG['images']
    paths_cfg = CONFIG['paths']
    msg_cfg = CONFIG['messages']['errors']
    
    result = ''
    for r in para.runs:
        text = r.text
        if text:
            text = escape_xml(text)
            
            # Apply formatting
            if r.italic and r.bold:
                text = f"<i><b>{text}</b></i>"
            elif r.italic:
                text = f"<i>{text}</i>"
            elif r.bold:
                text = f"<b>{text}</b>"
            result += text

        # Handle inline images if images_dir is provided
        if images_dir:
            drawing_elements = r.element.xpath('.//w:drawing')
            for drawing in drawing_elements:
                blip_elements = drawing.xpath('.//a:blip/@r:embed')
                if blip_elements:
                    rel_id = blip_elements[0]
                    try:
                        image_part = para.part.related_parts[rel_id]
                        image_bytes = image_part.blob
                        img = Image.open(io.BytesIO(image_bytes))
                        
                        # Determine extension
                        img_format = img.format.upper() if img.format else images_cfg['fallback_format']
                        if img_format not in images_cfg['supported_formats']:
                            ext = f".{images_cfg['fallback_format'].lower()}"
                        else:
                            ext = f".{img_format.lower()}"
                        
                        # Generate filename
                        uuid_part = uuid.uuid4().hex[:images_cfg['uuid_length']]
                        image_filename = f"{images_cfg['filename_prefix']}{uuid_part}{ext}"
                        image_filepath = os.path.join(images_dir, image_filename)
                        
                        # Save image, converting if necessary
                        if ext == f".{images_cfg['fallback_format'].lower()}" and img.format != images_cfg['fallback_format']:
                            img.save(image_filepath, images_cfg['fallback_format'])
                        else:
                            with open(image_filepath, 'wb') as f:
                                f.write(image_bytes)
                        
                        alt_text = images_cfg['alt_text_default']
                        result += f'\n\t<img src="{paths_cfg['images_relative']}{image_filename}" alt="{alt_text}" />\n'
                    except Exception as e:
                        error_msg = msg_cfg['image_processing'].format(error=str(e))
                        print(error_msg)

    return result


def convert_docx(docx_path, book_title="Untitled", images_dir=None):
    """
    Convert a DOCX to a single XHTML string.
    
    Args:
        docx_path: absolute path to input DOCX file
        book_title: title for the XHTML document
        images_dir: absolute path where extracted images should be saved.
                    If None, images are skipped.
    
    Returns:
        Full XHTML string.
    """
    if images_dir:
        os.makedirs(images_dir, exist_ok=True)

    document = Document(docx_path)
    heading_map = get_heading_map()
    paragraph_cfg = CONFIG['paragraph']
    body = ''

    for para in document.paragraphs:
        # Skip empty paragraphs if configured
        if paragraph_cfg['skip_empty'] and not para.text.strip() and not para.runs:
            continue

        # Convert paragraph content
        para_content = convert_runs(para, images_dir)
        if not para_content.strip():
            continue

        # Determine paragraph tag and class
        style_name = para.style.name
        if style_name in heading_map:
            tag = heading_map[style_name]['tag']
            css_class = heading_map[style_name]['class']
            body += f'\n\t<{tag} class="{css_class}">{para_content.strip()}</{tag}>'
        elif style_name.startswith('Heading'):
            # Fallback for unmapped heading styles
            level = ''.join(c for c in style_name if c.isdigit())
            tag = f"h{level}" if level else "h1"
            body += f'\n\t<{tag}>{para_content.strip()}</{tag}>'
        else:
            # Regular paragraph
            body += f'\n\t<p class="{paragraph_cfg['default_class']}">{para_content}</p>'

    xhtml_start = build_xhtml_start(book_title)
    xhtml_end = get_xhtml_end()
    return xhtml_start + body + xhtml_end


def save_full_xhtml(xhtml, output_dir, book_title="Untitled"):
    """Save the full XHTML to output_dir/full.xhtml."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, 'full.xhtml')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(xhtml.strip())
    return filepath


if __name__ == '__main__':
    import sys
    msg_cfg = CONFIG['messages']['cli']
    
    if len(sys.argv) < 3:
        print(msg_cfg['usage'])
        sys.exit(1)

    docx_path  = sys.argv[1]
    output_dir = sys.argv[2]
    title      = sys.argv[3] if len(sys.argv) > 3 else "Untitled"
    images_dir = os.path.join(os.path.dirname(output_dir), 'images')

    xhtml = convert_docx(docx_path, title, images_dir=images_dir)
    filepath = save_full_xhtml(xhtml, output_dir, title)
    print(msg_cfg['success'].format(filepath=filepath))