import sqlite3
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path='transcriptions.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Inizializza il database creando la tabella se non esiste."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transcriptions (
                        id TEXT PRIMARY KEY,
                        display_name TEXT,
                        original_filename TEXT,
                        language TEXT,
                        model TEXT,
                        temperature REAL,
                        created_at TEXT,
                        status TEXT,
                        content TEXT
                    )
                ''')
                # Indice per velocizzare l'ordinamento per data
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON transcriptions(created_at)')
                conn.commit()
            logger.info(f"Database inizializzato correttamente: {self.db_path}")
        except Exception as e:
            logger.error(f"Errore inizializzazione database: {str(e)}")

    def _check_size_limit(self, content: str) -> bool:
        """Verifica se il contenuto rispetta il limite di 2MB."""
        if content and len(content.encode('utf-8')) > 2 * 1024 * 1024: # 2MB in bytes
            return False
        return True

    def add_transcription(self, id: str, display_name: str, original_filename: str, 
                          language: str, model: str, temperature: float, 
                          created_at: str, status: str, content: str) -> bool:
        """Aggiunge una nuova trascrizione. Restituisce False se supera i 2MB."""
        
        if not self._check_size_limit(content):
            logger.error(f"Trascrizione {id} supera il limite di 2MB. Salvataggio annullato.")
            return False

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO transcriptions 
                    (id, display_name, original_filename, language, model, temperature, created_at, status, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (id, display_name, original_filename, language, model, temperature, created_at, status, content))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Errore salvataggio DB: {str(e)}")
            return False

    def get_transcription(self, id: str) -> Optional[Dict[str, Any]]:
        """Recupera una singola trascrizione completa di contenuto."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM transcriptions WHERE id = ?', (id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Errore lettura DB: {str(e)}")
            return None

    def get_transcriptions_paginated(self, page: int, limit: int, sort_by: str, sort_order: str) -> Dict:
        """
        Recupera le trascrizioni paginate e ordinate.
        Non restituisce il campo 'content' per risparmiare memoria nella lista.
        """
        offset = (page - 1) * limit
        
        # Whitelist per evitare SQL Injection sulle colonne
        valid_sort_cols = {'created_at': 'created_at', 'name': 'display_name'}
        safe_sort_by = valid_sort_cols.get(sort_by, 'created_at')
        safe_sort_order = 'DESC' if sort_order == 'desc' else 'ASC'

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Conta il totale
                cursor.execute('SELECT COUNT(*) FROM transcriptions')
                total_items = cursor.fetchone()[0]

                # Query dati (esclude content)
                # Nota: original_filename usato come fallback se display_name è null
                query = f'''
                    SELECT id, display_name, original_filename, language, model, temperature, created_at, status 
                    FROM transcriptions 
                    ORDER BY {safe_sort_by} {safe_sort_order} 
                    LIMIT ? OFFSET ?
                '''
                cursor.execute(query, (limit, offset))
                rows = cursor.fetchall()
                
                items = []
                for row in rows:
                    item = dict(row)
                    # Se display_name è vuoto, usa il nome file originale
                    if not item['display_name']:
                        item['display_name'] = item['original_filename']
                    items.append(item)

                total_pages = (total_items + limit - 1) // limit

                return {
                    'items': items,
                    'pagination': {
                        'current_page': page,
                        'total_pages': total_pages,
                        'total_items': total_items,
                        'items_per_page': limit,
                        'sort_by': sort_by,
                        'sort_order': sort_order
                    }
                }
        except Exception as e:
            logger.error(f"Errore paginazione DB: {str(e)}")
            return {'items': [], 'pagination': {}}

    def update_name(self, id: str, new_name: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE transcriptions SET display_name = ? WHERE id = ?', (new_name, id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Errore update DB: {str(e)}")
            return False

    def delete_transcription(self, id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM transcriptions WHERE id = ?', (id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Errore delete DB: {str(e)}")
            return False