from flask import Flask, render_template, request, jsonify, send_file
import os
import threading
import time
from datetime import datetime
import uuid

# Importa le funzioni dal tuo script
from typing import Dict, List
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

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './downloads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Assicurati che la cartella di download esista
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Dizionario per tenere tracc dello stato dei processi
download_status = {}

def ensure_music_folder():
    folder = './downloads'
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
        print(f"[!] Errore request per {src}: {e}")
        return False

    if r.status_code != 200:
        print(f"[!] Risposta non OK ({r.status_code}) per {src}")
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
        print(f"[!] Errore nella conversione {raw_path} -> pdf: {e}")
        # keep raw file for debugging
        return False

    print(f"[+] Salvato: {pdf_path}")
    return True

def mergePages(saveName, score_num):
    folder = ensure_music_folder()
    merger = PdfMerger()
    for i in range(0, score_num):
        path = os.path.join(folder, f"{saveName}_{i}.pdf")
        if os.path.isfile(path):
            merger.append(path)
        else:
            print(f"[!] Pagina mancante: {path}")
    out_path = os.path.join(folder, f"{saveName}.pdf")
    merger.write(out_path)
    merger.close()
    # remove single pdfs
    for i in range(0, score_num):
        p = os.path.join(folder, f"{saveName}_{i}.pdf")
        if os.path.isfile(p):
            os.remove(p)
    print(f"[✓] PDF finale creato: {out_path}")
    return out_path

def scrape_musescore(url, task_id, step_pixels=600, step_delay=0.6, end_pause=2.5):
    try:
        download_status[task_id] = {"status": "starting", "progress": 0, "message": "Avvio del browser..."}
        
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--headless=new")  # opzionale

        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
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
            print("[!] Nessun popup cookie trovato o timeout:", e)

        # trova lo scroller
        try:
            scroller = wait.until(EC.presence_of_element_located((By.ID, "jmuse-scroller-component")))
            download_status[task_id] = {"status": "processing", "progress": 10, "message": "Contenitore dello spartito trovato."}
        except Exception as e:
            print("[!] Contenitore non trovato:", e)
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

        # Set locale per memorizzare gli URL delle immagini senza duplicati
        imgs_urls = set()

        def find_score_imgs():
            imgs = scroller.find_elements(By.CSS_SELECTOR, 'img.MHaWn')
            for im in imgs:
                src = im.get_attribute("src")
                if src and (".png?" in src.lower() or ".png@0?" in src.lower() or ".svg?" in src.lower() or ".svg@0?" in src.lower() or ".jpg?" in src.lower()):
                    imgs_urls.add(src.replace("@0", ""))  # rimuovi eventuale @0

        download_status[task_id] = {"status": "processing", "progress": 20, "message": "Ricerca delle immagini..."}
        
        print("[⏳] Inizio scorrimento progressivo verso il basso")
        total_height = height_of_scroller()
        cur_top = top_of_scroller()

        # se scroller vuoto o altezza 0, prova a leggere document height come fallback
        if total_height is None or total_height == 0:
            total_height = driver.execute_script("return document.body.scrollHeight")

        # scendi a passi da cur_top fino a total_height
        values = []
        max = 4
        blocked = False
        progress_step = 50 / (total_height / step_pixels)
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
                    print("[!] Scroll bloccato, interrompo la discesa.")
                    blocked = True
                    continue

            cur_top = top_of_scroller()
            total_height = height_of_scroller() or total_height
            time.sleep(step_delay)

        # assicurati di toccare il fondo
        scroll_to(total_height)
        time.sleep(step_delay)
        find_score_imgs()

        imgs_urls_list = list(imgs_urls)
        print(f"[✓] Immagini trovate: {len(imgs_urls_list)}")
        
        driver.quit()
        
        download_status[task_id] = {"status": "processing", "progress": 75, "message": f"Ordinamento di {len(imgs_urls_list)} immagini..."}
        
        # Ordina le immagini per numero
        imgs_urls_list.sort(key=lambda x: int(x.split("score_")[1].split(".")[0]))
        
        download_status[task_id] = {"status": "processing", "progress": 80, "message": "Download delle immagini..."}
        
        return imgs_urls_list
    except Exception as e:
        download_status[task_id] = {"status": "error", "progress": 0, "message": f"Errore durante lo scraping: {str(e)}"}
        return []

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
    
    # Genera un ID unico per questo task
    task_id = str(uuid.uuid4())
    
    # Avvia il processo in background
    def background_task():
        try:
            # Fase 1: Scrape delle immagini
            imgs = scrape_musescore(url, task_id)
            
            if not imgs:
                download_status[task_id] = {"status": "error", "progress": 0, "message": "Nessuna immagine trovata"}
                return
            
            # Fase 2: Download delle immagini
            download_status[task_id] = {"status": "processing", "progress": 80, "message": "Download delle immagini..."}
            
            save_name = f"spartito_{task_id[:8]}"
            for idx, img_url in enumerate(imgs):
                downloadScore(img_url, save_name, idx, scale, sharpen_count)
                # Aggiorna lo stato di progresso
                progress = 80 + (idx + 1) / len(imgs) * 15
                download_status[task_id] = {
                    "status": "processing", 
                    "progress": progress, 
                    "message": f"Download immagine {idx+1}/{len(imgs)}..."
                }
            
            # Fase 3: Unione dei PDF
            download_status[task_id] = {"status": "processing", "progress": 95, "message": "Unione delle pagine in PDF..."}
            pdf_path = mergePages(save_name, len(imgs))
            
            # Completato
            download_status[task_id] = {
                "status": "completed", 
                "progress": 100, 
                "message": "Download completato!",
                "download_url": f"/download_file/{task_id[:8]}"
            }
        except Exception as e:
            download_status[task_id] = {"status": "error", "progress": 0, "message": f"Errore: {str(e)}"}
    
    # Avvia il thread in background
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
            return jsonify({"error": "File non trovato"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)