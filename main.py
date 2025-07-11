import asyncio
from playwright.async_api import async_playwright
import os 
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()
AUTH = os.getenv('AUTH')
SBR_WS_CDP = f'wss://{AUTH}@brd.superproxy.io:9222'

# get the base URL to the REALTOR.ca site and the Location you want to scrape 
BASE_URL = 'https://www.zoopla.co.uk/'
LOCATION = 'London'

async def run(pw):
    print('Connecting to Browser API...')
    browser = await pw.chromium.connect_over_cdp(SBR_WS_CDP)
    try:
        page = await browser.new_page()
        print(f'Connected! Navigating to webpage: {BASE_URL}')
        await page.goto(BASE_URL, wait_until = 'load')

        # click on the Accept all to dismiss the cookies popup 
        try:
            await page.click("text='Accept all'", timeout = 5000)
            print("Clicked Accept all for Cookies")
        except:
            print("Accept all button not found or already dismissed")

        # fill in the location into the search bar and press enter 
        await page.fill('input[name="autosuggest-input"]', LOCATION)
        await page.wait_for_timeout(1000)  # wait for suggestions to show
        await page.keyboard.press("Enter")
        print("Waiting for search results...")
        
        # wait for the page to load after you search the location 
        await page.wait_for_selector('[data-testid="search-results-header-control"]', timeout=10000)

        # pull the div that contains the regular listings for the page
        content = await page.inner_html('div[data-testid="regular-listings"]')

        await page.screenshot(path = "page.png", full_page = True)
        print("Screenshot saved as 'page.png'")
        html = await page.content()
        print(html)
    finally:
        await browser.close()

async def main():
    async with async_playwright() as playwright:
        await run(playwright)

if __name__ == '__main__':
    asyncio.run(main())