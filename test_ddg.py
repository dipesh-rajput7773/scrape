import asyncio
import random
from playwright.async_api import async_playwright

async def test_ddg():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        query = 'site:linkedin.com/in "real estate agent" "Dubai"'
        url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
        print(f"Visiting {url}")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        # Check for results
        content = await page.content()
        if "linkedin.com/in/" in content:
            print("Found LinkedIn profiles on DDG!")
            # Extract some
            import re
            links = re.findall(r'linkedin\.com/in/[A-Za-z0-9_\-%.]+', content)
            for link in set(links)[:5]:
                print(f" - {link}")
        else:
            print("No LinkedIn profiles found on DDG.")
            print(content[:500])
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_ddg())
