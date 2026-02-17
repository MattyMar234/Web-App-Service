import os
import random
import sys
import threading
import time
import logging
from typing import Dict, List, Optional, Tuple

# Import Playwright
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from PIL import Image, ImageFilter
from PyPDF2 import PdfMerger
import requests
import subprocess
import platform

from global_vars import *
from proxyFinder import get_valid_proxies, get_valid_proxies_async


class MuseScoreScraper:
  
    @staticmethod
    def init_system_setup() -> bool:
        logging.info("🔍 Verifica configurazione Playwright...")
        
        try:
            # 1. Tenta di ottenere la versione per verificare se è installato
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            logging.info(f"✅ Playwright è già installato: {result.stdout.strip()}")

        except (subprocess.CalledProcessError, FileNotFoundError):
            # 2. Se il comando fallisce, Playwright o i suoi binari mancano
            logging.warning("⚠️ Playwright non trovato o non configurato. Avvio installazione...")
            
            try:
                # Installa i browser necessari (chromium, firefox, webkit)
                # Nota: assume che il pacchetto 'playwright' sia già nel venv/sistema via pip
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "--with-deps"],
                    check=True
                )
                logging.info("🚀 Installazione completata con successo!")
            except subprocess.CalledProcessError as e:
                logging.error(f"❌ Errore durante l'installazione: {e}")
                return False

        return True
  
    def __init__(
        self, 
        headless: bool = True,
        use_remote: bool = False, 
        remote_url:  Optional[str] = None, 
        base_folder: Optional[str] = None,
        # Parametro mantenuto per compatibilità ma non più strettamente necessario 
        # poiché Playwright gestisce automaticamente le versioni dei browser.
        automatically_detect_version_and_download: bool = True, 
    ):
        """
        Inizializza lo scraper con Playwright.
        
        :param headless: Se True, esegue il browser in modalità headless.
        :param use_remote: Se True, tenta di connettersi a un endpoint CDP remoto.
        :param remote_url: L'URL dell'endpoint CDP (es. http://localhost:9222).
        :param base_folder: Cartella base per il salvataggio dei file.
        """
        self.__headless = headless
        self.use_remote = use_remote
        self.remote_url = remote_url
        self.base_folder = base_folder
        
        
            

    @staticmethod
    def _detect_score_type_from_url_or_header(url, headers):
        if url is None:
            return None
        url_lower = url.lower()
        if url_lower.endswith('.svg'):
            return 'svg'
        if url_lower.endswith('.png') or url_lower.endswith('.jpg') or url_lower.endswith('.jpeg'):
            return 'png'
        
        ct = headers.get('content-type', '')
        if 'svg' in ct:
            return 'svg'
        if 'png' in ct or 'jpeg' in ct or 'jpg' in ct:
            return 'png'
        return None


    async def download_FromMuseScore(self, context, browser, src: str, save_name: str, score_num: int, scale: int = 2, sharpen_count: int = 1) -> Tuple[bool, Optional[str]]:
        """
        Scarica e converte lo spartito usando il contesto di Playwright esistente.
        """
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        new_tab = None
        try:
            # 1. Crea un nuovo tab (page) nel contesto esistente
            new_tab = await context.new_page()
            
            # 2. Naviga all'URL dell'immagine
            # Usiamo wait_until="commit" o "domcontentloaded" per essere più veloci del "networkidle"
            response = await new_tab.goto(src, wait_until="domcontentloaded", timeout=25000)
            
            if not response or response.status != 200:
                logging.warning(f"Tab: Errore risposta {response.status if response else 'Null'} per {src}")
                await new_tab.close()
                return (False, None)

            # 3. Ottieni il buffer binario direttamente dal corpo della risposta del tab
            content = await response.body()
            res_headers = response.headers
            
            # Chiudiamo il tab immediatamente per risparmiare risorse
            await new_tab.close()
            new_tab = None

        except Exception as e:
            logging.error(f"Errore durante l'apertura del tab per {src}: {e}")
            if new_tab:
                await new_tab.close()
            return (False, None)

        # Riconoscimento tipo file
        score_type = self._detect_score_type_from_url_or_header(src, res_headers)
        if score_type is None:
            # Controllo rapido nel contenuto se l'header fallisce
            score_type = 'svg' if b'<svg' in content[:100].lower() else 'png'

        base_name = f"{save_name}_{score_num:03d}" # 001, 002... per ordinamento corretto
        ext = '.svg' if score_type == 'svg' else '.png'
        raw_path = os.path.join(DOWNLOAD_PATH, base_name + ext)
        pdf_path = os.path.join(DOWNLOAD_PATH, base_name + '.pdf')

        # Scrittura file temporaneo
        with open(raw_path, 'wb') as f:
            f.write(content)

        # Conversione in PDF
        try:
            if score_type == 'svg':
                drawing = svg2rlg(raw_path)
                renderPDF.drawToFile(drawing, pdf_path)
            else:
                with Image.open(raw_path) as im:
                    im = im.convert('RGB')
                    w, h = im.size
                    # Resize ad alta qualità
                    im = im.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
                    
                    for _ in range(sharpen_count):
                        im = im.filter(ImageFilter.SHARPEN)
                    
                    im.save(pdf_path, "PDF", resolution=100.0)
            
            # Pulizia: rimuove il file originale (PNG/SVG) dopo la conversione
            if os.path.exists(raw_path):
                os.remove(raw_path)
                
        except Exception as e:
            logging.error(f"Errore conversione {raw_path}: {e}")
            if os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except Exception as cleanup_e:
                    logging.error(f"Errore durante la pulizia del file {raw_path}: {cleanup_e}")
        
            return (False, None)

        logging.info(f"Completato: {pdf_path}")
        return (True, pdf_path)
        
    def merge_pages(self, save_name: str, files: List[str]) -> str:
        merger = PdfMerger()
        for f in files:
            if os.path.isfile(f):
                merger.append(f)
            else:
                logging.warning(f"Pagina mancante: {f}")
        out_path = os.path.join(DOWNLOAD_PATH, f"{save_name}.pdf")
        merger.write(out_path)
        merger.close()
        
        for f in files:
            if os.path.isfile(f):
                os.remove(f)
                
        logging.info(f"PDF finale creato: {out_path}")
        return out_path
    
    def scrape_musicSheet(self, url:str, save_name: str, scale: int = 2, sharpen_count: int = 1) -> Tuple[bool, Optional[str]]:
        try:
            result = asyncio.run(self.scrape_musescore(url, save_name, scale=scale, sharpen_count=sharpen_count))
            
            if not result or len(result) == 0:
                logging.warning("Nessuna immagine trovata durante lo scraping.")
                return (False, None)

            return (True, self.merge_pages(save_name, result))
            
        except Exception as e:
            logging.error(f"Errore durante lo scraping: {e}")
            return (False, None)
        
    
    async def scrape_musescore(self, url: str, save_name: str, scale: int = 2, sharpen_count: int = 1, step_pixels: int = 450, step_delay: float = 0.8, end_pause: float = 2.5) -> List[str]:
        """
        Esegue lo scraping utilizzando Playwright.
        """
        
        async def cloudfare_test_click1():
            await page.frame_locator("iframe").first.locator("input[type='checkbox']").click(timeout=3000)
            
        async def cloudfare_test_click2():
            await page.get_by_text("Stiamo verificando che tu non sia un robot").click(timeout=2000)    
            
        async def cloudfare_test_click3():
            await page.frame_locator("iframe").first.locator("label.cb-lb").click(timeout=2000)
        
        function_test_cick_cloudfare = [cloudfare_test_click1, cloudfare_test_click2, cloudfare_test_click3]
            
        
        imgs_urls = set()
        
        https_proxies, http_proxies = await get_valid_proxies_async()
        
        print(f"Proxy HTTPS validi: {len(https_proxies)}")
        print(f"Proxy HTTP validi: {len(http_proxies)}")
        
        available_proxies = https_proxies + http_proxies
        random.shuffle(available_proxies)
        
        if not available_proxies:
            logging.error("Nessun proxy valido disponibile.")
            return []

        last_exception = None

        # --- INIZIO CICLO SUI PROXY ---
        for proxy_info in available_proxies:
            proxy_ip = proxy_info['ip']
            proxy_port = proxy_info['port']
            proxy_settings = {
                "server": f"http://{proxy_ip}:{proxy_port}",
            }
            
            logging.info(f"Tentativo con Proxy: {proxy_ip}:{proxy_port}")
            
            # Variabili per il tracciamento delle immagini resettate ad ogni tentativo
            imgs_urls = set()
            
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=self.__headless,
                        proxy=proxy_settings,
                        args=[
                            "--disable-gpu",
                            "--no-sandbox",
                            #"--disable-blink-features=AutomationControlled",
                            #"--disable-features=IsolateOrigins,site-per-process"
                        ]
                    )
                    
                    context = await browser.new_context()
                    page = await context.new_page()
                    
                    # Imposta un timeout globale più alto per navigazioni lente con proxy
                    page.set_default_timeout(60000) 

                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        })
                    """)
                    
                    logging.info(f"Navigazione verso: {url}")
                    
                    # Tenta di caricare la pagina
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception as nav_err:
                        logging.warning(f"Timeout o errore di navigazione con proxy {proxy_ip}: {nav_err}")
                        raise nav_err # Solleva l'errore per passare al prossimo proxya

                    # --- Risoluzione Cloudflare / Robot Check ---
                    # Tentativo 1: Checkbox standard dentro iframe
                    
                    
                    laoded = False
                    clicked = False
                    for _ in range(5):
                        
                        if laoded:
                            break
    
                        for test_func in function_test_cick_cloudfare:
                            try:
                                await test_func()
                                clicked = True
                                break
                            except Exception:
                                continue
                        
                        if clicked:
                            break
                            
                        count = 0
                        while count <= 10:
                            try:
                                scroller = page.locator("#jmuse-scroller-component")
                                await scroller.wait_for(timeout=1000)
                                logging.info("Scroller trovato.")
                                laoded = True
                            except Exception:
                                logging.error(f"Scroller non trovato con proxy {proxy_ip}. Il sito potrebbe aver bloccato l'IP o la struttura è cambiata.")
                                raise Exception("Scroller non trovato")
                            count += 1
                    
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    except Exception as nav_err:
                        logging.warning(f"Timeout o errore di navigazione con proxy {proxy_ip}: {nav_err}")
                        raise nav_err # Solleva l'errore per passare al prossimo proxy


                    # --- Gestione Cookie ---
                    try:
                        accept_btn = page.locator("#accept-btn")
                        await accept_btn.click(timeout=8000)
                        logging.info("Cookie accettati.")
                    except Exception:
                        pass # Il banner potrebbe non esserci

                    # --- Trova lo scroller ---
                    try:
                        scroller = page.locator("#jmuse-scroller-component")
                        await scroller.wait_for(timeout=5000)
                        logging.info("Scroller trovato.")
                        
                        # Click per focus (opzionale)
                        try:
                            await scroller.click(timeout=2000)
                        except:
                            pass
                    except Exception:
                        logging.error(f"Scroller non trovato con proxy {proxy_ip}. Il sito potrebbe aver bloccato l'IP o la struttura è cambiata.")
                        raise Exception("Scroller non trovato")

                    # --- Funzioni Helper Scroll ---
                    async def get_scroll_state():
                        return await scroller.evaluate("""el => {
                            return {
                                height: el.scrollHeight,
                                top: el.scrollTop
                            };
                        }""")

                    async def do_scroll(pos):
                        await scroller.evaluate(f"el => el.scrollTop = {pos}")
                        await asyncio.sleep(0.5) # step_delay ottimizzato

                    async def find_score_imgs():
                        return await scroller.evaluate("""el => {
                            const imgs = el.querySelectorAll('img.MHaWn');
                            const sources = [];
                            imgs.forEach(im => {
                                let src = im.src;
                                if (src) {
                                    const srcLower = src.toLowerCase();
                                    if (srcLower.includes(".png?") || srcLower.includes(".png@0?") || 
                                        srcLower.includes(".svg?") || srcLower.includes(".svg@0?") || 
                                        srcLower.includes(".jpg?")) {
                                        let cleanSrc = src.replace("@0", "");
                                        sources.push(cleanSrc);
                                    }
                                }
                            });
                            return sources;
                        }""")

                    # --- Ciclo di Scrolling ---
                    state = await get_scroll_state()
                    total_height = state['height']
                    cur_top = state['top']
                    
                    # Variabili per il controllo blocco
                    stuck_counter = 0
                    last_top = -1

                    logging.info(f"Inizio scroll. Altezza iniziale: {total_height}")
                    
                    # Definiamo un limite massimo di iterazioni per evitare loop infiniti
                    max_iterations = 500 
                    iteration = 0

                    while cur_top + 300 < total_height and iteration < max_iterations:
                        iteration += 1
                        cur_top += 300
                        await do_scroll(cur_top)
                        
                        # Raccogli immagini
                        score_imgs = await find_score_imgs()
                        for src in score_imgs:
                            imgs_urls.add(src)
                        
                        # Controllo aggiornamento altezza e blocco
                        new_state = await get_scroll_state()
                        total_height = new_state['height']
                        
                        if new_state['top'] == last_top:
                            stuck_counter += 1
                        else:
                            stuck_counter = 0
                            last_top = new_state['top']
                            
                        if stuck_counter >= 4:
                            logging.warning("Scroll bloccato. Procedo al download.")
                            break
                        
                        await asyncio.sleep(0.2) # Piccola pausa per non sovraccaricare

                    # Scroll finale e raccolta ultima parte
                    await do_scroll(total_height)
                    final_imgs = await find_score_imgs()
                    for src in final_imgs:
                        imgs_urls.add(src)

                    # --- Download ---
                    imgs_urls_list = list(imgs_urls)
                    logging.info(f"Trovate {len(imgs_urls_list)} immagini con questo proxy.")

                    if not imgs_urls_list:
                        raise Exception("Nessuna immagine trovata nella pagina.")

                    try:
                        imgs_urls_list.sort(key=lambda x: int(''.join(filter(str.isdigit, x.split('/')[-1])) or 0))
                    except Exception:
                        pass

                    # Esecuzione download in parallelo
                    pages = [self.download_FromMuseScore(context, browser, url, save_name=save_name, score_num=i, scale=scale, sharpen_count=sharpen_count) for i, url in enumerate(imgs_urls_list)]
                    results_paths = await asyncio.gather(*pages)
                    
                    downlaod_statuses = [res[0] for res in results_paths]
                    downloaded_files = [res[1] for res in results_paths]

                    # Verifica download
                    if not all(downlaod_statuses):
                        logging.warning("Alcuni download sono falliti con questo proxy.")
                        # Pulizia file parziali
                        for idx, status in enumerate(downlaod_statuses):
                            if status and downloaded_files[idx] and os.path.exists(downloaded_files[idx]):
                                try:
                                    os.remove(downloaded_files[idx])
                                except:
                                    pass
                        raise Exception("Download incompleto.")
                    
                    # Se tutto ha successo, chiudi il browser e ritorna i risultati
                    await browser.close()
                    return [f for f in downloaded_files if f is not None]

            except Exception as e:
                logging.error(f"Proxy {proxy_ip} fallito: {e}")
                last_exception = e
                # Il ciclo continua al prossimo proxy
        
        # Se il ciclo finisce senza ritornare nulla, tutti i proxy sono falliti
        logging.error("Tutti i proxy disponibili hanno fallito.")
        raise Exception(f"Impossibile completare lo scraping. Ultimo errore: {last_exception}")

        




if __name__ == "__main__":
    # Test rapido
    test_url = "https://musescore.com/user/16006641/scores/4197961"
    task_id = "test_task"
    
    # Nota: Con Playwright non serve specificare automatic version download
    s = MuseScoreScraper(headless=False, use_remote=False)
    urls = s.scrape_musescore(test_url, task_id)
    
    print(f"Trovate {len(urls)} URL.")