import argparse
import logging
from typing import Dict, Final, List
from data_manager import DataBaseManager, GarbageCollector
from server import FlaskServer
from global_vars import *


if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Avvia il server Wake-on-LAN.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Indirizzo IP su cui il server è in ascolto. Default: '0.0.0.0'")
    parser.add_argument('--port', type=int, default=8080, help='Porta su cui il server è in ascolto. Default: 8080')
    args = parser.parse_args()
    
    # Start server
    logging.info(f"Starting server on http://localhost:{args.port}")
    logging.info(f"Allowed IP: {args.host}")
    
    
    db_manager = DataBaseManager(DB_FILE_PATH)
    gc = GarbageCollector(db_manager, download_path=DOWNLOAD_PATH, scan_interval_s=FILE_SCAN_INTERVAL_SECONDS, delated_time_s=DELATED_TIME_SECONDS)
    gc.start()
    
    gc.perform_garbage_collection()  # Esegui una pulizia iniziale all'avvio
    
    all_files = db_manager.get_all_files()
    for file in all_files:
        logging.info(f"File in database: {file.file_name} - Status: {file.status} - Created At: {file.created_at}")
    
    server = FlaskServer(host=args.host, port=args.port, database=db_manager)
    server.run()