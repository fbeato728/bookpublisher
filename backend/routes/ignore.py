import os
import json
from flask import Blueprint, request, jsonify

ignore_bp = Blueprint('ignore', __name__)

from config import PROJECTS_DIR


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

# ── Rule exceptions ───────────────────────────────────────────────────────────

def _rules_path(project_id):
    return os.path.join(PROJECTS_DIR, project_id, 'ignore_rules.json')


def load_ignore_rules(project_id):
    """Return the rule ignore list as a list of {rule_id, surface} dicts."""
    path = _rules_path(project_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        return [r for r in data if isinstance(r, dict) and 'rule_id' in r and 'surface' in r]
    except Exception:
        return []


def save_ignore_rules(project_id, rules_list):
    path = _rules_path(project_id)
    with open(path, 'w') as f:
        json.dump(rules_list, f, ensure_ascii=False, indent=2)


@ignore_bp.route('/api/projects/<project_id>/ignore-rules', methods=['GET'])
def get_ignore_rules(project_id):
    """Return the rule ignore list for this project."""
    return jsonify(load_ignore_rules(project_id))


@ignore_bp.route('/api/projects/<project_id>/ignore-rules', methods=['POST'])
def add_ignore_rule(project_id):
    """Add a rule+surface exception. Body: { "rule_id": "...", "surface": "..." }"""
    body    = request.get_json(force=True)
    rule_id = (body.get('rule_id') or '').strip()
    surface = (body.get('surface') or '').strip().lower()
    if not rule_id or not surface:
        return jsonify({'error': 'rule_id and surface are required'}), 400
    rules = load_ignore_rules(project_id)
    if not any(r['rule_id'] == rule_id and r['surface'] == surface for r in rules):
        rules.append({'rule_id': rule_id, 'surface': surface})
        save_ignore_rules(project_id, rules)
    return jsonify({'ok': True, 'count': len(rules)})


@ignore_bp.route('/api/projects/<project_id>/ignore-rules', methods=['DELETE'])
def remove_ignore_rule(project_id):
    """Remove a rule+surface exception. Query params: ?rule_id=X&surface=Y"""
    rule_id = (request.args.get('rule_id') or '').strip()
    surface = (request.args.get('surface') or '').strip().lower()
    if not rule_id or not surface:
        return jsonify({'error': 'rule_id and surface query params required'}), 400
    rules = load_ignore_rules(project_id)
    rules = [r for r in rules if not (r['rule_id'] == rule_id and r['surface'] == surface)]
    save_ignore_rules(project_id, rules)
    return jsonify({'ok': True, 'count': len(rules)})