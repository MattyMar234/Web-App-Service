import asyncio
import json
import os
import platform
import threading
import time
import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple, Optional

from global_vars import *

_cached_http: List[Dict[str, str]] = []
_cached_https: List[Dict[str, str]] = []
_last_scan_time: float = 0

_scan_lock = threading.Lock()  # Lock per evitare scansioni concorrenti
_async_scan_lock = asyncio.Lock()

def get_os_ping_command(ip: str) -> List[str]:
    """
    Restituisce il comando di ping corretto per il sistema operativo corrente.
    Windows: ping -n 1 -w 2000 (1 pacchetto, 2000ms wait)
    Linux/Mac: ping -c 1 -W 2 (1 pacchetto, 2s wait)
    """
    system = platform.system().lower()
    
    if system == "windows":
        # -n count, -w timeout in milliseconds
        return ["ping", "-n", "1", "-w", str(PING_TIMEOUT * 1000), ip]
    else:
        # -c count, -W timeout in seconds (Linux/Mac standard)
        return ["ping", "-c", "1", "-W", str(PING_TIMEOUT), ip]

async def ping_ip(ip: str) -> bool:
    """
    Esegue un ping di sistema asincrono.
    Ritorna True se l'host è raggiungibile, False altrimenti.
    """
    cmd = get_os_ping_command(ip)
    
    try:
        # Esegue il processo senza bloccare l'event loop
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        # Attende che il processo termini
        returncode = await proc.wait()
        
        # Return code 0 indica successo (standard POSIX e Windows)
        return returncode == 0
        
    except Exception as e:
        # Errori di permesso o esecuzione comando
        # print(f"Errore ping per {ip}: {e}") # Decommentare per debug
        return False

