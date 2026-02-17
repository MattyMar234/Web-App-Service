import logging
import os
from typing import Final

download_status = {}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        #logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

DELATED_TIME_SECONDS: Final[int] = 55 #2400  # 40 minute
FILE_SCAN_INTERVAL_SECONDS: Final[int] = 60  # 1 minute
FILE_MAX_SIZE_BYTE: Final[int] = 16 * 1024 * 1024  # 16MB max file size
MAX_FILES_IN_FOLDER: Final[int] = 32  # Max number of files in the download folder before cleanup

CURRENT_DIR: Final[str] = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR: Final[str]    = os.path.dirname(CURRENT_DIR)

DOWNLOAD_PATH: Final[str] = os.path.join(ROOT_DIR, "downloads")
DB_FILE_PATH: Final[str] = os.path.join(ROOT_DIR, "database.db")


# Configurazione
PROXY_LIST_URL = "https://free-proxy-list.net/it/#"
HTTP_TEST_URL = "http://httpbin.org/ip"
HTTPS_TEST_URL = "https://www.google.com"

# Parametri di concorrenza
MAX_PING_CONCURRENCY = 140  # Ping è leggero, possiamo farne tanti
MAX_HTTP_CONCURRENCY = 80   # HTTP è pesante, limitiamo per evitare blocchi o saturazione banda
PING_TIMEOUT = 6            # Secondi timeout per il ping

# Intervallo per la cache dei proxy (10 minuti)
PROXY_CACHE_TIME_SECONDS: Final[int] = 600
PROXY_CACHE_FILE = os.path.join(ROOT_DIR, "proxy_cache.json")
