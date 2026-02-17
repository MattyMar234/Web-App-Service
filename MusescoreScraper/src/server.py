import json
import queue
import re

from flask import Flask, Response, render_template, request, jsonify, send_file, stream_with_context
from typing import Any, Dict, Final, List, Tuple
import uuid
import os

from platform import system
from datetime import datetime
import threading

from scraper_laywright import MuseScoreScraper
from global_vars import *
from data_manager import DataBaseManager, DownloadStatus, FileRecord, GarbageCollector


# --- Gestione SSE (Server-Sent Events) ---
class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        q = queue.Queue(maxsize=5)
        self.listeners.append(q)
        return q

    def announce(self, message):
        # Rimuovi i listener disconnessi (dead listeners) e invia il messaggio
        to_remove = []
        for i, q in enumerate(self.listeners):
            try:
                q.put_nowait(message)
            except queue.Full:
                to_remove.append(i)
        
        # Pulizia listener pieni/disconnessi
        for i in reversed(to_remove):
            del self.listeners[i]

announcer = MessageAnnouncer()


class FlaskServer:
    def __init__(self, host: str, port: int, database: DataBaseManager, scarper: MuseScoreScraper):
        self.host = host
        self.port = port
        self.db_manager = database
        self.scraper = scarper
        
        # Configurazione Flask
        self.app = Flask(__name__)
        self.app.config['UPLOAD_FOLDER'] = DOWNLOAD_PATH
        self.app.config['MAX_CONTENT_LENGTH'] = FILE_MAX_SIZE_BYTE
        
        # Assicurati che la cartella di download esista
        os.makedirs(self.app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        
        # Stato dei download (in memoria per il tracking immediato)
        self.download_status: Dict[str, Dict] = {}
        
        """Registra le rotte Flask associandole ai metodi della classe."""
        self.app.add_url_rule('/', 'index', self.index)
        self.app.add_url_rule('/download', 'download', self.download, methods=['POST'])
        self.app.add_url_rule('/status/<task_id>', 'status', self.status)
        self.app.add_url_rule('/download_file/<file_id>', 'download_file', self.download_file)
        self.app.add_url_rule('/records', 'get_database_records', self.get_database_records)
        self.app.add_url_rule('/delete/<file_id>', 'delete_file', self.delete_file, methods=['POST'])
        self.app.add_url_rule('/stream', 'stream', self.stream) # Nuova rotta SSE
        
    # --- Metodi delle Rotte ---

    def index(self) -> Any:
        return render_template('index.html')
    
    def stream(self):
        """Endpoint SSE: invia aggiornamenti in tempo reale ai client."""
        def event_stream():
            q = announcer.listen()
            while True:
                msg = q.get()
                yield msg
        
        return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

    def download(self) -> Any:
        data = request.json
        assert isinstance(data, dict), "Dati della richiesta non validi"
        
        url = data.get('url')
        scale = float(data.get('scale', 2))
        sharpen_count = int(data.get('sharpen_count', 1))
        task_id = str(uuid.uuid4())
        
        if not url:
            return jsonify({"error": "URL è obbligatorio"}), 400
        
        #verifico se ho più url separati da virgola
        urls = [url.strip() for url in re.split(r'\s*,\s*', url) if url.strip()]
        
        threads = [threading.Thread(target=self._background_task, args=(url, task_id, scale, sharpen_count)) for url in urls]
        
        # Avvia il thread di background passando 'self' per accedere ai metodi e attributi
        for thread in threads:
            thread.daemon = True
            thread.start()
        
        self._broadcast_update()
        
        return jsonify({"task_id": task_id})

    def status(self, task_id):
        if task_id in self.download_status:
            return jsonify(self.download_status[task_id])
        else:
            return jsonify({"status": "not_found"}), 404

    def download_file(self, file_id):
        try:
            file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], f"spartito_{file_id}.pdf")
            
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True, download_name=f"spartito_{file_id}.pdf")
            else:
                logging.warning(f"Tentativo di download per un file non esistente: {file_path}")
                return jsonify({"error": "File non trovato"}), 404
        except Exception as e:
            logging.error(f"Errore durante l'invio del file {file_id}: {str(e)}")
            return jsonify({"error": str(e)}), 500

    def get_database_records(self) -> Tuple[Response, int]:
        """Restituisce al front-end lo stato di tutti i file presenti nel DB."""
        try:
            records = self.db_manager.get_all_files()
            return jsonify([
                {
                    "file_name": r.file_name,
                    "size": r.size,
                    "created_at": r.created_at,
                    "status": r.status.value,
                    "source_url": r.source_url,
                    "scale": r.scale,
                    "filter": r.filter
                } for r in records
            ]), 200
            
        except Exception as e:
            logging.error(f"Errore nel recupero record: {e}")
            return jsonify([]), 500
    
    
    def _broadcast_update(self):
        """Recupera i dati attuali e li invia a tutti i client connessi via SSE."""
        try:
            records = self.db_manager.get_all_files()
            data = [
                {
                    "file_name": r.file_name,
                    "size": r.size,
                    "created_at": r.created_at,
                    "status": r.status.value,
                    "source_url": r.source_url,
                    "scale": r.scale,
                    "filter": r.filter
                } for r in records
            ]
            # Formatta come messaggio SSE: "data: JSON\n\n"
            msg = f"data: {json.dumps(data)}\n\n"
            announcer.announce(msg)
        except Exception as e:
            logging.error(f"Errore durante il broadcast: {e}")
       
    def get_record(self, file_name: str) -> Tuple[Response, int]:
        """Recupera un record specifico dal database."""
        record = self.db_manager.get_file(file_name)
        if record:
            return jsonify({
                "path": record.file_name,
                "size": record.size,
                "created_at": record.created_at,
                "status": record.status.value,
                "source_url": record.source_url
            }), 200
        else:
            return jsonify({"error": "File non trovato"}), 404


    def delete_file(self, file_id) -> Tuple[Response, int]:
        """Elimina un file dal database e dal filesystem."""
        file_name = f"spartito_{file_id}.pdf"
        
        logging.info(f"Richiesta di eliminazione per file: {file_name}")
        
        try:
            # 1. Elimina dal Database
            status = self.db_manager.remove_file(file_name)
            
            if status:
                logging.info(f"File {file_name} eliminato dal database.")
            else:
                logging.warning(f"File {file_name} non trovato nel database durante l'eliminazione.")
                return jsonify({"error": "File non trovato nel database"}), 404
            
            self._broadcast_update()
            
            # 2. Elimina il file fisico
            file_path = os.path.join(self.app.config['UPLOAD_FOLDER'], file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.info(f"File fisico eliminato: {file_path}")
            
            return jsonify({"success": True, "message": "File eliminato correttamente"}), 200
        
        except Exception as e:
            logging.error(f"Errore durante l'eliminazione del file {file_id}: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    # --- Logica Background ---

    def _background_task(self, url: str, task_id: str, scale: float, sharpen_count: int):
        """Metodo eseguito nel thread separato per elaborare il download."""
        
        file_name = f"spartito_{task_id}"
        
        try:
            #realizzo la entry nel database
            record = FileRecord(
                file_name=file_name,
                size=0,  # Sarà aggiornato dopo la creazione del file
                created_at=datetime.now().isoformat(),
                scale=float(scale), # Cast a int come definito nella dataclass
                filter=sharpen_count,
                source_url=url,
                status=DownloadStatus.PROCESSING
            )
            
            
            self.db_manager.insert_file(record)
            result, file = self.scraper.scrape_musicSheet(url,file_name, scale=int(scale), sharpen_count=sharpen_count)
            
            if not result:
                raise Exception("Scraping fallito: nessun file generato.")
            
            # Registra il file creato nel database per il tracking e la pulizia automatica
            if not (file and os.path.exists(file)):
                raise Exception("File generato non trovato dopo lo scraping.")    
            
            record.file_name = file_name + ".pdf"
            record.size = os.path.getsize(file)
            record.status = DownloadStatus.COMPLETED
            self.db_manager.remove_file(file_name)  # Rimuove la vecchia entry se esiste
            self.db_manager.insert_file(record)

              
        except Exception as e:
            logging.error(f"Errore nel task background: {str(e)}", exc_info=True)
            self.db_manager.update_status(file_name, DownloadStatus.ERROR)
            
        finally:
            self._broadcast_update()
            
           
    def run(self):
        """Avvia il server Flask."""
        logging.info(f"Starting server on http://localhost:{self.port}")
        logging.info(f"Allowed IP: {self.host}")
        self.app.run(debug=True, host=self.host, port=self.port)