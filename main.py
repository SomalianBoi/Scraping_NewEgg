import asyncio
import csv
import logging
import os
import random
from urllib.parse import urljoin
import requests
from playwright.async_api import async_playwright, Error
from selectolax.parser import HTMLParser
import capsolver
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

BRIGHTDATA_USERNAME = os.getenv("BRIGHTDATA_USERNAME")
BRIGHTDATA_PASSWORD = os.getenv("BRIGHTDATA_PASSWORD")
BRIGHTDATA_PROXY_URL = os.getenv("BRIGHTDATA_PROXY_URL")


CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY")


USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15'
]


SEARCH_URLS = [
    'https://www.newegg.com/p/pl?N=100006662&cm_sp=shop-all-products-_-categroy-_-GPU-Video-Graphics-Device-bottom&PageSize=36',
    'https://www.newegg.com/p/pl?N=100006676&cm_sp=shop-all-products-_-categroy-_-CPU-Processor-bottom&PageSize=36',
    'https://www.newegg.com/p/pl?N=100006654&cm_sp=shop-all-products-_-categroy-_-Motherboard-bottom&PageSize=36',
    'https://www.newegg.com/p/pl?N=100006644&cm_sp=shop-all-products-_-categroy-_-Computer-Case-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100006656&cm_sp=shop-all-products-_-categroy-_-Power-Supply-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100006670&cm_sp=shop-all-products-_-categroy-_-Hard-Drive-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100006648&cm_sp=shop-all-products-_-categroy-_-Fans-PC-Cooling-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101702291&cm_sp=shop-all-products-_-categroy-_-Monitor-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101714292&cm_sp=shop-all-products-_-tab-_-Server-Components-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101702348&cm_sp=shop-all-products-_-categroy-_-Keyboard-Mouse-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100161628&cm_sp=shop-all-products-_-categroy-_-Printers-Scanners-Supplies-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101702324&cm_sp=shop-all-products-_-categroy-_-Headset-Speaker-Soundcard-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101702340&cm_sp=shop-all-products-_-categroy-_-Printer-Ink-Toner-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100158092&cm_sp=shop-all-products-_-categroy-_-Wireless-Networking-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100158091&cm_sp=shop-all-products-_-categroy-_-Wired-Networking-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101737310&cm_sp=shop-all-products-_-categroy-_-Networking-Accessories-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100021797&cm_sp=shop-all-products-_-categroy-_-Xbox-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100017489&cm_sp=shop-all-products-_-categroy-_-Laptop-Notebook-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=100157991&cm_sp=shop-all-products-_-categroy-_-Gaming-Laptop-top&PageSize=36',
    'https://www.newegg.com/p/pl?N=101708998&cm_sp=shop-all-products-_-categroy-_-Cooking-Appliances-top&PageSize=36',
]


