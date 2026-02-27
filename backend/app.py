import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests as http_requests
from routes.projects import projects_bp
from routes.split import split_bp
from routes.epub_import import epub_bp
from routes.build import build_bp
from routes.ignore import ignore_bp
from routes.ignore import load_ignore
from routes.images import images_bp
from routes.footnotes import footnotes_bp
from routes.hyphenate import hyphenate_bp

app = Flask(__name__,
    template_folder='templates',
    static_folder='static')
CORS(app)
app.config['PROJECTS_DIR'] = '/srv/bookpublisher/projects'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.register_blueprint(projects_bp)
app.register_blueprint(split_bp)
app.register_blueprint(epub_bp)
app.register_blueprint(build_bp)
app.register_blueprint(ignore_bp)
app.register_blueprint(images_bp)
app.register_blueprint(footnotes_bp)
app.register_blueprint(hyphenate_bp)

LT_URL = 'http://localhost:8082/v2/check'

@app.route('/api/check', methods=['POST'])
def lt_check():
    """Proxy to LanguageTool. Strips soft hyphens and filters project ignore list."""
    body       = request.get_json(force=True)
    text       = body.get('text', '')
    lang       = body.get('language', 'ca-ES')
    project_id = body.get('project_id', '')

    # Strip soft hyphens (&shy; / \u00ad) so LT never sees them
    text = text.replace('\u00ad', '')

    # Load this project's ignore list
    ignored = load_ignore(project_id) if project_id else set()

    try:
        resp = http_requests.post(LT_URL, data={
            'text':     text,
            'language': lang,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        matches = data.get('matches', [])

        # Filter out any match whose surface form is in the ignore list
        if ignored:
            def _surface(m):
                s = m.get('offset', 0)
                l = m.get('length', 0)
                return text[s:s+l].lower()
            matches = [m for m in matches if _surface(m) not in ignored]

        return jsonify(matches)

    except http_requests.exceptions.ConnectionError:
        return jsonify({'error': 'LanguageTool not reachable on port 8082'}), 502
    except http_requests.exceptions.Timeout:
        return jsonify({'error': 'LanguageTool timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Book Publisher API running'})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)