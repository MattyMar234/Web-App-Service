import os
import sys
import tempfile
import threading
import time
from typing import Callable, List
import uuid
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for
from flask_socketio import SocketIO, emit
import torch
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
import logging

from Transcriber import Transcription
from Transcriber import QueueItem, Transcriber
from Setting import *
from database import DatabaseManager

class WebServer:
    def __init__(self, host='0.0.0.0', port=12345, database: DatabaseManager = None):
        
        
        self._db = database
        self._modelName = 'small'
        self._items_per_page = 10
        
        #queue per l'elaborazione in background
        self._queueLock = threading.Lock()
        self._queue: List[QueueItem] = []
        self._maxQueue = 20
        
        # Avvia il thread di elaborazione
        self._processing_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._processing_thread.start()
        
        self._Transcriber = Transcriber()
        
        # # Memoria delle trascrizioni
        # self._transcriptions = {t.id: t for t in Transcription.load_transcriptions(TRANSCRIPTIONS_DIR)}
        
        # for filename in os.listdir(tempfile.gettempdir()):
        #     if os.path.isfile(os.path.join(tempfile.gettempdir(), filename)) and filename.endswith(tuple(ALLOWED_EXTENSIONS)):
        #         os.remove(os.path.join(tempfile.gettempdir(), filename))
            
        
        self._app: Flask = Flask(__name__)
        self._app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
        self._socketio = SocketIO(self._app, cors_allowed_origins="*")
        
        self._app.route('/', methods=['GET'])(self.index)
        self._app.route('/transcribe', methods=['POST'])(self.transcribe)
        self._app.route('/transcription', methods=['GET'])(self.get_transcriptions)
        #self._app.route('/transcription/<trans_id>', methods=['GET'])(self.get_transcription)
        self._app.route('/transcription/<trans_id>', methods=['PUT'])(self.rename_transcription)
        self._app.route('/transcription/<trans_id>', methods=['DELETE'])(self.delete_transcription)
        self._app.route('/transcription/<trans_id>/download', methods=['GET'])(self.download_transcription)
        self._app.route('/health', methods=['GET'])(self.health_check)
        self._app.route('/queue/<item_id>', methods=['DELETE'])(self.remove_from_queue)
        self._app.route('/queue/<item_id>/stop', methods=['DELETE'])(self.stop_and_remove_from_queue)
        
        # Eventi SocketIO
        self._socketio.on('connect')(self._handle_connect)
        self._socketio.on('disconnect')(self._handle_disconnect)
        self._socketio.on('get_queue_status')(self._send_queue_status)
        #self._socketio.on('get_transcriptions')(self._send_transcriptions)
        self._socketio.on('get_transcriptions')(self.handle_get_transcriptions)
        
        self._socketio.run(self._app, host=host, port=port, debug=True, allow_unsafe_werkzeug=True)
        logger.info("Server pronto con backend SQLite.")
        
    def index(self):
        return render_template(
            'index.html', 
            languages=SUPPORTED_LANGUAGES,
            models=SUPPORTED_MODELS,
            #transcriptions= [t.to_dict() for t in self._transcriptions.values()],
            transcriptions= [],
            gpu_available=torch.cuda.is_available()
        )
    
        
        
    #===================================================================================#
    # CONNECTION MOTHODS                                                                #
    #===================================================================================#
    
    
    def _handle_connect(self):
        logger.info("Client connesso")
        self._send_queue_status()
        self._send_transcriptions()
        
        
    def _handle_disconnect(self):
        logger.info("Client disconnesso")
    
    #===================================================================================#
    # QUEUE MOTHODS                                                                     #
    #===================================================================================#
    
    def _send_queue_status(self):
        with self._queueLock:
            queue_status = [item.to_dict() for item in self._queue]
        
        # Ottieni informazioni sul device corrente
        current_device = self._Transcriber.get_current_device()
        if current_device is None:
            current_device = "None"
        
        self._socketio.emit('queue_status', {
            'queue': queue_status,
            'transcriber_status': self._Transcriber.getCurrentStatus(),
            'current_file': self._Transcriber.getCurrentFile(),
            'current_device': current_device,
            'gpu_available': torch.cuda.is_available()
        })
    
    def remove_from_queue(self, item_id):
        logger.info(f"removing item {item_id} from queue")
        found: bool = False
        
        with self._queueLock:
            # Cerca l'elemento nella coda
            for i, item in enumerate(self._queue):
                if item.id == item_id and item.status == "pending":
                    
                    found = True
                    self._queue.pop(i)
                    try:  
                        os.remove(item.file_path) 
                    except:
                        pass

        if found:            
            # Notifica i client
            self._send_queue_status()
            print("updated")
            
            return jsonify({"success": True})
        return jsonify({"error": "Elemento non trovato nella coda o già in elaborazione"}), 404


    def stop_and_remove_from_queue(self, item_id):
        with self._queueLock:
            # Cerca l'elemento nella coda che è in fase di elaborazione
            item_to_stop = None
            item_index = -1
            for i, item in enumerate(self._queue):
                if item.id == item_id and item.status == "processing":
                    item_to_stop = item
                    item_index = i
                    break
            
        if item_to_stop:
            # Ferma l'elaborazione
            self._Transcriber.stop_transcription()
            
            # Rimuovi il file temporaneo se esiste
            with self._queueLock:
                self._queue.pop(item_index)
                try:
                    os.remove(item_to_stop.file_path)
                except:
                    pass
            
            self._send_queue_status()
            return jsonify({"success": True})
        
        return jsonify({"error": "Elemento non trovato o non in elaborazione"}), 404
    
    
    
        
    #===================================================================================#
    # transcriptions MOTHODS                                                            #
    #===================================================================================#
    
    def _get_paginated_transcriptions(self, page=1, sort_by='created_at', sort_order='desc'):
        """
        Restituisce le trascrizioni ordinate e paginate.
        """
        # items = list(self._transcriptions.values())
        
        # # Logica di ordinamento
        # reverse_sort = (sort_order == 'desc')
        
        # if sort_by == 'created_at':
        #     # Assicuriamoci che created_at sia confrontabile
        #     items.sort(key=lambda t: t.created_at if t.created_at else datetime.min, reverse=reverse_sort)
        # elif sort_by == 'name':
        #     items.sort(key=lambda t: t.display_name.lower() if t.display_name else "", reverse=reverse_sort)
        # else:
        #     # Default fallback
        #     items.sort(key=lambda t: t.created_at if t.created_at else datetime.min, reverse=True)

        # # Logica di paginazione
        # total_items = len(items)
        # total_pages = (total_items + self._items_per_page - 1) // self._items_per_page
        
        # # Calcolo indici di slice
        # start_index = (page - 1) * self._items_per_page
        # end_index = start_index + self._items_per_page
        
        # paginated_items = items[start_index:end_index]
        
        # return {
        #     'items': [t.to_dict() for t in paginated_items],
        #     'pagination': {
        #         'current_page': page,
        #         'total_pages': total_pages,
        #         'total_items': total_items,
        #         'items_per_page': self._items_per_page,
        #         'sort_by': sort_by,
        #         'sort_order': sort_order
        #     }
        # }
        return self._db.get_transcriptions_paginated(page, self._items_per_page, sort_by, sort_order)

        
    def handle_get_transcriptions(self, data=None):
        """
        Gestisce la richiesta SocketIO per le trascrizioni con parametri opzionali.
        Frontend può inviare: {page: 1, sort_by: 'name', sort_order: 'asc'}
        """
        
        page = 1
        sort_by = 'created_at'
        sort_order = 'desc'
        
        if data:
            page = data.get('page', 1)
            sort_by = data.get('sort_by', 'created_at')
            sort_order = data.get('sort_order', 'desc')
            
        result = self._get_paginated_transcriptions(page, sort_by, sort_order)
        self._socketio.emit('transcriptions_update', result)
    
    
    def _send_transcriptions(self):
        """
        Helper per inviare aggiornamenti generici (es. dopo eliminazione).
        Mantiene i filtri attuali? Per semplicità invia la pagina 1, 
        ma il frontend dovrebbe ri-richiedere con i filtri attivi.
        """
        # Nota: idealmente il frontend dovrebbe rifare la richiesta con i parametri salvati.
        # Qui inviamo un evento generico per notificare che la lista è cambiata.
        # Per semplicità, inviamo la pagina 1 default.
        result = self._get_paginated_transcriptions()
        self._socketio.emit('transcriptions_update', result)
        
        # transcriptions = [t.to_dict() for t in self._transcriptions.values()]
        # self._socketio.emit('transcriptions_update', {'transcriptions': transcriptions})
            
    
    def get_transcriptions(self):
        """
        Endpoint REST per ottenere le trascrizioni paginate e ordinate.
        Query Params: page, sort_by, sort_order
        """
        page = int(request.args.get('page', 1))
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        result = self._get_paginated_transcriptions(page, sort_by, sort_order)
        return jsonify(result)  
    
    
    # serve al frontend per il pulsante "Visualizza"
    def get_transcription(self, trans_id):
        # if trans_id in self._transcriptions:
        #     trans = self._transcriptions[trans_id]
            
        #     try:
        #         with open(trans.file_path, 'r', encoding='utf-8') as f:
        #             text = f.read()
        #         return jsonify({
        #             'id': trans_id,
        #             'filename': trans.display_name,
        #             'display_name': trans.display_name,
        #             'text': text,
        #             'language': trans.language,
        #             'model': trans.model,
        #             'created_at': trans.created_at,
        #             'status': trans.status
        #         })
        #     except Exception as e:
        #         return jsonify({"error": f"Errore lettura file: {str(e)}"}), 500
        # return jsonify({"error": "Trascrizione non trovata"}), 404
        trans = self._db.get_transcription(trans_id)
        if trans:
            return jsonify({
                'id': trans_id,
                'filename': trans['original_filename'], # Campo legacy
                'display_name': trans['display_name'] or trans['original_filename'],
                'text': trans['content'], # Il contenuto è salvato nel DB
                'language': trans['language'],
                'model': trans['model'],
                'created_at': trans['created_at'],
                'status': trans['status']
            })
        return jsonify({"error": "Trascrizione non trovata"}), 404

    def rename_transcription(self, trans_id):
        # data = request.get_json()
        # if not data or 'display_name' not in data:
        #     return jsonify({"error": "Nome non specificato"}), 400
        
        # if trans_id in self._transcriptions:
        #     self._transcriptions[trans_id].rename(data['display_name'])
        #     #self._send_transcriptions()
        #     return jsonify({"success": True, "display_name": data['display_name']})
        
        # return jsonify({"error": "Trascrizione non trovata"}), 404
        data = request.get_json()
        if not data or 'display_name' not in data:
            return jsonify({"error": "Nome non specificato"}), 400
        
        if self._db.update_name(trans_id, data['display_name']):
            # Non serve _send_transcriptions perché il frontend aggiorna via JS o richiesta successiva
            return jsonify({"success": True, "display_name": data['display_name']})
        
        return jsonify({"error": "Trascrizione non trovata"}), 404
    

    def delete_transcription(self, trans_id):
        # if trans_id in self._transcriptions:
        #     trans = self._transcriptions[trans_id]
        #     try:
        #         os.remove(trans.file_path)
        #     except:
        #         pass
        #     del self._transcriptions[trans_id]
        #     #self._send_transcriptions()
        #     return jsonify({"success": True})
        
        # return jsonify({"error": "Trascrizione non trovata"}), 404
        if self._db.delete_transcription(trans_id):
            return jsonify({"success": True})
        return jsonify({"error": "Trascrizione non trovata"}), 404

    def download_transcription(self, trans_id):
        
        # # print(self._transcriptions.keys())
        # # print(trans_id)
        
        # if trans_id in self._transcriptions:
        #     trans = self._transcriptions[trans_id]
        #     try:
        #         return send_file(
        #             trans.file_path,
        #             as_attachment=True,
        #             #download_name=f"{trans.file_path.split("/")[-1]}",#f"{trans.display_name}.txt",
        #             download_name=f"{trans.get_download_name()}",
        #             mimetype='text/plain'
        #         )
        #     except Exception as e:
        #         return jsonify({"error": f"Errore download: {str(e)}"}), 500
        
        # return jsonify({"error": "Trascrizione non trovata"}), 404 
        trans = self._db.get_transcription(trans_id)
        if trans:
            try:
                # Creiamo un file in memoria per il download
                file_content = trans['content']
                display_name = trans['display_name'] or trans['original_filename']
                
                # Utilizziamo send_file con BytesIO per non creare file temporanei
                from io import BytesIO
                buffer = BytesIO(file_content.encode('utf-8'))
                
                return send_file(
                    buffer,
                    as_attachment=True,
                    download_name=f"{display_name}.txt",
                    mimetype='text/plain'
                )
            except Exception as e:
                return jsonify({"error": f"Errore download: {str(e)}"}), 500
        
        return jsonify({"error": "Trascrizione non trovata"}), 404
    
    def allowed_file(self, filename) -> bool:
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS   

    
    #===================================================================================#
    # PROCESSING MOTHODS                                                                #
    #===================================================================================#
    
    def _process_queue(self):
        while True:
            
            # Attendi prima di controllare di nuovo la coda
            time.sleep(2)
            
            with self._queueLock:
                if self._queue:
                    item = self._queue[0]
                    
                    if item.status == "completed" or item.status == "error":
                        self._queue.pop(0)
                        self._queue.append(item)
                        continue
                    
                    item.status = "processing"
                else:
                    continue
            
            self._send_queue_status()
            
            if item is not None and isinstance(item, QueueItem):
                try:
                    # Processa il file
                    
                    # self._transcriptions[item.id] = self._Transcriber.transcribe(
                    #     self._queueLock, item, updateFunc=lambda: self._send_queue_status()
                    # )
                    transcription_obj = self._Transcriber.transcribe(
                        self._queueLock, item, updateFunc=lambda: self._send_queue_status()
                    )
                    
                    # 1. Leggi il contenuto del file generato
                    if os.path.exists(transcription_obj.file_path):
                        with open(transcription_obj.file_path, 'r', encoding='utf-8') as f:
                            text_content = f.read()
                            
                        # 2. Salva nel Database
                        success = self._db.add_transcription(
                            id=item.id,
                            display_name=item.filename, # Nome iniziale è il nome file
                            original_filename=item.filename,
                            language=item.language,
                            model=item.model_name,
                            temperature=item.temperature,
                            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            status="completed",
                            content=text_content
                        )
                        
                        # 3. Rimuovi il file fisico (ormai è nel DB)
                        try:
                            os.remove(transcription_obj.file_path)
                        except:
                            pass
                            
                        if not success:
                             logger.error(f"Impossibile salvare la trascrizione {item.id} nel DB (superamento limiti?)")
                             with self._queueLock:
                                item.status = "error"
                    
                    self._send_transcriptions()
                    
                    # Aggiorna lo stato della coda
                    with self._queueLock:
                        item.status = "completed"
                        item.progress = 100
                        
                    self._send_queue_status()
                    
                
                except Exception as e:
                    logger.error(f"Errore nell'elaborazione del file {item.filename}: {str(e)}")
                    with self._queueLock:
                        item.status = "error"
                        
                    self._send_queue_status()
                
                # Rimuovi il file temporaneo
                try:
                    os.remove(item.file_path)
                except:
                    pass
                
         
                self._send_queue_status()
            
            else:
                with self._queueLock:
                    item.status = "error"
                self._send_queue_status()
            
            threading.Thread(target=self.delayed_item_removal, args=(item, 60), daemon=True).start()
                


    def delayed_item_removal(self, item: QueueItem, delay: int = 5):
        time.sleep(delay)
        with self._queueLock:
            if item in self._queue:
                self._queue.remove(item)
        self._send_queue_status()

    def transcribe(self):
        # Verifica presenza file
        if 'files' not in request.files:
            return jsonify({"error": "Nessun file fornito"}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({"error": "Nessun file selezionato"}), 400



        # Parametri opzionali
        language = request.form.get('language', None)
        model_name = request.form.get('model', None)
        
        # Parametri base
        add_info = 'add_info' in request.form
        vad_filter = 'vad_filter' in request.form
        beam_size = int(request.form.get('beam_size', 5))
        
        # Parametri avanzati
        temperature = float(request.form.get('temperature', 0.0))
        best_of = int(request.form.get('best_of', 5))
        compression_ratio_threshold = float(request.form.get('compression_ratio_threshold', 2.4))
        no_repeat_ngram_size = int(request.form.get('no_repeat_ngram_size', 0))
        vad_min_silence = int(request.form.get('vad_min_silence', 1000))
        patience = request.form.get('patience', None)
        
        # Converti patience in float se presente
        if patience:
            patience = float(patience)
        
        # Crea i parametri VAD
        vad_parameters = {"min_silence_duration_ms": vad_min_silence}
        
        results = []
      

        # Processa i file in parallelo
        with self._queueLock:
            
            total = 0
            for q in self._queue:
                if q.status in ['pending', 'processing']:
                    total += 1
                    
            if total + len(files) > self._maxQueue:
                logger.error(f"Coda piena.")
                return jsonify({
                    "success": False,
                    "error": f"Coda piena. Massimo {self._maxQueue} file contemporaneamente."
                }), 429
                
            
            for file in files:
                if file and self.allowed_file(file.filename) and file.filename is not None:
                    filename = secure_filename(file.filename)
                    counter = 1
                    
                    temp_path = os.path.join(self._app.config['UPLOAD_FOLDER'], filename)

                    if os.path.exists(temp_path):
                        while True:
                            name, ext = os.path.splitext(filename)
                            new_filename = f"{name}({counter}){ext}"
                            temp_path = os.path.join(self._app.config['UPLOAD_FOLDER'], new_filename)
                            counter += 1
                            if not os.path.exists(temp_path):
                                filename = new_filename
                                break
                            
                        temp_path = os.path.join(self._app.config['UPLOAD_FOLDER'], filename)
                    

                    try:
                        file.save(temp_path)
                        logger.info(f"File salvato temporaneamente in {temp_path}")
                        #self._queue.append(temp_path)
                        
                        # Aggiungi alla coda
                        item_id = str(uuid.uuid4())
                        item = QueueItem(
                            id=item_id,
                            filename=filename,
                            file_path=temp_path,
                            language=language,
                            model_name=model_name,
                            add_info=add_info,
                            vad_filter=vad_filter,
                            beam_size=beam_size,
                            temperature=temperature,
                            best_of=best_of,
                            compression_ratio_threshold=compression_ratio_threshold,
                            no_repeat_ngram_size=no_repeat_ngram_size,
                            vad_parameters=vad_parameters,
                            patience=patience
                        )
                        
                        logger.info(f"\n{'='*80}\nAggiunto alla coda:\n {item}\n{'='*80}")
                        
                        self._queue.append(item)
                        results.append({
                            "id": item_id,
                            "filename": filename,
                            "success": True
                        })
                        
                    except Exception as e:
                        logger.error(f"Errore salvataggio file {filename}: {str(e)}")
                        results.append({
                            "filename": filename,
                            "success": False,
                            "error": f"Errore salvataggio: {str(e)}"
                        })
                
        # Notifica i client
        self._send_queue_status()  
                                   
        return jsonify({
            "success": True,
            "results": results
        })
        

    

    
        
    def health_check(self):
        return jsonify({"status": "healthy", "model": self._modelName})