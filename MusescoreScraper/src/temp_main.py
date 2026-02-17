import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def advanced_example():
    # Configurazione lingue (puoi mettere "it-IT", "it" se sei in Italia)
    custom_languages = ("it-IT", "it")
    stealth = Stealth(
        navigator_languages_override=custom_languages,
        init_scripts_only=True
    )

    async with async_playwright() as p:
        # 1. 'headless=False' serve per VEDERE il browser aprirsi
        browser = await p.chromium.launch(headless=False)
        
        context = await browser.new_context()
        await stealth.apply_stealth_async(context)

        # 2. Creiamo una pagina
        page = await context.new_page()
        # 3. NAVIGHIAMO verso l'indirizzo desiderato
        print("Navigazione in corso...")
        await page.goto("https://www.wikipedia.org") # Inserisci qui l'URL che ti serve

        # 4. Opzionale: Aspetta che un elemento sia caricato per sicurezza
        await page.wait_for_load_state("networkidle")
        
        print(f"Sito caricato: {await page.title()}")

        # 5. IMPORTANTE: Questo trucco serve a non far chiudere il browser subito
        print("\nPremi INVIO nel terminale per chiudere il browser...")
        await asyncio.to_thread(input) 

        await browser.close()

if __name__ == "__main__":
    asyncio.run(advanced_example())