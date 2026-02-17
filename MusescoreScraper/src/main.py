import argparse
import logging
from typing import Dict, Final, List
from data_manager import DataBaseManager, GarbageCollector
from scraper_laywright import MuseScoreScraper
from server import FlaskServer
from global_vars import *


if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Avvia il server Wake-on-LAN.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Indirizzo IP su cui il server è in ascolto. Default: '0.0.0.0'")
    parser.add_argument('--port', type=int, default=8080, help='Porta su cui il server è in ascolto. Default: 8080')
    parser.add_argument('--log-level', type=str, default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], help="Livello di log (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: 'INFO'")
    parser.add_argument('--headless', type=bool, default=False, choices=[True, False], help="Esegui il browser in modalità headless (True o False). Default: False")
    args = parser.parse_args()
    
    # Configura il logging
    logging.basicConfig(level=getattr(logging, args.log_level), format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Start server
    logging.info(f"Starting server on http://localhost:{args.port}")
    logging.info(f"Allowed IP: {args.host}")
    
    scaraper = MuseScoreScraper(headless=args.headless)
    if not MuseScoreScraper.init_system_setup():
        logging.error("Playwright non è configurato correttamente. Assicurati di avere Playwright installato e configurato.")
        exit(1)
    
    db_manager = DataBaseManager(DB_FILE_PATH)
    server = FlaskServer(host=args.host, port=args.port, database=db_manager, scarper=scaraper)
    gc = GarbageCollector(
        db_manager, 
        on_update_func=lambda: server._broadcast_update(),
        download_path=DOWNLOAD_PATH, 
        scan_interval_s=FILE_SCAN_INTERVAL_SECONDS, 
        delated_time_s=DELATED_TIME_SECONDS
    )
    
    gc.perform_garbage_collection()  # Esegui una pulizia iniziale all'avvio
    
    all_files = db_manager.get_all_files()
    for file in all_files:
        logging.info(f"File in database: {file.file_name} - Status: {file.status} - Created At: {file.created_at}")
    
    gc.start()
    server.run()