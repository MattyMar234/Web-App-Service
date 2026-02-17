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

DELATED_TIME_SECONDS: Final[int] = 2400  # 40 minute
FILE_SCAN_INTERVAL_SECONDS: Final[int] = 60*5  # 5 minute
FILE_MAX_SIZE_BYTE: Final[int] = 16 * 1024 * 1024  # 16MB max file size
MAX_FILES_IN_FOLDER: Final[int] = 32  # Max number of files in the download folder before cleanup

CURRENT_DIR: Final[str] = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR: Final[str]    = os.path.dirname(CURRENT_DIR)

DOWNLOAD_PATH: Final[str] = os.path.join(ROOT_DIR, "downloads")
DB_FILE_PATH: Final[str] = os.path.join(ROOT_DIR, "database.db")


