import sqlite3
import logging
import threading
from typing import Dict, List, Optional, Any
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)


@dataclass
class Transcription:
    id: str
    display_name: Optional[str]
    original_filename: str
    language: str
    model: str
    temperature: float
    created_at: str
    status: str
    content: str
    
    @staticmethod
    def from_db_row(row: Any) -> 'Transcription':
        """Crea un oggetto Transcription da una riga (Row) del database."""
        # row può essere un oggetto sqlite3.Row o un dizionario
        d = dict(row)
        return Transcription(
            id=d['id'],
            display_name=d['display_name'] or d['original_filename'],
            original_filename=d['original_filename'],
            language=d['language'],
            model=d['model'],
            temperature=d['temperature'],
            created_at=d['created_at'],
            status=d['status'],
            content=d.get('content', "") # Il contenuto potrebbe mancare nelle query paginate
        )
        
    def to_dict(self) -> Dict[str, Any]:
        """Restituisce la rappresentazione a dizionario dell'oggetto."""
        return asdict(self)
    
    
    def get_download_name(self) -> str:
        safe_display_name = self.display_name.replace(']', '').replace('[', '')
        return f"[{safe_display_name}]-[{self.created_at}]-[{self.language}]-[{self.model}]-[t{self.temperature}].txt" 
    



class DatabaseManager:
    def __init__(self, db_path='transcriptions.db'):
        self.db_path = db_path
        
        # Lock per garantire la thread-safety
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
    
        self._init_db()

    def _init_db(self):
        """Inizializza il database con protezione lock."""
        with self._lock:
            try:
                with self._conn as conn:
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

    def add_transcription(self, t: Transcription) -> bool:
        """Riceve un oggetto Transcription e lo salva in modo thread-safe."""
        if not self._check_size_limit(t.content):
            logger.error(f"Trascrizione {t.id} supera il limite di 2MB.")
            return False

        with self._lock:
            try:
                with self._conn as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO transcriptions 
                        (id, display_name, original_filename, language, model, temperature, created_at, status, content)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (t.id, t.display_name, t.original_filename, t.language, 
                          t.model, t.temperature, t.created_at, t.status, t.content))
                    conn.commit()
                return True
            except Exception as e:
                logger.error(f"Errore salvataggio DB: {str(e)}")
                return False
            

    def get_transcription(self, id: str) -> Optional[Transcription]:
        """Recupera una trascrizione e restituisce un oggetto Transcription."""
        with self._lock:
            try:
                with self._conn as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM transcriptions WHERE id = ?', (id,))
                    row = cursor.fetchone()
                    return Transcription.from_db_row(row) if row else None
            except Exception as e:
                logger.error(f"Errore lettura: {e}")
                return None

    def get_transcriptions_paginated(self, page: int, limit: int, sort_by: str, sort_order: str) -> Dict:
        """
        Recupera le trascrizioni paginate e ordinate.
        Non restituisce il campo 'content' per risparmiare memoria nella lista.
        """
        offset = (page - 1) * limit
        valid_sort_cols = {'created_at': 'created_at', 'name': 'display_name'}
        safe_sort_by = valid_sort_cols.get(sort_by, 'created_at')
        safe_sort_order = 'DESC' if sort_order == 'desc' else 'ASC'

        with self._lock:
            try:
                with self._conn as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT COUNT(*) FROM transcriptions')
                    total_items = cursor.fetchone()[0]

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
                        if not item['display_name']:
                            item['display_name'] = item['original_filename']
                        items.append(item)

                    total_pages = (total_items + limit - 1) // limit if limit > 0 else 0

                    return {
                        'items': items,
                        'pagination': {
                            'current_page': page,
                            'total_pages': total_pages,
                            'total_items': total_items,
                            'items_per_page': limit
                        }
                    }
            except Exception as e:
                logger.error(f"Errore paginazione DB: {str(e)}")
                return {'items': [], 'pagination': {}}


    def update_name(self, id: str, new_name: str) -> bool:
        with self._lock:
            try:
                with self._conn as conn:
                    cursor = conn.cursor()
                    cursor.execute('UPDATE transcriptions SET display_name = ? WHERE id = ?', (new_name, id))
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Errore update DB: {str(e)}")
                return False

    def delete_transcription(self, id: str) -> bool:
        with self._lock:
            try:
                with self._conn as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM transcriptions WHERE id = ?', (id,))
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Errore delete DB: {str(e)}")
                return False