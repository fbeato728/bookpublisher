import os
import re
import json
from flask import Blueprint, request, jsonify

footnotes_bp = Blueprint('footnotes', __name__)

from config import PROJECTS_DIR

def _footnotes_path(project_id):
    return os.path.join(PROJECTS_DIR, project_id, 'footnotes.json')

def _parse_footnote_file(text):
    """Parse footnote file with format: (N) text"""
    footnotes = {}
    # Match (N) at start of line or after whitespace, capture everything until next (N) or end
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
    # Return as sorted list for display
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
