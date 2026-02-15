from flask import Flask, request, jsonify
from flask_cors import CORS
from scraper import JobScraper
import os

app = Flask(__name__)
CORS(app)
scraper = JobScraper()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        'message': 'Job Search API',
        'version': '1.0',
        'endpoints': {
            'search': '/api/search?keyword=your_keyword'
        }
    })

@app.route('/api/search', methods=['GET'])
def search():
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'error': 'Keyword parameter is required'}), 400
    try:
        results = scraper.search_jobs(keyword)
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
