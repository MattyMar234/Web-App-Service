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
        
        imgs_urls = set()
        
        https_proxies, http_proxies = await get_valid_proxies_async()
        
        print(f"Proxy HTTPS validi: {len(https_proxies)}")
        print(f"Proxy HTTP validi: {len(http_proxies)}")
        
        server = https_proxies[random.randint(0, len(https_proxies)-1)]
        
        available_proxies = https_proxies + http_proxies
        
        for p in available_proxies:
            logging.info(f"Proxy in utilizzo: {p['ip']}:{p['port']} (HTTPS: {p['https']}, Anonimato: {p['anonymity']})")
        
        
        proxy_settings = {
            "server": f"http://{server['ip']}:{server['port']}",
            # "username": "tua-username", # Opzionale
            # "password": "tua-password"  # Opzionale
        }
        
        print(f"Utilizzo del proxy: {proxy_settings['server']}")
        
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.__headless,
                proxy=proxy_settings,
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

            time.sleep(2)  # Pausa per assicurarsi che tutto sia stabile
        
            #berifica cloudflare button
            """
            <div class="main-wrapper .zxIB4 theme-light size-normal lang-it-it"><div id="content" aria-live="polite" aria-atomic="true" style="display: flex;"><div id="ehurV4" style="display: grid;"><div class="cb-c" role="alert" style="display: flex;"><label class="cb-lb"><input type="checkbox"><span class="cb-i"></span><span class="cb-lb-t">Stiamo verificando che tu non sia un robot</span></label></div></div><div id="verifying" class="cb-container" style="display: none; visibility: hidden;"><div class="verifying-container"><svg id="verifying-i" viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" class="unspun"><line x1="15" x2="15" y1="1.5" y2="5.5" class="circle"></line><line x1="24.5459" x2="24.5459" y1="5.45405" y2="10.45405" transform="rotate(45 24.5459 5.45405)" class="circle"></line><line x1="28.5" x2="28.5" y1="15" y2="20" transform="rotate(90 28.5 15)" class="circle"></line><line x1="24.5459" x2="24.5459" y1="24.546" y2="29.546" transform="rotate(135 24.5459 24.546)" class="circle"></line><line x1="15" x2="15" y1="28.5" y2="33.5" transform="rotate(180 15 28.5)" class="circle"></line><line x1="5.4541" x2="5.4541" y1="24.5459" y2="29.5459" transform="rotate(-135 5.4541 24.5459)" class="circle"></line><line x1="1.5" x2="1.5" y1="15" y2="20" transform="rotate(-90 1.5 15)" class="circle"></line><line x1="5.45408" x2="5.45408" y1="5.45404" y2="10.45404" transform="rotate(-45 5.45408 5.45404)" class="circle"></line></svg></div><div id="verifying-msg"><span id="verifying-text">Verifica in corso</span><br><div id="error-overrun" class="error-message-sm" style="display: none;"><span id="fr-overrun">Bloccato?</span><a href="#refresh" id="fr-overrun-link">Risoluzione dei problemi</a></div></div></div><div id="success" class="cb-container" role="alert" style="display: none;"><svg id="success-pre-i" viewBox="0 0 30 30"><g><line x1="15" x2="15" y1="7.5" y2="0"></line><line x1="20.303" x2="23.787" y1="9.697" y2="5.303"></line><line x1="22.5" x2="30" y1="15" y2="15"></line><line x1="20.303" x2="23.787" y1="20.303" y2="24.697"></line><line x1="15" x2="15" y1="22.5" y2="30"></line><line x1="9.697" x2="5.303" y1="20.303" y2="23.787"></line><line x1="7.5" x2="0" y1="15" y2="15"></line><line x1="9.697" x2="5.303" y1="9.697" y2="5.303"></line></g></svg><svg id="success-i" viewBox="0 0 52 52" aria-hidden="true" style="display: none;"><circle class="success-circle" cx="26" cy="26" r="25"></circle><path class="p1" d="m13,26l9.37,9l17.63,-18"></path></svg><span id="success-text">Operazione completata!</span></div><div id="fail" class="cb-container" role="alert" style="display: none;"><svg id="fail-i" viewBox="0 0 30 30" aria-hidden="true" fill="none"><circle class="failure-circle" cx="15" cy="15" r="15" fill="none"></circle><path class="failure-cross" d="M15.9288 16.2308H13.4273L13.073 7H16.2832L15.9288 16.2308ZM14.6781 19.1636C15.1853 19.1636 15.5918 19.3129 15.8976 19.6117C16.2103 19.9105 16.3666 20.2927 16.3666 20.7583C16.3666 21.2169 16.2103 21.5956 15.8976 21.8944C15.5918 22.1932 15.1853 22.3425 14.6781 22.3425C14.1778 22.3425 13.7713 22.1932 13.4586 21.8944C13.1529 21.5956 13 21.2169 13 20.7583C13 20.2997 13.1529 19.921 13.4586 19.6222C13.7713 19.3164 14.1778 19.1636 14.6781 19.1636Z"></path></svg><div id="failure-msg" class="cf-troubleshoot-wrapper"><p id="fail-text" class="error-message-sm">Verifica non riuscita</p><a id="fr-fail-troubleshoot-link" class="cf-troubleshoot" href="#refresh">Risoluzione dei problemi</a></div></div><div id="expired" class="cb-container" role="alert" style="display: none;"><svg id="expired-i" viewBox="0 0 30 30" aria-hidden="true"><circle class="expired-circle" cx="15" cy="15" r="15"></circle><path class="expired-p1" d="M15.3125 6H13V16.7184L19.2438 23.2108L20.9088 21.6094L15.3125 15.7877V6Z"></path></svg><div id="expiry-msg"><p id="expired-text" class="error-message-sm">Verifica scaduta</p><a href="#refresh" id="expired-refresh-link">Aggiorna</a></div></div><div id="timeout" class="cb-container" role="alert" style="display: none;"><svg id="timeout-i" viewBox="0 0 30 30" aria-hidden="true"><circle class="timeout-circle" cx="15" cy="15" r="15"></circle><path class="timeout-p1" d="M15.3125 6H13V16.7184L19.2438 23.2108L20.9088 21.6094L15.3125 15.7877V6Z"></path></svg><div id="timeout-msg"><p id="timeout-text" class="error-message-sm">Verifica scaduta</p><a href="#refresh" id="timeout-refresh-link">Aggiorna</a></div></div><div id="challenge-error" class="cb-container error-message-wrapper" role="alert" style="display: none;"><svg id="fail-small-i" viewBox="0 0 30 30" aria-hidden="true" fill="none"><circle class="failure-circle" cx="15" cy="15" r="15" fill="none"></circle><path class="failure-cross" d="M15.9288 16.2308H13.4273L13.073 7H16.2832L15.9288 16.2308ZM14.6781 19.1636C15.1853 19.1636 15.5918 19.3129 15.8976 19.6117C16.2103 19.9105 16.3666 20.2927 16.3666 20.7583C16.3666 21.2169 16.2103 21.5956 15.8976 21.8944C15.5918 22.1932 15.1853 22.3425 14.6781 22.3425C14.1778 22.3425 13.7713 22.1932 13.4586 21.8944C13.1529 21.5956 13 21.2169 13 20.7583C13 20.2997 13.1529 19.921 13.4586 19.6222C13.7713 19.3164 14.1778 19.1636 14.6781 19.1636Z"></path></svg><div id="error-msg" class="cf-troubleshoot-wrapper"><p id="challenge-error-text" class="error-message-sm"></p><a id="fr-troubleshoot-link" class="cf-troubleshoot" href="#refresh">Risoluzione dei problemi</a></div></div><div id="branding"><a class="cf-link" id="branding-link" target="_blank" href="https://www.cloudflare.com/products/turnstile/?utm_source=turnstile&amp;utm_campaign=widget" rel="noopener noreferrer"><svg role="img" aria-label="Cloudflare" id="logo" viewBox="0 0 73 25" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M61.8848 15.7841L62.0632 15.1578C62.2758 14.4126 62.1967 13.7239 61.8401 13.2178C61.5118 12.7517 60.9649 12.4773 60.3007 12.4453L47.7201 12.2836C47.6811 12.2829 47.6428 12.2728 47.6083 12.2542C47.5738 12.2356 47.5442 12.209 47.5217 12.1766C47.4996 12.1431 47.4856 12.1049 47.4807 12.0649C47.4758 12.025 47.4801 11.9844 47.4933 11.9465C47.5149 11.8839 47.5541 11.8291 47.6061 11.7888C47.658 11.7486 47.7204 11.7247 47.7856 11.72L60.4827 11.5566C61.9889 11.4864 63.6196 10.2462 64.1905 8.73372L64.9146 6.81361C64.9443 6.73242 64.951 6.64444 64.9341 6.55957C64.112 2.80652 60.8115 0 56.8652 0C53.2293 0 50.1421 2.38158 49.0347 5.69186C48.2864 5.12186 47.3535 4.85982 46.4228 4.95823C44.6785 5.13401 43.276 6.55928 43.1034 8.32979C43.059 8.77189 43.0915 9.21845 43.1992 9.64918C40.3497 9.73347 38.0645 12.1027 38.0645 15.0151C38.0649 15.2751 38.0838 15.5347 38.1212 15.7919C38.1294 15.8513 38.1584 15.9057 38.2029 15.9452C38.2474 15.9847 38.3044 16.0067 38.3635 16.0071L61.5894 16.0099C61.5916 16.0101 61.5938 16.0101 61.596 16.0099C61.6616 16.0088 61.7252 15.9862 61.7772 15.9455C61.8293 15.9049 61.867 15.8483 61.8848 15.7841Z" fill="#F6821F"></path><path d="M66.0758 6.95285C65.9592 6.95285 65.843 6.95582 65.7274 6.96177C65.7087 6.96312 65.6904 6.96719 65.6729 6.97385C65.6426 6.98437 65.6152 7.00219 65.5931 7.02579C65.5711 7.04939 65.555 7.07806 65.5462 7.10936L65.0515 8.84333C64.8389 9.58847 64.918 10.2766 65.2749 10.7827C65.6029 11.2494 66.1498 11.5233 66.814 11.5552L69.4959 11.7186C69.5336 11.7199 69.5705 11.73 69.6037 11.7483C69.6369 11.7666 69.6654 11.7925 69.687 11.8239C69.7092 11.8576 69.7234 11.896 69.7283 11.9363C69.7332 11.9765 69.7288 12.0173 69.7153 12.0555C69.6937 12.118 69.6546 12.1727 69.6028 12.2129C69.5509 12.2531 69.4887 12.2771 69.4236 12.2819L66.6371 12.4453C65.1241 12.5161 63.4937 13.7558 62.9233 15.2682L62.722 15.8022C62.7136 15.8245 62.7105 15.8486 62.713 15.8724C62.7155 15.8961 62.7236 15.9189 62.7365 15.9389C62.7495 15.9589 62.7669 15.9755 62.7874 15.9873C62.8079 15.9991 62.8309 16.0058 62.8544 16.0068C62.8569 16.0068 62.8592 16.0068 62.8618 16.0068H72.4502C72.506 16.0073 72.5604 15.9893 72.6051 15.9554C72.6498 15.9216 72.6823 15.8739 72.6977 15.8195C72.8677 15.2043 72.9535 14.5684 72.9529 13.9296C72.9517 10.0767 69.8732 6.95285 66.0758 6.95285Z" fill="#FBAD41"></path><path d="M8.11963 18.8904H9.75541V23.4254H12.6139V24.8798H8.11963V18.8904Z" class="logo-text"></path><path d="M14.3081 21.9023V21.8853C14.3081 20.1655 15.674 18.7704 17.4952 18.7704C19.3164 18.7704 20.6653 20.1482 20.6653 21.8681V21.8853C20.6653 23.6052 19.2991 24.9994 17.4785 24.9994C15.6578 24.9994 14.3081 23.6222 14.3081 21.9023ZM18.9958 21.9023V21.8853C18.9958 21.0222 18.3806 20.2679 17.4785 20.2679C16.5846 20.2679 15.9858 21.0038 15.9858 21.8681V21.8853C15.9858 22.7484 16.6013 23.5025 17.4952 23.5025C18.3973 23.5025 18.9958 22.7666 18.9958 21.9023Z" class="logo-text"></path><path d="M22.6674 22.253V18.8901H24.3284V22.2191C24.3284 23.0822 24.7584 23.4939 25.4159 23.4939C26.0733 23.4939 26.5034 23.1003 26.5034 22.2617V18.8901H28.1647V22.2093C28.1647 24.1432 27.0772 24.9899 25.3991 24.9899C23.7211 24.9899 22.6674 24.1268 22.6674 22.2522" class="logo-text"></path><path d="M30.668 18.8907H32.9445C35.0526 18.8907 36.275 20.1226 36.275 21.8508V21.8684C36.275 23.5963 35.0355 24.88 32.911 24.88H30.668V18.8907ZM32.97 23.4076C33.9483 23.4076 34.597 22.8609 34.597 21.8928V21.8759C34.597 20.9178 33.9483 20.3614 32.97 20.3614H32.3038V23.4082L32.97 23.4076Z" class="logo-text"></path><path d="M38.6525 18.8904H43.3738V20.3453H40.2883V21.3632H43.079V22.7407H40.2883V24.8798H38.6525V18.8904Z" class="logo-text"></path><path d="M45.65 18.8904H47.2858V23.4254H50.1443V24.8798H45.65V18.8904Z" class="logo-text"></path><path d="M54.4187 18.8475H55.9949L58.5079 24.8797H56.7541L56.3238 23.8101H54.047L53.6257 24.8797H51.9058L54.4187 18.8475ZM55.8518 22.5183L55.1941 20.8154L54.5278 22.5183H55.8518Z" class="logo-text"></path><path d="M60.6149 18.8901H63.4056C64.3083 18.8901 64.9317 19.13 65.328 19.5406C65.6742 19.883 65.8511 20.3462 65.8511 20.9357V20.9526C65.8511 21.8678 65.3691 22.4754 64.6369 22.7919L66.045 24.88H64.1558L62.9671 23.0658H62.2507V24.88H60.6149V18.8901ZM63.3299 21.7654C63.8864 21.7654 64.2071 21.4915 64.2071 21.0551V21.0381C64.2071 20.5674 63.8697 20.328 63.3211 20.328H62.2507V21.7665L63.3299 21.7654Z" class="logo-text"></path><path d="M68.2112 18.8904H72.9578V20.3024H69.8302V21.209H72.6632V22.5183H69.8302V23.4683H73V24.8798H68.2112V18.8904Z" class="logo-text"></path><path d="M4.53824 22.6043C4.30918 23.13 3.82723 23.5022 3.18681 23.5022C2.29265 23.5022 1.67746 22.7493 1.67746 21.8851V21.8678C1.67746 21.0047 2.27593 20.2676 3.1698 20.2676C3.84367 20.2676 4.35681 20.6882 4.5734 21.2605H6.29764C6.02151 19.8349 4.78716 18.7707 3.18681 18.7707C1.36533 18.7707 0 20.1666 0 21.8851V21.9021C0 23.6219 1.3486 25 3.1698 25C4.72762 25 5.94525 23.9764 6.26645 22.6046L4.53824 22.6043Z" class="logo-text"></path></svg></a><div id="terms"><a id="privacy-link" target="_blank" rel="noopener noreferrer" href="https://www.cloudflare.com/it-it/privacypolicy/">Privacy</a><span class="link-spacer"> • </span><a id="help-link" target="_blank" rel="noopener noreferrer" href="/cdn-cgi/challenge-platform/help">Guida</a></div></div></div></div>
            """
            
            try:
                await page.get_by_text("Stiamo verificando che tu non sia un robot").click()
            except:
                pass
            
            try:
                frame = page.frame_locator("iframe")
                await frame.get_by_role("checkbox").click()
            except:
                pass
            
            try:
                frame = page.frame_locator("iframe")
                await frame.locator("label.cb-lb").click()
            except:
                pass
            
            try:
                await page.locator("input[type='checkbox']").click()
            except:
                pass
            
            time.sleep(3)  # Pausa per eventuali verifiche o caricamenti dinamici dopo il click
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