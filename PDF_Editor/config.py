# config.py
import os

# Percorso assoluto della cartella del progetto
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Chiave segreta per i sessioni di Flask
    SECRET_KEY = 'una-chiave-segreta-molto-sicura'
    
    # Cartella per i file uploadati temporanei
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    
    # Estensioni dei file consentiti
    ALLOWED_EXTENSIONS = {'pdf'}
    
    # Assicurati che la cartella di upload esista
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)