import os
import re
import json

from config import GLOBAL_DIR

TOKENS_PATH = os.path.join(GLOBAL_DIR, 'config', 'tokens.json')


def fill_tokens(content: str, meta: dict) -> str:
    """Replace {{TOKEN}} placeholders in content using meta and tokens.json mapping."""
    with open(TOKENS_PATH, encoding='utf-8') as f:
        token_config = json.load(f)

    for token, token_info in token_config.items():
        value = ''

        if 'meta_field' in token_info:
            value = meta.get(token_info['meta_field'], '')
        elif 'meta_fields' in token_info:
            for field in token_info['meta_fields']:
                value = meta.get(field, '')
                if value:
                    break

        if not value:
            value = token_info.get('default', '')

        content = content.replace(token, value or '')

    return content

# ── Self-closing tag normalisation ────────────────────────────────────────────
# lxml may serialise empty non-void elements as self-closing (e.g. <span/>).
# Tags listed here are always written as explicit open+close regardless.
# Add any tag that must never be self-closing in project XHTML files.
EXPLICIT_CLOSE_TAGS = {'span'}

_SELF_CLOSING_RE = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>]*)?)/>')

def _restore_explicit_close(data: bytes) -> bytes:
    """Expand self-closing tags in EXPLICIT_CLOSE_TAGS to explicit open+close form."""
    text = data.decode('utf-8')
    def _expand(m):
        tag   = m.group(1)
        attrs = m.group(2)
        if tag.lower() in EXPLICIT_CLOSE_TAGS:
            return f'<{tag}{attrs}></{tag}>'
        return m.group(0)
    text = _SELF_CLOSING_RE.sub(_expand, text)
    return text.encode('utf-8')