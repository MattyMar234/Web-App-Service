# data_manager.py

import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Any, Final
import threading

# Configurazione del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Directory per le trascrizioni (usata per l'esempio)
TRANSCRIPTIONS_DIR: Final[str] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcriptions")

if not os.path.exists(TRANSCRIPTIONS_DIR):
    os.makedirs(TRANSCRIPTIONS_DIR)


class FileStatus(Enum):
    """Enum per rappresentare lo stato di elaborazione del file."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class DataManager:
    """
    Classe per la gestione dei file tramite database SQLite.
    Progettata per essere thread-safe: ogni thread ottiene la propria connessione.
    
    Args:
        db_path (str): Percorso del file del database SQLite.
        files_dir (str): Directory in cui sono memorizzati i file.
    """
    
    def __init__(self, db_path: str, files_dir: str):
        self.db_path = db_path
        self.files_dir = files_dir
        self._initialize_db()
    
    def _initialize_db(self) -> None:
        """Inizializza il database creando la tabella se non esiste e impostando la modalità WAL."""
        # La connessione per l'inizializzazione può essere una sola poiché avviene in __init__
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        filename TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP NOT NULL,
                        status TEXT NOT NULL,
                        config TEXT
                    )
                ''')
                # Abilita la modalità Write-Ahead Logging per migliore concorrenza
                cursor.execute('PRAGMA journal_mode=WAL;')
                conn.commit()
                logger.info(f"Database inizializzato e modalità WAL impostata: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Errore durante l'inizializzazione del database: {e}")
            raise

    def _get_connection(self) -> sqlite3.Connection:
        """Crea e restituisce una nuova connessione al database."""
        # Ogni thread che chiama questo metodo otterrà una connessione unica.
        # Il timeout gestisce i casi di alta contensione sul lock del file.
        return sqlite3.connect(self.db_path, timeout=10.0)

    def insert_file(self, filename: str, status: FileStatus, config: Optional[Dict[str, Any]] = None) -> int:
        """
        Inserisce un nuovo file nel database.
        Thread-safe.
        """
        config_json = json.dumps(config) if config else None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO files (filename, created_at, status, config)
                    VALUES (?, ?, ?, ?)
                ''', (filename, datetime.now(), status.value, config_json))
                conn.commit()
                file_id = cursor.lastrowid
                logger.info(f"File inserito: {filename} con ID {file_id} nel thread {threading.current_thread().name}")
                return file_id
        except sqlite3.IntegrityError:
            logger.error(f"Il file {filename} esiste già nel database")
            raise
        except sqlite3.Error as e:
            logger.error(f"Errore durante l'inserimento del file: {e}")
            raise

    def get_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Recupera i dettagli di un file tramite ID. Thread-safe."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM files WHERE id = ?', (file_id,))
                row = cursor.fetchone()
                if row:
                    result = dict(row)
                    if result['config']:
                        result['config'] = json.loads(result['config'])
                    return result
                return None
        except sqlite3.Error as e:
            logger.error(f"Errore durante il recupero del file con ID {file_id}: {e}")
            raise

    def get_file_by_name(self, filename: str) -> Optional[Dict[str, Any]]:
        """Recupera i dettagli di un file tramite nome. Thread-safe."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM files WHERE filename = ?', (filename,))
                row = cursor.fetchone()
                if row:
                    result = dict(row)
                    if result['config']:
                        result['config'] = json.loads(result['config'])
                    return result
                return None
        except sqlite3.Error as e:
            logger.error(f"Errore durante il recupero del file {filename}: {e}")
            raise

    def update_file_status(self, file_id: int, status: FileStatus) -> None:
        """Aggiorna lo stato di un file. Thread-safe."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE files SET status = ? WHERE id = ?', (status.value, file_id))
                conn.commit()
                if cursor.rowcount == 0:
                    logger.warning(f"Nessun file trovato con ID {file_id}")
                else:
                    logger.info(f"Stato del file {file_id} aggiornato a {status.value}")
        except sqlite3.Error as e:
            logger.error(f"Errore durante l'aggiornamento dello stato del file {file_id}: {e}")
            raise

    def update_file_config(self, file_id: int, config: Dict[str, Any]) -> None:
        """Aggiorna la configurazione di un file. Thread-safe."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                config_json = json.dumps(config)
                cursor.execute('UPDATE files SET config = ? WHERE id = ?', (config_json, file_id))
                conn.commit()
                if cursor.rowcount == 0:
                    logger.warning(f"Nessun file trovato con ID {file_id}")
                else:
                    logger.info(f"Configurazione del file {file_id} aggiornata")
        except sqlite3.Error as e:
            logger.error(f"Errore durante l'aggiornamento della configurazione del file {file_id}: {e}")
            raise

    def delete_file(self, file_id: int, delete_physical_file: bool = False) -> bool:
        """Elimina un file dal database e opzionalmente il file fisico. Thread-safe."""
        file_details = self.get_file(file_id)
        if not file_details:
            logger.warning(f"Nessun file trovato con ID {file_id}")
            return False
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
                conn.commit()

                if delete_physical_file:
                    file_path = os.path.join(self.files_dir, file_details['filename'])
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"File fisico eliminato: {file_path}")
                    else:
                        logger.warning(f"File fisico non trovato: {file_path}")
                
                logger.info(f"File con ID {file_id} eliminato dal database")
                return True
        except sqlite3.Error as e:
            logger.error(f"Errore durante l'eliminazione del file {file_id}: {e}")
            raise

    def get_all_files(self, status: Optional[FileStatus] = None) -> List[Dict[str, Any]]:
        """Recupera tutti i file, opzionalmente filtrati per stato. Thread-safe."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if status:
                    cursor.execute('SELECT * FROM files WHERE status = ? ORDER BY created_at DESC', (status.value,))
                else:
                    cursor.execute('SELECT * FROM files ORDER BY created_at DESC')
                
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    file_data = dict(row)
                    if file_data['config']:
                        file_data['config'] = json.loads(file_data['config'])
                    result.append(file_data)
                return result
        except sqlite3.Error as e:
            logger.error(f"Errore durante il recupero dei file: {e}")
            raise

    def count_files(self, status: Optional[FileStatus] = None) -> int:
        """Conta il numero di file, opzionalmente filtrati per stato. Thread-safe."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if status:
                    cursor.execute('SELECT COUNT(*) FROM files WHERE status = ?', (status.value,))
                else:
                    cursor.execute('SELECT COUNT(*) FROM files')
                count = cursor.fetchone()[0]
                return count
        except sqlite3.Error as e:
            logger.error(f"Errore durante il conteggio dei file: {e}")
            raise

    def get_oldest_file(self) -> Optional[Dict[str, Any]]:
        """Recupera il file meno recente nel database. Thread-safe."""
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM files ORDER BY created_at ASC LIMIT 1')
                row = cursor.fetchone()
                if row:
                    result = dict(row)
                    if result['config']:
                        result['config'] = json.loads(result['config'])
                    return result
                return None
        except sqlite3.Error as e:
            logger.error(f"Errore durante il recupero del file meno recente: {e}")
            raise

    def get_files_older_than(self, days: int) -> List[Dict[str, Any]]:
        """Recupera i file più vecchi di un numero specificato di giorni. Thread-safe."""
        threshold_date = datetime.now() - timedelta(days=days)
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM files WHERE created_at < ? ORDER BY created_at ASC', (threshold_date,))
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    file_data = dict(row)
                    if file_data['config']:
                        file_data['config'] = json.loads(file_data['config'])
                    result.append(file_data)
                return result
        except sqlite3.Error as e:
            logger.error(f"Errore durante il recupero dei file più vecchi di {days} giorni: {e}")
            raise


