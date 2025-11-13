import argparse
import logging
from flask import Flask, render_template, request, jsonify, send_file
import os
import threading
import time
from datetime import datetime
import uuid
import subprocess

# Importa le funzioni dal tuo script
from typing import Dict, Final, List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from PIL import Image, ImageFilter
from PyPDF2 import PdfMerger
import requests

DELATE_TINME_SECONDS: Final[int] = 1200  # 20 minute

# --- Configurazione del Logging ---
# Configura il logging per scrivere su console e su un file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        #logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# --- Configurazione dell'Applicazione Flask ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './downloads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Assicurati che la cartella di download esista
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Dizionario per tenere traccia dello stato dei processi
download_status = {}


# --- Funzioni di Pulizia Automatica ---
def cleanup_old_files_and_status():
    """Rimuove i file PDF più vecchi di un'ora e gli stati di download inattivi."""
    
    global DELATE_TINME_SECONDS
    
    logging.info("Avvio del processo di pulizia periodica...")
    now = time.time()
    
    # Soglia di 1 ora (3600 secondi)
    time_threshold = now - DELATE_TINME_SECONDS 

    # Pulizia dei file PDF
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(file_path):
                # Controlla se il file è più vecchio della soglia
                if os.path.getctime(file_path) < time_threshold:
                    os.remove(file_path)
                    logging.info(f"Rimosso file vecchio: {file_path}")
    except Exception as e:
        logging.error(f"Errore durante la pulizia dei file: {e}")

    # Pulizia degli stati di download per evitare memory leak
    statuses_to_remove = []
    for task_id, data in download_status.items():
        # Rimuovi gli stati completati o con errore da più di un'ora
        if data.get('status') in ['completed', 'error'] and os.path.getctime(file_path) < time_threshold:
             statuses_to_remove.append(task_id)
    
    for task_id in statuses_to_remove:
        del download_status[task_id]
        logging.info(f"Rimosso stato di download scaduto: {task_id}")

