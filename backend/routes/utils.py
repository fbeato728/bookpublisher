import os
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