import sqlite3
import os # Importa os
from contextlib import contextmanager

# Definisci il percorso del database in modo assoluto
# Questo assicura che il file venga sempre creato nella cartella del progetto
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'data', 'linktree.db')
os.makedirs(os.path.dirname(DATABASE), exist_ok=True)

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                template TEXT DEFAULT 'default',
                custom_color TEXT,
                custom_border_color TEXT,
                custom_text_color TEXT,
                icon TEXT,
                position INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def get_entries():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM entries ORDER BY position ASC, id ASC')
        entries = cursor.fetchall()
        return [
            {
                'id': entry[0],
                'title': entry[1],
                'url': entry[2],
                'template': entry[3],
                'custom_color': entry[4],
                'custom_border_color': entry[5],
                'custom_text_color': entry[6],
                'icon': entry[7],
                'position': entry[8]
            }
            for entry in entries
        ]

def add_entry(title, url, template='default', custom_color=None, custom_border_color=None, custom_text_color=None, icon=None):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO entries (title, url, template, custom_color, custom_border_color, custom_text_color, icon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, url, template, custom_color, custom_border_color, custom_text_color, icon))
        conn.commit()
        return cursor.lastrowid

def update_entry(entry_id, title, url, template='default', custom_color=None, custom_border_color=None, custom_text_color=None, icon=None):
    with get_db() as conn:
        cursor = conn.cursor()
        # Costruisci la query di aggiornamento in modo dinamico
        # per non sovrascrivere l'icona se non viene fornita una nuova
        query_parts = []
        params = []
        
        query_parts.append("title = ?")
        params.append(title)
        
        query_parts.append("url = ?")
        params.append(url)
        
        query_parts.append("template = ?")
        params.append(template)
        
        query_parts.append("custom_color = ?")
        params.append(custom_color)
        
        query_parts.append("custom_border_color = ?")
        params.append(custom_border_color)
        
        query_parts.append("custom_text_color = ?")
        params.append(custom_text_color)

        # Aggiungi l'icona ai parametri solo se è stata effettivamente passata (non None)
        if icon is not None:
            query_parts.append("icon = ?")
            params.append(icon)

        params.append(entry_id)
        
        query = f"UPDATE entries SET {', '.join(query_parts)} WHERE id = ?"
        
        cursor.execute(query, params)
        conn.commit()

def delete_entry(entry_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM entries WHERE id=?', (entry_id,))
        conn.commit()