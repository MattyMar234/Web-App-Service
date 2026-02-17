import os
import time
import logging
import subprocess
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException 

from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from PIL import Image, ImageFilter
from PyPDF2 import PdfMerger
import requests

from global_vars import *

class MuseScoreScraper:
    def __init__(
        self, 
        headless: bool = True,
        use_remote: bool = False, 
        remote_url:  Optional[str] = None, 
        base_folder: Optional[str] = None,
        automatically_detect_version_and_download: bool = True,
    ):
        """
        Inizializza lo scraper.
        
        :param use_remote: Se True, tenta di connettersi a un Selenium Hub remoto.
        :param remote_url: L'URL del remote hub (es. http://selenium_hub:4444/wd/hub).
        :param base_folder: Cartella base per il salvataggio dei file. Se None, usa app.config['UPLOAD_FOLDER'].
        :param status_dict: Dizionario opzionale per aggiornare lo stato del progresso (es. per UI Flask).
        """
        
        self.__headless = headless
        self.use_remote = use_remote
        self.remote_url = remote_url
        self.base_folder = base_folder
        self.__automatically_detect_version_and_download = automatically_detect_version_and_download
        
        #self.driver = self._init_driver()


    @staticmethod
    def _detect_score_type_from_url_or_header(url, headers):
        # try to guess from url first
        if url is None:
            return None
        url_lower = url.lower()
        if url_lower.endswith('.svg'):
            return 'svg'
        if url_lower.endswith('.png') or url_lower.endswith('.jpg') or url_lower.endswith('.jpeg'):
            return 'png'
        # fallback to headers content-type
        ct = headers.get('content-type', '')
        if 'svg' in ct:
            return 'svg'
        if 'png' in ct or 'jpeg' in ct or 'jpg' in ct:
            return 'png'
        return None


    def get_chromium_version(self) -> str:
        """Determina la versione di Chromium / Chrome in base al sistema operativo."""
        
        import shutil
        import platform
        import re
        
        system = platform.system()
        logging.info(f"Rilevato sistema operativo: {system}")
        
        if system == "Windows":
            # Su Windows è più affidabile il registro
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Google\Chrome\BLBeacon"
                )
                version, _ = winreg.QueryValueEx(key, "version")
                logging.info(f"Versione Chromium/Chrome (registro): {version}")
                return version

            except Exception as e:
                logging.error("Impossibile leggere la versione di Chrome dal registro", exc_info=True)
                raise RuntimeError("Impossibile determinare la versione di Chromium su Windows") from e

        # Lista di possibili comandi per OS
        if system == "Linux":
            candidates = [
                "chromium",
                "chromium-browser",
                "google-chrome",
                "google-chrome-stable",
            ]

        elif system == "Darwin":  # macOS
            candidates = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        else:
            raise RuntimeError(f"Sistema operativo non supportato: {system}")

        # Tentativi via CLI
        for cmd in candidates:
            path = shutil.which(cmd) or cmd
            logging.debug(f"Tentativo comando: {path}")

            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    check=True
                )

                output = result.stdout.strip()
                logging.info(f"Output versione browser: {output}")

                # Estrazione versione (es. "Chromium 121.0.6167.85")
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", output)
                if match:
                    return match.group(1)

                return output  # fallback se il formato è strano

            except FileNotFoundError:
                logging.debug(f"Eseguibile non trovato: {cmd}")
                continue
            except subprocess.CalledProcessError as e:
                logging.warning(f"Comando trovato ma fallito: {cmd} ({e})")
                continue

        raise RuntimeError("Impossibile determinare la versione di Chromium/Chrome con i comandi disponibili.")

    def _init_driver(self):
        """Inizializza il driver webdriver (locale o remoto)."""
        chrome_options = Options()
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        
        if self.__headless:
            chrome_options.add_argument("--headless=new") # Decomentare se necessario
        
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        # Fix SSL
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--ignore-ssl-errors")
        chrome_options.add_argument("--allow-running-insecure-content")

        # Consigliato per scraping immagini
        #chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")

        if self.use_remote:
            if not self.remote_url:
                raise ValueError("URL remoto non specificato per il driver.")
            logging.info(f"Connessione al Selenium Hub remoto: {self.remote_url}")
            return webdriver.Remote(command_executor=self.remote_url, options=chrome_options)
       
        if self.__automatically_detect_version_and_download:
            return webdriver.Chrome(options=chrome_options)
            
        try:
            browser_version = self.get_chromium_version()
            logging.info(f"Versione di Chromium rilevata: {browser_version}")
            browser_version_major = browser_version.split(".")[0]
            service = ChromeService(ChromeDriverManager(driver_version=browser_version_major).install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
        
        except Exception as e:
            logging.warning(f"Fallito rilevamento versione automatico: {e}. Tentativo installazione generica.")
            # Fallback: lasciare che webdriver-manager scelga la versione migliore
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.execute_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """)
        return driver
    
    def __click_element(self, driver, element):
        """Tentativo robusto di click su un elemento, con fallback a JavaScript."""
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)

    def download_score(self, src: str, save_name: str, score_num: int, scale: int = 2, sharpen_count: int = 1) -> bool:
        
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        
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

        res_headers = r.headers
        score_type = self._detect_score_type_from_url_or_header(src, res_headers)
        if score_type is None:
            # try to inspect first bytes (rudimentale)
            content_start = r.content[:100].lower()
            if b'<svg' in content_start:
                score_type = 'svg'
            else:
                # fallback to png
                score_type = 'png'

        base_name = f"{save_name}_{score_num}"
        raw_path = os.path.join(DOWNLOAD_PATH, base_name + ('.svg' if score_type == 'svg' else '.png'))

        # write raw file
        with open(raw_path, 'wb') as f:
            f.write(r.content)

        # convert to pdf
        pdf_path = os.path.join(DOWNLOAD_PATH, base_name + '.pdf')
        try:
            if score_type == 'svg':
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
    
    def merge_pages(self, save_name: str, score_num: int) -> str:
        
        merger = PdfMerger()
        for i in range(0, score_num):
            path = os.path.join(DOWNLOAD_PATH, f"{save_name}_{i}.pdf")
            if os.path.isfile(path):
                merger.append(path)
            else:
                logging.warning(f"Pagina mancante: {path}")
        out_path = os.path.join(DOWNLOAD_PATH, f"{save_name}.pdf")
        merger.write(out_path)
        merger.close()
        # remove single pdfs
        for i in range(0, score_num):
            p = os.path.join(DOWNLOAD_PATH, f"{save_name}_{i}.pdf")
            if os.path.isfile(p):
                os.remove(p)
        logging.info(f"PDF finale creato: {out_path}")
        return out_path
    
    def scrape_musescore(self, url: str, task_id: str = None, step_pixels: int = 600, step_delay: float = 0.9, end_pause: float = 2.5) -> List[str]:
        driver = None
        
        try:
            driver = self._init_driver()
            driver.get(url)

            wait = WebDriverWait(driver, 20)
            found:bool = False
            attemps = 0

            # click cookie button if present
            while not found and attemps < 3:
                try:
                    agree_btn = wait.until(EC.element_to_be_clickable((By.ID, "accept-btn")))
                    time.sleep(1)
                    self.__click_element(driver, agree_btn)
                    found = True
                    break
                except TimeoutException:
                        logging.warning("Timeout durante il click del bottone cookie")
                except Exception as e:
                    logging.info(f"Nessun popup cookie trovato By.ID o timeout: {e}")

                try:
                    agree_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id='accept-btn']")))
                    time.sleep(1)
                    self.__click_element(driver, agree_btn)
                    found = True
                    break
                except TimeoutException:
                        logging.warning("Timeout durante il click del bottone cookie")
                except Exception as e:
                    logging.info(f"Nessun popup cookie trovato By.XPATH o timeout: {e}")

                time.sleep(1)

            if not found:
                logging.info("Nessun popup cookie trovato dopo 3 tentativi.")

            while True:
                
                driver.execute_script("""
                    document.querySelectorAll('img').forEach(img => {
                        if (img.dataset.src) {
                            img.src = img.dataset.src;
                        }
                        if (img.dataset.lazySrc) {
                            img.src = img.dataset.lazySrc;
                        }
                    });
                    """)
                
                
                time.sleep(0.5)

            # trova lo scroller
            try:
                scroller = wait.until(EC.presence_of_element_located((By.ID, "jmuse-scroller-component")))
            except Exception as e:
                logging.error(f"Contenitore non trovato: {e}")
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
                try:
                    imgs = scroller.find_elements(By.CSS_SELECTOR, 'img.MHaWn')
                    for im in imgs:
                        try:
                            src = im.get_attribute("src")
                            if src and (".png?" in src.lower() or ".png@0?" in src.lower() or ".svg?" in src.lower() or ".svg@0?" in src.lower() or ".jpg?" in src.lower()):
                                imgs_urls.add(src.replace("@0", "").split("?")[0])
                        except StaleElementReferenceException:
                            logging.debug("Rilevato un elemento stale durante l'iterazione, lo salto.")
                            continue
                except Exception as e:
                    logging.warning(f"Errore durante la ricerca delle immagini: {e}")

            
            logging.info(f"Inizio scorrimento progressivo per l'URL: {url}")
            total_height = height_of_scroller()
            cur_top = top_of_scroller()

            if total_height is None or total_height == 0:
                total_height = driver.execute_script("return document.body.scrollHeight")

            values = []
            max_values = 4
            blocked = False
            # Calcolo incremento progresso
            progress_step = 50 / (total_height / step_pixels) if total_height > 0 else 0
            current_progress = 20
            
            while (cur_top + step_pixels < total_height) and not blocked:
                next_pos = cur_top + step_pixels
                scroll_to(next_pos)
                values.append(cur_top)
                find_score_imgs()
                
                current_progress = min(70, current_progress + progress_step)
                
                if len(values) > max_values:
                    values.pop(0)
                
                if len(values) >= max_values:
                    # Controllo se lo scroll è bloccato (ultimi 4 valori identici)
                    for i in range(1, max_values):
                        if values[i] != values[i-1]:
                            break
                    else:
                        logging.warning("Scroll bloccato, interrompo la discesa.")
                        blocked = True
                        continue

                cur_top = top_of_scroller()
                total_height = height_of_scroller() or total_height
                time.sleep(step_delay)

            # Scroll finale e timeout
            scroll_to(total_height)
            time.sleep(end_pause)
            find_score_imgs()

            imgs_urls_list = list(imgs_urls)
            logging.info(f"Immagini trovate: {len(imgs_urls_list)}")
            
            
            # Ordinamento intelligente basato sul numero nello score
            imgs_urls_list.sort(key=lambda x: int(x.split("score_")[1].split(".")[0]))
            
            
            return imgs_urls_list
            
        except Exception as e:
            logging.error(f"Errore durante lo scraping: {str(e)}", exc_info=True)
            return []
        finally:
            if driver:
                driver.quit()
    
# --- Funzioni di Download e Elaborazione ---
def ensure_music_folder(folder: str):
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
    raw_path = os.path.join(DOWNLOAD_PATH, base_name + ('.svg' if scoreType == 'svg' else '.png'))

    # write raw file
    with open(raw_path, 'wb') as f:
        f.write(r.content)

    # convert to pdf
    pdf_path = os.path.join(DOWNLOAD_PATH, base_name + '.pdf')
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
  
    merger = PdfMerger()
    for i in range(0, score_num):
        path = os.path.join(DOWNLOAD_PATH, f"{saveName}_{i}.pdf")
        if os.path.isfile(path):
            merger.append(path)
        else:
            logging.warning(f"Pagina mancante: {path}")
    out_path = os.path.join(DOWNLOAD_PATH, f"{saveName}.pdf")
    merger.write(out_path)
    merger.close()
    
    # remove single pdfs
    for i in range(0, score_num):
        p = os.path.join(DOWNLOAD_PATH, f"{saveName}_{i}.pdf")
        if os.path.isfile(p):
            os.remove(p)
    logging.info(f"PDF finale creato: {out_path}")
    return out_path

# def scrape_musescore(url, task_id, step_pixels=600, step_delay=0.6, end_pause=2.5):
#     try:
#         download_status[task_id] = {"status": "starting", "progress": 0, "message": "Avvio del browser..."}
        
#         chrome_options = Options()
#         chrome_options.add_argument("--disable-gpu")
#         chrome_options.add_argument("--no-sandbox")
#         chrome_options.add_argument("--window-size=1920,1080")
#         #chrome_options.add_argument("--headless=new")
        
#         chrome_options.add_argument('--ignore-certificate-errors')
#         chrome_options.add_argument('--disable-blink-features=AutomationControlled')
#         chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
#         chrome_options.add_experimental_option('useAutomationExtension', False)

#         browser_version = get_chromium_version()
#         logging.info(f"Versione di Chromium rilevata: {browser_version}")

#         driver = webdriver.Chrome(
#             #service=ChromeService(ChromeDriverManager(version="114.0.5735.90").install()), 
#             service=ChromeService(ChromeDriverManager(version=browser_version).install()), 
#             options=chrome_options
#         )
#         # driver = webdriver.Remote(
#         #     command_executor='http://selenium_hub:4444/wd/hub',
#         #     options=chrome_options
#         # )
#         driver.get(url)

#         wait = WebDriverWait(driver, 20)

#         # click cookie button if present
#         try:
#             agree_btn = wait.until(EC.element_to_be_clickable((By.ID, "accept-btn")))
#             download_status[task_id] = {"status": "processing", "progress": 5, "message": "Gestione dei cookie..."}
#             try:
#                 agree_btn.click()
#             except Exception:
#                 driver.execute_script("arguments[0].click();", agree_btn)
#         except Exception as e:
#             logging.info(f"Nessun popup cookie trovato o timeout: {e}")

#         # trova lo scroller
#         try:
#             scroller = wait.until(EC.presence_of_element_located((By.ID, "jmuse-scroller-component")))
#             download_status[task_id] = {"status": "processing", "progress": 10, "message": "Contenitore dello spartito trovato."}
#         except Exception as e:
#             logging.error(f"Contenitore non trovato: {e}")
#             driver.quit()
#             download_status[task_id] = {"status": "error", "progress": 0, "message": f"Contenitore non trovato: {e}"}
#             return []

#         time.sleep(0.5)
#         try:
#             scroller.click()
#         except:
#             pass

#         def height_of_scroller():
#             return driver.execute_script("return arguments[0].scrollHeight", scroller)

#         def top_of_scroller():
#             return driver.execute_script("return arguments[0].scrollTop", scroller)

#         def scroll_to(pos):
#             driver.execute_script("arguments[0].scrollTop = %s" % pos, scroller)

#         imgs_urls = set()

#         def find_score_imgs():
#             # imgs = scroller.find_elements(By.CSS_SELECTOR, 'img.MHaWn')
#             # for im in imgs:
#             #     src = im.get_attribute("src")
#             #     if src and (".png?" in src.lower() or ".png@0?" in src.lower() or ".svg?" in src.lower() or ".svg@0?" in src.lower() or ".jpg?" in src.lower()):
#             #         imgs_urls.add(src.replace("@0", ""))
#             try:
#                 imgs = scroller.find_elements(By.CSS_SELECTOR, 'img.MHaWn')
#                 for im in imgs:
#                     try:
#                         src = im.get_attribute("src")
#                         if src and (".png?" in src.lower() or ".png@0?" in src.lower() or ".svg?" in src.lower() or ".svg@0?" in src.lower() or ".jpg?" in src.lower()):
#                             imgs_urls.add(src.replace("@0", ""))
#                     except StaleElementReferenceException:
#                         # L'elemento è diventato obsoleto mentre stavamo processandolo.
#                         # Non è un problema critico, lo ignoriamo e continuiamo.
#                         logging.debug("Rilevato un elemento stale durante l'iterazione, lo salto.")
#                         continue
#             except Exception as e:
#                 # Gestisce altri possibili errori, come il container che non è più presente
#                 logging.warning(f"Errore durante la ricerca delle immagini: {e}")

#         download_status[task_id] = {"status": "processing", "progress": 20, "message": "Ricerca delle immagini..."}
        
#         logging.info(f"Inizio scorrimento progressivo per l'URL: {url}")
#         total_height = height_of_scroller()
#         cur_top = top_of_scroller()

#         if total_height is None or total_height == 0:
#             total_height = driver.execute_script("return document.body.scrollHeight")

#         values = []
#         max = 4
#         blocked = False
#         progress_step = 50 / (total_height / step_pixels) if total_height > 0 else 0
#         current_progress = 20
        
#         while (cur_top + step_pixels < total_height) and not blocked:
#             next_pos = cur_top + step_pixels
#             scroll_to(next_pos)
#             values.append(cur_top)
#             find_score_imgs()
            
#             current_progress = min(70, current_progress + progress_step)
#             download_status[task_id] = {"status": "processing", "progress": current_progress, "message": f"Scansione in corso... {len(imgs_urls)} immagini trovate"}

#             if len(values) > max:
#                 values.pop(0)
            
#             if len(values) >= max:
#                 for i in range(1, max):
#                     if values[i] != values[i-1]:
#                         break
#                 else:
#                     logging.warning("Scroll bloccato, interrompo la discesa.")
#                     blocked = True
#                     continue

#             cur_top = top_of_scroller()
#             total_height = height_of_scroller() or total_height
#             time.sleep(step_delay)

#         scroll_to(total_height)
#         time.sleep(step_delay)
#         find_score_imgs()

#         imgs_urls_list = list(imgs_urls)
#         logging.info(f"Immagini trovate: {len(imgs_urls_list)}")
        
#         driver.quit()
        
#         download_status[task_id] = {"status": "processing", "progress": 75, "message": f"Ordinamento di {len(imgs_urls_list)} immagini..."}
        
#         imgs_urls_list.sort(key=lambda x: int(x.split("score_")[1].split(".")[0]))
        
#         download_status[task_id] = {"status": "processing", "progress": 80, "message": "Download delle immagini..."}
        
#         return imgs_urls_list
#     except Exception as e:
#         logging.error(f"Errore durante lo scraping: {str(e)}", exc_info=True)
#         download_status[task_id] = {"status": "error", "progress": 0, "message": f"Errore durante lo scraping: {str(e)}"}
#         return []
    
if __name__ == "__main__":
    # Test rapido
    test_url = "https://musescore.com/user/16006641/scores/4197961"
    task_id = "test_task"
    s = MuseScoreScraper(headless=False, use_remote=False, automatically_detect_version_and_download = False)
    s.scrape_musescore(test_url, task_id)
    
    print(s.get_chromium_version())