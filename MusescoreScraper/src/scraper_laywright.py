import os
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

  
#verifica se playwright è stato installato
#verifico con "playwright --version" se è disponibile.
#altrimenti, se è installato ma non è stato eseguito "playwright install", allora i browser non saranno presenti e il codice fallirà al momento del lancio del browser. In questo caso, è necessario eseguire "playwright install" per scaricare i browser necessari.

if platform.system() == "Windows":
    status_command = "playwright --version"
    subprocess.run(status_command, shell=True)

elif platform.system() in ["Linux", "Darwin"]:
    status_command = "playwright --version"
    subprocess.run(status_command, shell=True)
     

class MuseScoreScraper:
    
      
    
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
        
        imgs_urls = set()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.__headless,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process"
                ]
            )
            context = await browser.new_context()

            page = await context.new_page()
            
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """)
            
            logging.info(f"Navigazione verso: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_load_state("networkidle")
        
        
            # --- Gestione Cookie ---
            
            for _ in range(3):  # Tentativi multipli per gestire eventuali ritardi o pop-up dinamici
                try:
                    # Cerca il bottone con timeout breve
                    accept_btn = page.locator("#accept-btn")
                    await accept_btn.click(timeout=5000)
                    logging.info("Cookie accettati.")
                    break  # Esce dal ciclo se il click ha successo
                except TimeoutError:
                    logging.info("Nessun popup cookie trovato o già accettati.")
                
                except Exception as e:
                    logging.info(f"Eccezione durante gestione cookie (ignorata): {e}")
                
                await asyncio.sleep(1)  # Piccola pausa prima di riprovare
                

            # --- Trova lo scroller ---
            try:
                scroller = page.locator("#jmuse-scroller-component")
                # Attende che lo scroller sia visibile e stabile
                await scroller.wait_for(timeout=4000)
                logging.info("Scroller trovato.")
                try:
                    await scroller.click(timeout=4000)
                except:
                    pass
            except TimeoutError:
                logging.error("Contenitore #jmuse-scroller-component non trovato.")
                return []

            # --- Definizione Funzioni Helper (Scope corretto) ---
            async def get_scroll_state():
                return await scroller.evaluate("""el => {
                    return {
                        height: el.scrollHeight,
                        top: el.scrollTop
                    };
                }""")

            async def do_scroll(pos):
                await scroller.evaluate(f"el => el.scrollTop = {pos}")
                await asyncio.sleep(step_delay)

            async def find_score_imgs():
                # Estrae gli src direttamente dal browser per evitare problemi di staleness
                # Restituisce una lista di stringhe
                return await scroller.evaluate("""el => {
                    const imgs = el.querySelectorAll('img.MHaWn');
                    const sources = [];
                    imgs.forEach(im => {
                        let src = im.src;
                        if (src) {
                            // Filtra per estensioni valide
                            const srcLower = src.toLowerCase();
                            if (srcLower.includes(".png?") || srcLower.includes(".png@0?") || 
                                srcLower.includes(".svg?") || srcLower.includes(".svg@0?") || 
                                srcLower.includes(".jpg?")) {
                                
                                // Pulizia URL
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

            # if total_height == 0:
            #     total_height = page.evaluate("document.body.scrollHeight")

            values: List[bool] = []
            max_stuck_counts: int = 4

            
            logging.info(f"Inizio scroll. Altezza stimata: {total_height}")
            
            while cur_top + step_pixels < total_height:
                cur_top += step_pixels
                await do_scroll(cur_top)
                
                logging.info(f"Scrolled to: {cur_top} / {total_height}")
                
                # Raccogli immagini
                score_imgs = await find_score_imgs()
                for src in score_imgs:
                    imgs_urls.add(src)
                
                
                # Controllo blocco (se il scrollTop non aumenta più)
                new_state = await get_scroll_state()
                if new_state['top'] == state['top']:
                    values.append(True)
                else:
                    values = []

                # Aggiorna stato
                state = new_state
                total_height = state['height']
                
                if len(values) >= max_stuck_counts:
                    logging.warning("Scroll bloccato, fine raggiungibile.")
                    break
                
            # Scroll finale
            await do_scroll(total_height)
            
            # Ultima raccolta
            final_imgs = await find_score_imgs()
            for src in final_imgs:
                imgs_urls.add(src)

            # --- Ordinamento e Risultato ---
            imgs_urls_list = list(imgs_urls)
            logging.info(f"Immagini totali trovate: {len(imgs_urls_list)}")
            
            try:
                # Prova a ordinare se il nome file contiene numeri (es. score_1.png)
                imgs_urls_list.sort(key=lambda x: int(''.join(filter(str.isdigit, x.split('/')[-1])) or 0))
            except Exception as e:
                logging.warning(f"Ordinamento personalizzato fallito: {e}")

            pages = [self.download_FromMuseScore(context, browser, url, save_name=save_name, score_num=i, scale=scale, sharpen_count=sharpen_count) for i,url in enumerate(imgs_urls_list)]
            results_paths = await asyncio.gather(*pages)
            
            downlaod_statuses = [res[0] for res in results_paths]
            downloaded_files = [res[1] for res in results_paths]
            
            for idx, url in enumerate(imgs_urls_list):
                logging.info(f"\nURL: {url} - Download {'Successo' if downlaod_statuses[idx] else 'Fallito'} \nFile: {downloaded_files[idx] if downlaod_statuses[idx] else 'N/A'}\n")
            
            if not all(downlaod_statuses):
                logging.warning("Alcuni download sono falliti.")
                for idx, status in enumerate(downlaod_statuses):
                    if status:
                        try:
                            path = downloaded_files[idx]
                            if path and os.path.exists(path):
                                os.remove(path)
                                logging.info(f"File rimosso a causa di download fallito: {path}")
                            logging.info(f"File rimosso a causa di download fallito: {downloaded_files[idx]}")
                        
                        except Exception as e:
                            logging.error(f"Errore durante la rimozione del file {downloaded_files[idx]}: {e}")
                return []
            
            return [f for f in downloaded_files if f is not None]

        




if __name__ == "__main__":
    # Test rapido
    test_url = "https://musescore.com/user/16006641/scores/4197961"
    task_id = "test_task"
    
    # Nota: Con Playwright non serve specificare automatic version download
    s = MuseScoreScraper(headless=False, use_remote=False)
    urls = s.scrape_musescore(test_url, task_id)
    
    print(f"Trovate {len(urls)} URL.")