import asyncio
from playwright.async_api import async_playwright

async def scrape_page(context, url):
    page = await context.new_page()
    await page.goto(url)
    title = await page.title()
    print(f"Sito: {url} - Titolo: {title}")
    await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        
        urls = [
            "https://www.google.com",
            "https://www.bing.com",
            "https://www.wikipedia.org"
        ]
        
        # Crea una lista di "task" da eseguire insieme
        tasks = [scrape_page(context, url) for url in urls]
        
        # Avvia tutto in parallelo
        await asyncio.gather(*tasks)
        
        await browser.close()

asyncio.run(main())