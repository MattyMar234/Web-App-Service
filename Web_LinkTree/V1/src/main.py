from flask import Flask, render_template, request, jsonify, redirect, url_for
from database import init_db, get_entries, add_entry, update_entry, delete_entry
import os
import argparse
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
app.config['SECRET_KEY'] = 'your_secret_key_here'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    entries = get_entries()
    return render_template('index.html', entries=entries)

@app.route('/api/entries', methods=['GET'])
def api_get_entries():
    entries = get_entries()
    return jsonify(entries)

@app.route('/api/entries', methods=['POST'])
def api_add_entry():
    data = request.form
    icon = None
    
    if 'icon' in request.files:
        file = request.files['icon']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            icon_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(icon_path)
            icon = f"uploads/{filename}"
    
    entry_id = add_entry(
        title=data.get('title'),
        url=data.get('url'),
        template=data.get('template'),
        custom_color=data.get('custom_color'),
        custom_border_color=data.get('custom_border_color'),
        custom_text_color=data.get('custom_text_color'),
        icon=icon
    )
    
    return jsonify({"id": entry_id, "message": "Entry added successfully"})

@app.route('/api/entries/<int:entry_id>', methods=['PUT'])
def api_update_entry(entry_id):
    data = request.form
    new_icon_path = None
    
    if 'icon' in request.files:
        file = request.files['icon']
        # Controlla se è stato selezionato un nuovo file
        if file and file.filename != '':
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                icon_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(icon_path)
                new_icon_path = f"uploads/{filename}"
    
    # Chiama la funzione di update. Se new_icon_path è None, l'icona nel DB non verrà modificata.
    update_entry(
        entry_id=entry_id,
        title=data.get('title'),
        url=data.get('url'),
        template=data.get('template'),
        custom_color=data.get('custom_color'),
        custom_border_color=data.get('custom_border_color'),
        custom_text_color=data.get('custom_text_color'),
        icon=new_icon_path # Passa il nuovo percorso o None
    )
    
    return jsonify({"message": "Entry updated successfully"})

@app.route('/api/entries/<int:entry_id>', methods=['DELETE'])
def api_delete_entry(entry_id):
    delete_entry(entry_id)
    return jsonify({"message": "Entry deleted successfully"})

if __name__ == '__main__':
    init_db()

    parser = argparse.ArgumentParser(description='Avvia il server web Linktree Clone.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Indirizzo IP su cui il server è in ascolto. Default: '0.0.0.0'")
    parser.add_argument('--port', type=int, default=8080, help='Porta su cui il server è in ascolto. Default: 8080')
    args = parser.parse_args()
    
    print(f"Avvio del server su http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=True)