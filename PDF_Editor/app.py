# app.py
from server import PDFWebServer
from config import Config

if __name__ == '__main__':
    # Crea un'istanza del nostro server web
    app = PDFWebServer(__name__, Config)
    
    # Avvia l'applicazione
    app.run(debug=True, port=5000)