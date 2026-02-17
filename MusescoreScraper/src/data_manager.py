from dataclasses import dataclass
from enum import Enum
import sqlite3
import os
import threading
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple, List

from global_vars import *

class DownloadStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class FileRecord:
    """
    Dataclass che modella le informazioni di un file.
    Utilizzata per passare i dati in modo strutturato e tipizzato.
    """
    file_name: str
    size: int
    created_at: str  # Memorizzato come stringa ISO format
    scale: float
    filter: int
    source_url: str  # Link di origine del file
    status: DownloadStatus = DownloadStatus.PENDING
    
    
class GarbageCollector:
    
    def __init__(self, db_manager: 'DataBaseManager', download_path: str, scan_interval_s: int = 60, delated_time_s: int = 1200):
        self.__db_manager = db_manager
        self.__download_path = download_path
        self.__scan_interval_s = scan_interval_s
        self.__delated_time_s = delated_time_s
        self.__stop_event = threading.Event()
        self.__lock = threading.Lock()
        
    def start(self):
        """Avvia il processo di pulizia in un thread separato."""
        thread = threading.Thread(target=self.__run_cleanup_loop)
        thread.daemon = True
        thread.start()
        
    def stop(self):
        """Segnala al processo di pulizia di fermarsi."""
        self.__stop_event.set()
        
    def __del__ (self):
        """Assicura che il thread venga fermato quando l'istanza viene distrutta."""
        self.stop()
        
    def perform_garbage_collection(self):
        """Esegue una singola iterazione di pulizia, rimuovendo i file obsoleti."""
        
        with self.__lock:
            
            #verifico entry senza file fisico e rimuovo dal database per evitare accumulo di entry orfane
            all_files = self.__db_manager.get_all_files()
            entry_to_remove = []
            for file in all_files:
                file_path = os.path.join(self.__download_path, file.file_name)
                if not os.path.exists(file_path):
                    logging.warning(f"File fisico mancante per entry '{file.file_name}' - Rimuovendo entry dal database.")
                    entry_to_remove.append(file.file_name)
            
            for file_name in entry_to_remove:
                self.__db_manager.remove_file(file_name)
            
            #verifico i file più vecchi e rimuovo quelli che hanno superato il tempo di delazione
            oldest_file = self.__db_manager.get_oldest_file()
            while oldest_file is not None:
                
                # Calcola il tempo trascorso dalla creazione del file
                created_time = datetime.fromisoformat(oldest_file.created_at)
                elapsed_time_s = (datetime.now() - created_time).total_seconds()
                
                if elapsed_time_s >= self.__delated_time_s:
                    # Rimuovi il file dal filesystem
                    
                    pth_to_remove = os.path.join(self.__download_path, oldest_file.file_name)
                    
                    if os.path.exists(pth_to_remove):
                        try:
                            logging.info(f"Rimuovendo file obsoleto: {pth_to_remove}")
                            os.remove(pth_to_remove)
                        except OSError as e:
                            logging.error(f"Errore durante la rimozione del file '{pth_to_remove}': {e}")
                    
                    # Rimuovi la entry dal database
                    self.__db_manager.remove_file(oldest_file.file_name)
                else:
                    break  # Il file più vecchio non è ancora scaduto
                
                oldest_file = self.__db_manager.get_oldest_file()  # Controlla il prossimo file più vecchio
            
        
    def __run_cleanup_loop(self):
        """Loop che esegue periodicamente la pulizia dei file obsoleti."""
        while not self.__stop_event.is_set():
            self.perform_garbage_collection()
            self.__stop_event.wait(self.__scan_interval_s)



