import argparse
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os
from pathlib import Path
from data_manager import DataManagerFactory
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = Flask(__name__, static_folder='../frontend/public', static_url_path='')
CORS(app)

# Initialize data manager with factory pattern
data_manager = DataManagerFactory.create(os.environ.get('STORAGE_TYPE', 'JSON'))

# Serve static files
@app.route('/')
def serve_index():
    assert app.static_folder is not None
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    assert app.static_folder is not None
    return send_from_directory(app.static_folder, path)

# API Routes
@app.route('/api/links', methods=['GET'])
def get_links():
    links = data_manager.get_all_links()
    return jsonify(links)

@app.route('/api/links', methods=['POST'])
def create_link():
    link_data = request.json
    if link_data is None:
        return jsonify({'error': 'data is None'}), 404 
    
    new_link = data_manager.create_link(link_data)
    return jsonify(new_link), 201

@app.route('/api/links/<link_id>', methods=['PUT'])
def update_link(link_id):
    link_data = request.json
    if link_data is None:
        return jsonify({'error': 'data is None'}), 404 
    
    updated_link = data_manager.update_link(link_id, link_data)
    if updated_link:
        return jsonify(updated_link)
    return jsonify({'error': 'Link not found'}), 404

@app.route('/api/links/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    success = data_manager.delete_link(link_id)
    if success:
        return jsonify({'message': 'Link deleted'})
    return jsonify({'error': 'Link not found'}), 404

@app.route('/api/links/reorder', methods=['PUT'])
def reorder_links():
    order_data = request.json  # Expected: {'links': [list of links in new order]}
    
    if order_data is None or type(order_data) != dict:
        return jsonify({'error': 'data is None'}), 404 
    
    data_manager.reorder_links(order_data.get('links', []))
    return jsonify({'message': 'Links reordered'})

@app.route('/api/export', methods=['GET'])
def export_data():
    data = data_manager.export_data()
    return jsonify(data)

@app.route('/api/import', methods=['POST'])
def import_data():
    data = request.json
    if data is None:
        return jsonify({'error': 'data is None'}), 404 
    data_manager.import_data(data)
    return jsonify({'message': 'Data imported successfully'})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    settings = data_manager.get_settings()
    return jsonify(settings)

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    settings_data = request.json
    if settings_data is None:
        return jsonify({'error': 'data is None'}), 404 
    updated_settings = data_manager.update_settings(settings_data)
    return jsonify(updated_settings)

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Avvia il server web Linktree Clone.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Indirizzo IP su cui il server è in ascolto. Default: '0.0.0.0'")
    parser.add_argument('--port', type=int, default=8080, help='Porta su cui il server è in ascolto. Default: 8080')
    args = parser.parse_args()
    
    print(f"Avvio del server su http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)
