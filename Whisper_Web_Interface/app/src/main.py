import os
import sys
import tempfile
import threading
import time
from typing import Callable, List
import uuid
import json
from datetime import datetime
import torch
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor
import logging

from data.database import DatabaseManager
from Setting import *
from server import WebServer


logger.info(f"torch version: {torch.__version__}")
logger.info(f"torch cuda version: {torch.version.cuda}")
logger.info(f"torch cuda available: {torch.cuda.is_available()}")
logger.info(f"torch backends cudnn version: {torch.backends.cudnn.version()}")


def main():
    
    database = DatabaseManager('transcriptions.db')
    wb = WebServer(database = database)


if __name__ == "__main__":
    main()