def get_chromium_version():
    """Esegue un comando di sistema per trovare la versione di Chromium."""
    try:
        # Esegui il comando sapendo che l'eseguibile è 'chromium'
        result = subprocess.run(
            ['chromium', '--version'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        version_output = result.stdout
        
    except subprocess.CalledProcessError as e:
        # Se il browser è stato installato, ma non è accessibile o non funziona
        raise RuntimeError("Chromium trovato, ma il comando '--version' ha fallito.") from e
    
    # Estrae la versione (il secondo elemento della stringa)
    version_string = version_output.split(' ')[1].strip()
    return version_string


# --- Funzioni di Download e Elaborazione ---
def ensure_music_folder():
    folder = app.config['UPLOAD_FOLDER']
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder

def detectScoreType_from_url_or_header(url, headers):
    # try to guess from url first
    if url is None:
        return None
    if url.lower().endswith('.svg'):
        return 'svg'
    if url.lower().endswith('.png') or url.lower().endswith('.jpg') or url.lower().endswith('.jpeg'):
        return 'png'
    # fallback to headers content-type
    ct = headers.get('content-type', '')
    if 'svg' in ct:
        return 'svg'
    if 'png' in ct or 'jpeg' in ct or 'jpg' in ct:
        return 'png'
    return None

def downloadScore(src, saveName, score_num, scale=2, sharpen_count=1):
    folder = ensure_music_folder()
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/118.0.5993.90 Safari/537.36",
        }

        r = requests.get(src, stream=True, timeout=20, headers=headers)
    except Exception as e:
        logging.error(f"Errore request per {src}: {e}")
        return False

    if r.status_code != 200:
        logging.warning(f"Risposta non OK ({r.status_code}) per {src}")
        return False

    headers = r.headers
    scoreType = detectScoreType_from_url_or_header(src, headers)
    if scoreType is None:
        # try to inspect first bytes (rudimentale)
        content_start = r.content[:100].lower()
        if b'<svg' in content_start:
            scoreType = 'svg'
        else:
            # fallback to png
            scoreType = 'png'

    base_name = f"{saveName}_{score_num}"
    raw_path = os.path.join(folder, base_name + ('.svg' if scoreType == 'svg' else '.png'))

    # write raw file
    with open(raw_path, 'wb') as f:
        f.write(r.content)

    # convert to pdf
    pdf_path = os.path.join(folder, base_name + '.pdf')
    try:
        if scoreType == 'svg':
            svg = svg2rlg(raw_path)
            renderPDF.drawToFile(svg, pdf_path)
            os.remove(raw_path)
        else:  # png / jpg
            im = Image.open(raw_path)
            im = im.convert('RGB')

            # Applica la scala di ridimensionamento
            w, h = im.size
            im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            
            # Applica il filtro sharpen per il numero di volte specificato
            for _ in range(sharpen_count):
                im = im.filter(ImageFilter.SHARPEN)
            
            im.save(pdf_path)
            im.close()
            os.remove(raw_path)
    except Exception as e:
        logging.error(f"Errore nella conversione {raw_path} -> pdf: {e}")
        # keep raw file for debugging
        return False

    logging.info(f"Salvato: {pdf_path}")
    return True

def mergePages(saveName, score_num):
    folder = ensure_music_folder()
    merger = PdfMerger()
    for i in range(0, score_num):
        path = os.path.join(folder, f"{saveName}_{i}.pdf")
        if os.path.isfile(path):
            merger.append(path)
        else:
            logging.warning(f"Pagina mancante: {path}")
    out_path = os.path.join(folder, f"{saveName}.pdf")
    merger.write(out_path)
    merger.close()
    # remove single pdfs
    for i in range(0, score_num):
        p = os.path.join(folder, f"{saveName}_{i}.pdf")
        if os.path.isfile(p):
            os.remove(p)
    logging.info(f"PDF finale creato: {out_path}")
    return out_path

def scrape_musescore(url, task_id, step_pixels=600, step_delay=0.6, end_pause=2.5):
    try:
        download_status[task_id] = {"status": "starting", "progress": 0, "message": "Avvio del browser..."}
        
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--headless=new")

        browser_version = get_chromium_version()
        logging.info(f"Versione di Chromium rilevata: {browser_version}")

        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager(version=browser_version).install()), 
            options=chrome_options
        )
        driver.get(url)

        wait = WebDriverWait(driver, 20)

        # click cookie button if present
        try:
            agree_btn = wait.until(EC.element_to_be_clickable((By.ID, "accept-btn")))
            download_status[task_id] = {"status": "processing", "progress": 5, "message": "Gestione dei cookie..."}
            try:
                agree_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", agree_btn)
        except Exception as e:
            logging.info(f"Nessun popup cookie trovato o timeout: {e}")

        # trova lo scroller
        try:
            scroller = wait.until(EC.presence_of_element_located((By.ID, "jmuse-scroller-component")))
            download_status[task_id] = {"status": "processing", "progress": 10, "message": "Contenitore dello spartito trovato."}
        except Exception as e:
            logging.error(f"Contenitore non trovato: {e}")
            driver.quit()
            download_status[task_id] = {"status": "error", "progress": 0, "message": f"Contenitore non trovato: {e}"}
            return []

        time.sleep(0.5)
        try:
            scroller.click()
        except:
            pass

        def height_of_scroller():
            return driver.execute_script("return arguments[0].scrollHeight", scroller)

        def top_of_scroller():
            return driver.execute_script("return arguments[0].scrollTop", scroller)

        def scroll_to(pos):
            driver.execute_script("arguments[0].scrollTop = %s" % pos, scroller)

        imgs_urls = set()

        def find_score_imgs():
            imgs = scroller.find_elements(By.CSS_SELECTOR, 'img.MHaWn')
            for im in imgs:
                src = im.get_attribute("src")
                if src and (".png?" in src.lower() or ".png@0?" in src.lower() or ".svg?" in src.lower() or ".svg@0?" in src.lower() or ".jpg?" in src.lower()):
                    imgs_urls.add(src.replace("@0", ""))

        download_status[task_id] = {"status": "processing", "progress": 20, "message": "Ricerca delle immagini..."}
        
        logging.info(f"Inizio scorrimento progressivo per l'URL: {url}")
        total_height = height_of_scroller()
        cur_top = top_of_scroller()

        if total_height is None or total_height == 0:
            total_height = driver.execute_script("return document.body.scrollHeight")

        values = []
        max = 4
        blocked = False
        progress_step = 50 / (total_height / step_pixels) if total_height > 0 else 0
        current_progress = 20
        
        while (cur_top + step_pixels < total_height) and not blocked:
            next_pos = cur_top + step_pixels
            scroll_to(next_pos)
            values.append(cur_top)
            find_score_imgs()
            
            current_progress = min(70, current_progress + progress_step)
            download_status[task_id] = {"status": "processing", "progress": current_progress, "message": f"Scansione in corso... {len(imgs_urls)} immagini trovate"}

            if len(values) > max:
                values.pop(0)
            
            if len(values) >= max:
                for i in range(1, max):
                    if values[i] != values[i-1]:
                        break
                else:
                    logging.warning("Scroll bloccato, interrompo la discesa.")
                    blocked = True
                    continue

            cur_top = top_of_scroller()
            total_height = height_of_scroller() or total_height
            time.sleep(step_delay)

        scroll_to(total_height)
        time.sleep(step_delay)
        find_score_imgs()

        imgs_urls_list = list(imgs_urls)
        logging.info(f"Immagini trovate: {len(imgs_urls_list)}")
        
        driver.quit()
        
        download_status[task_id] = {"status": "processing", "progress": 75, "message": f"Ordinamento di {len(imgs_urls_list)} immagini..."}
        
        imgs_urls_list.sort(key=lambda x: int(x.split("score_")[1].split(".")[0]))
        
        download_status[task_id] = {"status": "processing", "progress": 80, "message": "Download delle immagini..."}
        
        return imgs_urls_list
    except Exception as e:
        logging.error(f"Errore durante lo scraping: {str(e)}", exc_info=True)
        download_status[task_id] = {"status": "error", "progress": 0, "message": f"Errore durante lo scraping: {str(e)}"}
        return []