class GarbageCollector:
    """
    Classe per la pulizia dei file e delle entry nel database.
    Utilizza un'istanza di DataManager, quindi eredita la sua thread-safety per le operazioni DB.
    """
    def __init__(self, data_manager: DataManager, max_file_age_days: int = 30):
        self.data_manager = data_manager
        self.max_file_age_days = max_file_age_days

    def cleanup_old_files(self) -> int:
        """Rimuove i file più vecchi di max_file_age_days giorni."""
        old_files = self.data_manager.get_files_older_than(self.max_file_age_days)
        removed_count = 0
        for file_data in old_files:
            file_id = file_data['id']
            if self.data_manager.delete_file(file_id, delete_physical_file=True):
                removed_count += 1
                logger.info(f"Rimosso file vecchio: {file_data['filename']} (ID: {file_id})")
        logger.info(f"Rimossi {removed_count} file vecchi.")
        return removed_count

    def cleanup_orphaned_files(self) -> int:
        """Rimuove i file nel filesystem che non hanno una entry nel DB."""
        db_files = {f['filename'] for f in self.data_manager.get_all_files()}
        removed_count = 0
        for filename in os.listdir(self.data_manager.files_dir):
            file_path = os.path.join(self.data_manager.files_dir, filename)
            if os.path.isdir(file_path):
                continue
            if filename not in db_files:
                try:
                    os.remove(file_path)
                    removed_count += 1
                    logger.info(f"Rimosso file orfano: {filename}")
                except OSError as e:
                    logger.error(f"Errore rimuovendo file orfano {filename}: {e}")
        logger.info(f"Rimossi {removed_count} file orfani.")
        return removed_count

    def cleanup_missing_files(self) -> int:
        """Rimuove le entry nel DB per file che non esistono nel filesystem."""
        all_files = self.data_manager.get_all_files()
        removed_count = 0
        for file_data in all_files:
            file_path = os.path.join(self.data_manager.files_dir, file_data['filename'])
            if not os.path.exists(file_path):
                self.data_manager.delete_file(file_data['id'], delete_physical_file=False)
                removed_count += 1
                logger.info(f"Rimossa entry DB per file mancante: {file_data['filename']}")
        logger.info(f"Rimosse {removed_count} entry di file mancanti.")
        return removed_count

    def run_full_cleanup(self) -> Dict[str, int]:
        """Esegue una pulizia completa."""
        result = {
            'old_files': self.cleanup_old_files(),
            'orphaned_files': self.cleanup_orphaned_files(),
            'missing_files': self.cleanup_missing_files()
        }
        logger.info(f"Pulizia completa completata. Totale elementi rimossi: {sum(result.values())}")
        return result