async def fetch_brightdata_page(url, max_retries=3):
    proxies = {
        'http': f'http://{BRIGHTDATA_USERNAME}:{BRIGHTDATA_PASSWORD}@{BRIGHTDATA_PROXY_URL}',
        'https': f'https://{BRIGHTDATA_USERNAME}:{BRIGHTDATA_PASSWORD}@{BRIGHTDATA_PROXY_URL}',
    }
    headers = {
        'User-Agent': random.choice(USER_AGENTS)
    }

    for attempt in range(max_retries):
        try:
            logging.info(f"Fetching {url} with verify=False")
            response = requests.get(url, headers=headers, proxies=proxies, verify=False, timeout=60)
            if response.status_code != 200:
                logging.error(f"Bright Data proxy error {response.status_code} for {url}")
                logging.debug(f"Response headers: {response.headers}")
                logging.debug(f"Response text: {response.text}")
                raise Exception(f"Status {response.status_code}")
            html = response.text
            if not html:
                logging.error(f"No content returned for {url}")
                raise Exception("Empty content")
            return html
        except Exception as e:
            logging.error(f"Bright Data proxy error fetching {url}, attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(random.uniform(10, 20))
    return None


async def simulate_human_clicks(page, page_type='search'):
    try:
        selectors = [
            '.list-tools-bar a',
            '.filter-box-label',
            '.banner-img img',
            '.category-title a',
            '.footer-nav a'
        ]
        max_clicks = 2
        click_prob = 0.3

        clicked = 0
        for selector in selectors:
            if clicked >= max_clicks:
                break
            elements = await page.query_selector_all(selector)
            if not elements:
                continue
            for element in random.sample(elements, min(len(elements), max_clicks - clicked)):
                if random.random() < click_prob:
                    try:
                        await element.scroll_into_view_if_needed()
                        await element.click()
                        logging.info(f"Simulated click on {selector}")
                        clicked += 1
                        await asyncio.sleep(random.uniform(1, 3))
                    except Error:
                        logging.debug(f"Failed to click {selector}")
        return clicked
    except Exception as e:
        logging.error(f"Error simulating clicks: {e}")
        return 0


async def solve_capsolver_captcha(page):
    try:
        capsolver.api_key = CAPSOLVER_API_KEY
        if await page.query_selector('div.h-captcha'):
            logging.info("Solving hCaptcha with CapSolver...")
            site_key = await page.evaluate('() => document.querySelector("div.h-captcha").dataset.sitekey')
            solution = capsolver.solve({
                'type': 'HCaptchaTaskProxyless',
                'websiteURL': page.url,
                'websiteKey': site_key
            })
            response = solution.get('solution', {}).get('gRecaptchaResponse')
            if response:
                await page.evaluate(f'document.querySelector("div.h-captcha").dataset.hcaptcha_response = "{response}"')
                await page.click('button[type="submit"] || button:near(text=/Verify|Submit/i)')
                await page.wait_for_timeout(7000)
                return True
            else:
                logging.error("CapSolver returned no solution.")
        return False
    except Exception as e:
        logging.error(f"CapSolver error: {e}")
        return False


async def get_product_urls(context, search_urls, max_products=500):
    product_urls = set()
    for search_url in search_urls:
        if len(product_urls) >= max_products:
            break
        logging.info(f"Fetching search page: {search_url}")

        html = await fetch_brightdata_page(search_url)
        if not html:
            logging.error(f"Skipping {search_url} due to fetch failure.")
            for attempt in range(3):
                try:
                    page = await context.new_page()
                    await page.goto(search_url, timeout=180000, wait_until='domcontentloaded')
                    await page.wait_for_timeout(7000)

                    await simulate_human_clicks(page, 'search')
                    await asyncio.sleep(random.uniform(1, 3))

                    button_captcha = await page.query_selector('#cf-hcaptcha-container') or await page.query_selector('text=/Please verify|Human verification/i')
                    image_captcha = await page.query_selector('div.h-captcha') or await page.query_selector('iframe[src*="hcaptcha.com"]')

                    if button_captcha:
                        logging.warning(f"Button CAPTCHA detected on {search_url}, attempt {attempt + 1}")
                        try:
                            await page.click('#cf-hcaptcha-container input || button:near(text=/Verify|Human verification/i)')
                            await page.wait_for_timeout(10000)
                        except Error:
                            logging.error("Failed to solve button CAPTCHA")
                            await page.close()
                            if attempt == 2:
                                break
                            await asyncio.sleep(random.uniform(10, 20))
                            continue

                    if image_captcha:
                        logging.warning(f"Image CAPTCHA detected on {search_url}, attempt {attempt + 1}")
                        if await solve_capsolver_captcha(page):
                            logging.info("CapSolver solved CAPTCHA successfully")
                        else:
                            await page.screenshot(path=f'captcha_search_{search_url.split("=")[-1]}_attempt_{attempt + 1}.png')
                            print(f"CapSolver failed! Solve CAPTCHA manually at {search_url}, then press Enter...")
                            input()
                        await page.wait_for_timeout(7000)

                    await page.wait_for_selector('.item-container', timeout=180000)
                    product_containers = await page.query_selector_all('.item-container')

                    for container in product_containers:
                        classes = await container.evaluate('(element) => element.className')
                        if 'item-sponsored' in classes:
                            continue
                        product_link = await container.query_selector('a.item-title')
                        if product_link:
                            href = await product_link.get_attribute('href')
                            full_url = urljoin(search_url, href)
                            product_urls.add(full_url)
                            if len(product_urls) >= max_products:
                                break
                        await asyncio.sleep(random.uniform(0.5, 2))

                    logging.info(f"Collected {len(product_urls)} product URLs so far.")
                    await page.close()
                    break

                except Error as e:
                    logging.error(f"Playwright error fetching {search_url}, attempt {attempt + 1}: {e}")
                    await page.screenshot(path=f'error_search_{search_url.split("=")[-1]}_attempt_{attempt + 1}.png', timeout=60000)
                    await page.close()
                    if attempt == 2:
                        break
                    await asyncio.sleep(random.uniform(10, 20))
            continue

        parser = HTMLParser(html)
        product_containers = parser.css('.item-container')

        if not product_containers:
            logging.error(f"No products found on {search_url}")
            continue

        for container in product_containers:
            if 'item-sponsored' in container.attributes.get('class', ''):
                continue
            product_link = container.css_first('a.item-title')
            if product_link and 'href' in product_link.attributes:
                href = product_link.attributes['href']
                full_url = urljoin(search_url, href)
                product_urls.add(full_url)
                if len(product_urls) >= max_products:
                    break
            await asyncio.sleep(random.uniform(0.5, 2))

        logging.info(f"Collected {len(product_urls)} product URLs so far.")
        await asyncio.sleep(random.uniform(20, 40))

    return list(product_urls)[:max_products]


def save_urls_to_csvs(urls, num_files=5, base_filename='urls'):
    urls_per_file = len(urls) // num_files
    remainder = len(urls) % num_files

    for i in range(num_files):
        start_idx = i * urls_per_file
        end_idx = start_idx + urls_per_file + (1 if i == num_files - 1 else 0)
        if i == num_files - 1:
            file_urls = urls[start_idx:]
        else:
            file_urls = urls[start_idx:end_idx]

        filename = f'{base_filename}_{i+1}.csv'
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['URL'])
            for url in file_urls:
                writer.writerow([url])
        logging.info(f"Saved {len(file_urls)} URLs to {filename}")


async def main():
    try:
        async with async_playwright() as p:
            BRIGHTDATA_PROXY = {
                'server': f'http://{BRIGHTDATA_PROXY_URL}',
                'username': BRIGHTDATA_USERNAME,
                'password': BRIGHTDATA_PASSWORD
            }
            browser = await p.chromium.launch(headless=True, proxy=BRIGHTDATA_PROXY)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={'width': 1280, 'height': 720},
                ignore_https_errors=False
            )

            product_urls = await get_product_urls(context, SEARCH_URLS, max_products=500)
            save_urls_to_csvs(product_urls)

            await context.close()
            await browser.close()
    except Exception as e:
        logging.error(f"Main execution error: {e}")

if __name__ == '__main__':
    asyncio.run(main())
