import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from routes.projects import projects_bp
from routes.split import split_bp
from routes.epub_import import epub_bp
from routes.build import build_bp

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Book Publisher API running'})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)