# --- Rotte Flask ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    scale = float(data.get('scale', 2))
    sharpen_count = int(data.get('sharpen_count', 1))
    
    if not url:
        return jsonify({"error": "URL è obbligatorio"}), 400
    
    task_id = str(uuid.uuid4())
    
    def background_task():
        try:
            imgs = scrape_musescore(url, task_id)
            
            if not imgs:
                download_status[task_id] = {"status": "error", "progress": 0, "message": "Nessuna immagine trovata"}
                return
            
            download_status[task_id] = {"status": "processing", "progress": 80, "message": "Download delle immagini..."}
            
            save_name = f"spartito_{task_id[:8]}"
            for idx, img_url in enumerate(imgs):
                downloadScore(img_url, save_name, idx, scale, sharpen_count)
                progress = 80 + (idx + 1) / len(imgs) * 15
                download_status[task_id] = {
                    "status": "processing", 
                    "progress": progress, 
                    "message": f"Download immagine {idx+1}/{len(imgs)}..."
                }
            
            download_status[task_id] = {"status": "processing", "progress": 95, "message": "Unione delle pagine in PDF..."}
            pdf_path = mergePages(save_name, len(imgs))
            
            download_status[task_id] = {
                "status": "completed", 
                "progress": 100, 
                "message": "Download completato!",
                "download_url": f"/download_file/{task_id[:8]}"
            }
        except Exception as e:
            logging.error(f"Errore nel task background: {str(e)}", exc_info=True)
            download_status[task_id] = {"status": "error", "progress": 0, "message": f"Errore: {str(e)}"}
    
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()
    
    return jsonify({"task_id": task_id})

@app.route('/status/<task_id>')
def status(task_id):
    if task_id in download_status:
        return jsonify(download_status[task_id])
    else:
        return jsonify({"status": "not_found"}), 404

@app.route('/download_file/<file_id>')
def download_file(file_id):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"spartito_{file_id}.pdf")
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=f"spartito_{file_id}.pdf")
        else:
            logging.warning(f"Tentativo di download per un file non esistente: {file_path}")
            return jsonify({"error": "File non trovato"}), 404
    except Exception as e:
        logging.error(f"Errore durante l'invio del file {file_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


# --- Avvio dell'Applicazione ---

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='Avvia il server Wake-on-LAN.')
    parser.add_argument('--host', type=str, default='0.0.0.0', help="Indirizzo IP su cui il server è in ascolto. Default: '0.0.0.0'")
    parser.add_argument('--port', type=int, default=8080, help='Porta su cui il server è in ascolto. Default: 8080')
    args = parser.parse_args()
    
    # Start server
    logging.info(f"Starting server on http://localhost:{args.port}")
    logging.info(f"Allowed IP: {args.host}")
    
    app.run(debug=True, host=args.host, port=args.port)