# download_musescore.py
from pathlib import Path
#from musescore import MuseScraper
import musescore

# Lista di URL MuseScore (esempi). Sostituisci con gli URL reali degli spartiti che puoi scaricare.
URLS = [
    "https://musescore.com/user/123456/scores/654321",
    
    # aggiungi altri URL se vuoi
]

#https://musescore.com/user/14645141/scores/3311646

musescore.download(user = 14645141, score = 3311646, dpi = 40)

# OUTPUT_DIR = Path("musescore_pdfs")
# OUTPUT_DIR.mkdir(exist_ok=True)

# def url_to_filename(url: str) -> str:
#     # genera un nome file semplice basato sull'URL
#     safe = url.rstrip("/").replace("https://", "").replace("/", "_")
#     return safe + ".pdf"

# def main():
#     # MuseScraper viene usato come context manager; si occupa dell'avvio/chiusura del browser interno
#     with MuseScraper() as ms:
#         for url in URLS:
#             try:
#                 out_name = url_to_filename(url)
#                 out_path = OUTPUT_DIR / out_name
#                 print(f"[+] Scaricando {url} -> {out_path}")
#                 # to_pdf accetta l'URL e salva il PDF (vedi doc ufficiale)
#                 ms.to_pdf(url, str(out_path))
#                 print(f"[✓] Salvato: {out_path}")
#             except Exception as e:
#                 print(f"[!] Errore scaricando {url}: {e}")

# if __name__ == "__main__":
#     main()
