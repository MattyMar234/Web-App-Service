# musescore_selenium_fixed.py
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
from PIL import Image
from PyPDF2 import PdfMerger

import os
import time
import requests
import shutil
import tkinter as tk


#<button mode="primary" id="accept-btn" size="large" class=" css-15vl1qi"><span>AGREE</span></button>

def ensure_music_folder():
    folder = './Music'
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

def downloadScore(src, saveName, score_num):
    folder = ensure_music_folder()
    try:
        r = requests.get(src, stream=True, timeout=20)
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

# ---------- main scraping logic ----------
def scrape_musescore(url,
                     step_pixels=600,      # passo di scroll per ogni step (px)
                     step_delay=0.6,       # pausa breve dopo ogni step (s)
                     end_pause=2.5):       # pausa lunga alla fine del ciclo (s)
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
        print("[✓] Pulsante cookie trovato, clicco...")
        try:
            agree_btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", agree_btn)
    except Exception as e:
        print("[!] Nessun popup cookie trovato o timeout:", e)

    # trova lo scroller
    try:
        scroller = wait.until(EC.presence_of_element_located((By.ID, "jmuse-scroller-component")))
        print("[✓] Contenitore dello spartito trovato.")
    except Exception as e:
        print("[!] Contenitore non trovato:", e)
        driver.quit()
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
                imgs_urls.add(src)

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
    while (cur_top + step_pixels < total_height) and not blocked:
        next_pos = cur_top + step_pixels
        scroll_to(next_pos)
        values.append(cur_top)
        find_score_imgs()

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
    
    for idx, img_url in enumerate(imgs_urls_list):
        print(f"{img_url}")

    driver.quit()
    return imgs_urls_list

imgs = scrape_musescore("https://musescore.com/user/14645141/scores/3311646",
                            step_pixels=500,
                            step_delay=0.8,
                            end_pause=2.5)

# Ora puoi usare la lista 'imgs' per scaricare le immagini
# Ad esempio:
for idx, img_url in enumerate(imgs):
    downloadScore(img_url, "spartito", idx)
mergePages("spartito", len(imgs))