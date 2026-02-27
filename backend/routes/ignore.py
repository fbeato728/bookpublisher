import os
import json
from flask import Blueprint, request, jsonify

ignore_bp = Blueprint('ignore', __name__)

PROJECTS_DIR = '/srv/bookpublisher/projects'


def _ignore_path(project_id):
    return os.path.join(PROJECTS_DIR, project_id, 'ignore_words.json')


def load_ignore(project_id):
    """Return the ignore list as a set of lowercase strings."""
    path = _ignore_path(project_id)
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(w.lower() for w in data if isinstance(w, str))
    except Exception:
        return set()


def save_ignore(project_id, words_set):
    path = _ignore_path(project_id)
    with open(path, 'w') as f:
        json.dump(sorted(words_set), f, ensure_ascii=False, indent=2)


@ignore_bp.route('/api/projects/<project_id>/ignore-words', methods=['GET'])
def get_ignore_words(project_id):
    """Return the sorted ignore list for this project."""
    path = _ignore_path(project_id)
    if not os.path.exists(path):
        return jsonify([])
    try:
        with open(path) as f:
            data = json.load(f)
        return jsonify(sorted(data, key=str.lower))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ignore_bp.route('/api/projects/<project_id>/ignore-words', methods=['POST'])
def add_ignore_word(project_id):
    """Add a word to the ignore list. Body: { "word": "..." }"""
    body = request.get_json(force=True)
    word = (body.get('word') or '').strip()
    if not word:
        return jsonify({'error': 'word is required'}), 400

    words = load_ignore(project_id)
    words.add(word.lower())
    save_ignore(project_id, words)
    return jsonify({'ok': True, 'word': word.lower(), 'count': len(words)})


@ignore_bp.route('/api/projects/<project_id>/ignore-words/<word>', methods=['DELETE'])
def remove_ignore_word(project_id, word):
    """Remove a word from the ignore list."""
    words = load_ignore(project_id)
    words.discard(word.lower())
    save_ignore(project_id, words)
    return jsonify({'ok': True, 'count': len(words)})