class DataBaseManager:
    
    __INSTANCE: Dict[str, 'DataBaseManager'] = {}
    
    def __new__(cls, db_path):
        if db_path not in cls.__INSTANCE:
            cls.__INSTANCE[db_path] = super(DataBaseManager, cls).__new__(cls)
        return cls.__INSTANCE[db_path]
    
    def __init__(self, db_path):
        # Controllo per evitare di re-inizializzare l'istanza singleton esistente
        if hasattr(self, 'db_path') and self.__db_path == db_path:
            return
        
        # Lock per la gestione della concorrenza (Thread Safety)
        self._lock = threading.Lock()
        self.initialized = True
        self.__db_path = db_path
        self.__conn = None
        self.__cursor = None
        
        # Connessione e inizializzazione automatica alla creazione
        self.connect()
        
    
    def connect(self):
        """Stabilisce la connessione al database e inizializza la tabella."""
        
        try:
            self.__conn = sqlite3.connect(self.__db_path, check_same_thread=False)
            self.__cursor = self.__conn.cursor()
            self.__init_db()
        except sqlite3.Error as e:
            logging.error(f"Errore di connessione al database: {e}")


    def __init_db(self):
        
        query = """
        CREATE TABLE IF NOT EXISTS files (
            name TEXT PRIMARY KEY,
            size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            scale REAL,
            filter INTEGER,
            source_url TEXT,
            status TEXT NOT NULL
        )
        """
        try:
            # Operazione di scrittura iniziale
            with self._lock:
                self.__cursor.execute(query)
                self.__conn.commit()
       
        except sqlite3.Error as e:
            logging.error(f"Errore durante l'inizializzazione della tabella: {e}")


    def insert_file(self, file_record: FileRecord) -> bool:
        """
        Inserisce una nuova entry nel database usando un oggetto FileRecord.
        Restituisce True se successo, False se fallisce.
        """
        
        query = """
        INSERT INTO files (name, size, created_at, scale, filter, source_url, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        data = (
            file_record.file_name, 
            file_record.size, 
            file_record.created_at, 
            file_record.scale, 
            file_record.filter,
            file_record.source_url,
            file_record.status.value  # Salviamo la stringa dell'Enum
        )

        with self._lock:
            # Controllo esistenza per evitare errori o sovrascritture silenziose
            if self._file_exists_unsafe(file_record.file_name):
                logging.warning(f"Warning: Il file '{file_record.file_name}' è già presente nel database.")
                return False

            try:
                self.__cursor.execute(query, data)
                self.__conn.commit()
                return True
            
            except sqlite3.IntegrityError:
                return False
            
            except sqlite3.Error as e:
                logging.error(f"Errore durante l'inserimento: {e}")
                return False

    def update_status(self, file_name: str, status: DownloadStatus) -> bool:
        """
        Metodo per aggiornare lo stato di un file durante il ciclo di vita.
        """
        query = "UPDATE files SET status = ? WHERE name = ?"
        with self._lock:
            try:
                self.__cursor.execute(query, (status.value, file_name))
                self.__conn.commit()
                return self.__cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"Errore aggiornamento stato: {e}")
                return False

    def get_oldest_file(self) -> Optional[FileRecord]:
        """
        Restituisce il file meno recente basandosi su 'created_at'.
        Restituisce un oggetto FileRecord o None se il DB è vuoto.
        """
        query = "SELECT name, size, created_at, scale, filter, source_url, status FROM files ORDER BY created_at ASC LIMIT 1"
        
        with self._lock:
            try:
                self.__cursor.execute(query)
                row = self.__cursor.fetchone()
                
                if row:
                    # Mappatura della tupla risultante alla Dataclass
                    return FileRecord(
                        file_name=row[0],
                        size=row[1],
                        created_at=row[2],
                        scale=row[3],
                        filter=row[4],
                        source_url=row[5],
                        status=DownloadStatus(row[6]) # Riconverte la stringa in Enum
                    )
                return None
            except sqlite3.Error as e:
                logging.error(f"Errore durante il recupero del file più vecchio: {e}")
                return None

    def file_exists(self, file_name: str) -> bool:
        """Verifica se un file esiste nel database (Thread-safe)."""
        with self._lock:
            return self._file_exists_unsafe(file_name)

    def _file_exists_unsafe(self, file_name: str) -> bool:
        """Metodo interno per verifica esistenza senza lock."""
        query = "SELECT 1 FROM files WHERE name = ? LIMIT 1"
        self.__cursor.execute(query, (file_name,))
        return self.__cursor.fetchone() is not None

    def remove_file(self, file_name: str) -> bool:
        """Rimuove una entry dal database (Thread-safe)."""
        query = "DELETE FROM files WHERE name = ?"
        
        with self._lock:
            try:
                self.__cursor.execute(query, (file_name,))
                self.__conn.commit()
                return self.__cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"Errore durante la rimozione: {e}")
                return False

    def get_file(self, file_name: str) -> Optional[FileRecord]:
        """Recupera un file specifico dal database (Thread-safe)."""
        query = "SELECT name, size, created_at, scale, filter, source_url, status FROM files WHERE name = ?"
        
        with self._lock:
            try:
                self.__cursor.execute(query, (file_name,))
                row = self.__cursor.fetchone()
                
                if row:
                    return FileRecord(
                        file_name=row[0],
                        size=row[1],
                        created_at=row[2],
                        scale=row[3],
                        filter=row[4],
                        source_url=row[5],
                        status=DownloadStatus(row[6]) # Riconverte la stringa in Enum
                    )
                return None
            except sqlite3.Error as e:
                logging.error(f"Errore durante il recupero del file '{file_name}': {e}")
                return None
    
    def get_all_files(self) -> List[FileRecord]:
        """Restituisce una lista di tutti i file nel database (Thread-safe)."""
        query = "SELECT name, size, created_at, scale, filter, source_url, status FROM files"
        
        with self._lock:
            try:
                self.__cursor.execute(query)
                rows = self.__cursor.fetchall()
                return [
                    FileRecord(
                        file_name=row[0],
                        size=row[1],
                        created_at=row[2],
                        scale=row[3],
                        filter=row[4],
                        source_url=row[5],
                        status=DownloadStatus(row[6]) # Riconverte la stringa in Enum
                    )
                    for row in rows
                ]
            except sqlite3.Error as e:
                logging.error(f"Errore durante il recupero dei file: {e}")
                return []

    def get_file_count(self) -> int:
        """Restituisce il numero totale di file (Thread-safe)."""
        query = "SELECT COUNT(*) FROM files"
        with self._lock:
            try:
                self.__cursor.execute(query)
                result = self.__cursor.fetchone()
                return result[0] if result else 0
            except sqlite3.Error as e:
                logging.error(f"Errore durante il conteggio: {e}")
                return 0

    def close(self):
        """Chiude la connessione al database."""
        with self._lock:
            if self.__conn:
                self.__conn.close()
                self.__conn = None
                self.__cursor = None
                