async def get_proxies_async() -> List[Dict]:
    """Scarica la pagina e parsa i proxy in modo asincrono."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        try:
            response = await client.get(PROXY_LIST_URL)
            response.raise_for_status()
        except Exception as e:
            logging.error(f"❌ Errore download pagina proxy: {e}")
            return []

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_="table table-striped table-bordered")
    
    if table is None:
        logging.error("❌ Tabella non trovata.")
        return []

    tbody = table.find("tbody")
    rows = tbody.find_all("tr")
    proxies = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 8:
            continue

        proxies.append({
            "ip": cols[0].text.strip(),
            "port": cols[1].text.strip(),
            "code": cols[2].text.strip(),
            "country": cols[3].text.strip(),
            "anonymity": cols[4].text.strip(),
            "https": cols[6].text.strip(),
        })

    return proxies

def filter_proxies(proxies: List[Dict]) -> List[Dict]:
    """Filtra solo elite e anonymous."""
    return [
        p for p in proxies 
        if p["anonymity"] in ("elite proxy", "anonymous")
    ]

async def filter_by_ping(proxies: List[Dict]) -> List[Dict]:
    """
    Esegue il ping su tutti i proxy in parallelo e ritorna solo quelli vivi.
    """
    semaphore = asyncio.Semaphore(MAX_PING_CONCURRENCY)

    async def limited_ping(proxy):
        async with semaphore:
            is_alive = await ping_ip(proxy['ip'])
            return proxy if is_alive else None

    logging.info(f"🌐 Verifica Ping di {len(proxies)} IP...")
    
    tasks = [limited_ping(p) for p in proxies]
    results = await asyncio.gather(*tasks)
    
    alive_proxies = [p for p in results if p is not None]
    logging.info(f"✅ IP rispondenti al ping: {len(alive_proxies)} / {len(proxies)}")
    
    return alive_proxies

async def test_proxy_http(proxy_dict: Dict, timeout: float = 5.0) -> Optional[Dict]:
    """Testa singolo proxy su HTTP e HTTPS."""
    proxy_url = f"http://{proxy_dict['ip']}:{proxy_dict['port']}"
    
    result = {
        "proxy": proxy_dict,
        "proxy_url": proxy_url,
        "http_latency": None,
        "https_latency": None,
        "working_http": False,
        "working_https": False,
    }

    # Configuriamo il client per usare il proxy
    # verify=False evita errori SSL su proxy che manomettono i certificati (comune nei free proxy)
    async with httpx.AsyncClient(proxies={"all://": proxy_url}, timeout=timeout, verify=False) as client:
        # Test HTTP
        try:
            start = time.perf_counter()
            r = await client.get(HTTP_TEST_URL)
            if r.status_code == 200:
                result["http_latency"] = time.perf_counter() - start
                result["working_http"] = True
        except Exception:
            pass

        # Test HTTPS
        try:
            start = time.perf_counter()
            r = await client.get(HTTPS_TEST_URL)
            if r.status_code == 200:
                result["https_latency"] = time.perf_counter() - start
                result["working_https"] = True
        except Exception:
            pass

    if not result["working_http"] and not result["working_https"]:
        return None
        
    return result

async def test_all_proxies(proxies: List[Dict]) -> List[Dict]:
    """Testa tutti i proxy passati con concorrenza limitata."""
    semaphore = asyncio.Semaphore(MAX_HTTP_CONCURRENCY)

    async def sem_task(p):
        async with semaphore:
            return await test_proxy_http(p)

    logging.info(f"🚀 Test HTTP/HTTPS su {len(proxies)} proxy...")
    
    tasks = [sem_task(p) for p in proxies]
    results = await asyncio.gather(*tasks)
    
    return [r for r in results if r is not None]

def sort_and_print_results(results: List[Dict]):
    """Ordina e stampa i risultati."""
    if not results:
        logging.error("❌ Nessun proxy funzionante alla fine dei test.")
        return [], []

    https_proxies = sorted(
        [r for r in results if r["working_https"]], 
        key=lambda x: x["https_latency"]
    )
    http_proxies = sorted(
        [r for r in results if r["working_http"]], 
        key=lambda x: x["http_latency"]
    )

    logging.info(f"\n--- RISULTATI FINALI ---")
    logging.info(f"✅ Proxy HTTPS funzionanti: {len(https_proxies)}")
    logging.info(f"✅ Proxy HTTP funzionanti: {len(http_proxies)}")

    if https_proxies:
        best = https_proxies[0]
        logging.info(f"🥇 Miglior HTTPS: {best['proxy_url']} | Latenza: {best['https_latency']:.3f}s")
    
    if http_proxies:
        best = http_proxies[0]
        logging.info(f"🥇 Miglior HTTP:  {best['proxy_url']} | Latenza: {best['http_latency']:.3f}s")

    return https_proxies, http_proxies


def _save_cache_to_file():
    """Salva i dati correnti su file JSON."""
    data = {
        "last_scan_time": _last_scan_time,
        "https": _cached_https,
        "http": _cached_http
    }
    try:
        with open(PROXY_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"⚠️ Errore salvataggio cache su file: {e}")

def _load_cache_from_file():
    """Carica i dati dal file JSON se validi."""
    global _cached_http, _cached_https, _last_scan_time
    if os.path.exists(PROXY_CACHE_FILE):
        try:
            with open(PROXY_CACHE_FILE, "r") as f:
                data = json.load(f)
                _last_scan_time = data.get("last_scan_time", 0)
                _cached_https = data.get("https", [])
                _cached_http = data.get("http", [])
                logging.info("💾 Cache caricata da file.")
        except Exception as e:
            logging.error(f"⚠️ Errore caricamento cache: {e}")

# Inizializzazione immediata al caricamento del modulo
_load_cache_from_file()

async def get_valid_proxies_async() -> Tuple[List[Dict], List[Dict]]:
    global _cached_http, _cached_https, _last_scan_time
    
    async with _async_scan_lock:
        current_time = time.time()
        
        if current_time - _last_scan_time > PROXY_CACHE_TIME_SECONDS:
            logging.info(f"🔄 Cache scaduta o assente. Avvio scansione asincrona...")
            try:
                results = await _perform_full_scan()
                _cached_https = [{"ip": p["proxy"]["ip"], "port": p["proxy"]["port"]} for p in results if p["working_https"]]
                _cached_http = [{"ip": p["proxy"]["ip"], "port": p["proxy"]["port"]} for p in results if p["working_http"]]
                _last_scan_time = time.time()
                
                _save_cache_to_file() # Salvataggio su disco
                logging.info(f"✅ Scansione completata e salvata su file.")
            except Exception as e:
                logging.error(f"❌ Errore durante la scansione: {e}")
        else:
            logging.info(f"📦 Utilizzo cache valida caricata da file/memoria.")

        return _cached_https, _cached_http

def get_valid_proxies() -> Tuple[List[Dict], List[Dict]]:
    global _cached_http, _cached_https, _last_scan_time
    
    with _scan_lock:
        current_time = time.time()
        
        if current_time - _last_scan_time > PROXY_CACHE_TIME_SECONDS:
            logging.info(f"🔄 Cache scaduta o assente. Avvio scansione sincrona...")
            try:
                # Esegue asyncio.run per il bridge sincrono
                results = asyncio.run(_perform_full_scan())
                _cached_https = [{"ip": p["proxy"]["ip"], "port": p["proxy"]["port"]} for p in results if p["working_https"]]
                _cached_http = [{"ip": p["proxy"]["ip"], "port": p["proxy"]["port"]} for p in results if p["working_http"]]
                _last_scan_time = time.time()
                
                _save_cache_to_file() # Salvataggio su disco
                logging.info(f"✅ Scansione completata e salvata su file.")
            except Exception as e:
                logging.error(f"❌ Errore durante la scansione: {e}")
        else:
            logging.info(f"📦 Utilizzo cache valida caricata da file/memoria.")

        return _cached_https, _cached_http
    
    
async def _perform_full_scan():
    """Versione ridotta della logica main() per gestire la scansione interna."""
    all_proxies = await get_proxies_async()
    if not all_proxies:
        return []

    filtered = filter_proxies(all_proxies)
    
    # Eseguiamo il ping (opzionale, come da tuo codice originale)
    alive = await filter_by_ping(filtered)
    if not alive:
        alive = filtered

    # Test effettivo HTTP/HTTPS
    return await test_all_proxies(alive)


if __name__ == "__main__":
    
    print(get_valid_proxies())