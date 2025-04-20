import asyncio
import csv
import logging
import random
import sys
import requests
import uuid
import json
from playwright.async_api import async_playwright, Error
from selectolax.parser import HTMLParser
import capsolver
import os
import re
import time
import urllib3
from dotenv import load_dotenv


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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


async def fetch_brightdata_page(url, max_retries=2):
    session_id = str(uuid.uuid4())
    username = f"{BRIGHTDATA_USERNAME}-session-{session_id}"
    proxies = {
        'http': f'http://{username}:{BRIGHTDATA_PASSWORD}@{BRIGHTDATA_PROXY_URL}',
        'https': f'https://{username}:{BRIGHTDATA_PASSWORD}@{BRIGHTDATA_PROXY_URL}',
    }
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.newegg.com/'
    }
    for attempt in range(max_retries):
        try:
            logging.info(f"Fetching {url} with verify=False, session {session_id}")
            response = requests.get(url, headers=headers, proxies=proxies, verify=False, timeout=90)
            if response.status_code != 200:
                logging.error(f"Bright Data proxy error {response.status_code} for {url}: {response.text[:500]}")
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
            await asyncio.sleep(15)
    return None


async def fetch_no_proxy(url, max_retries=2):
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.newegg.com/'
    }
    for attempt in range(max_retries):
        try:
            logging.info(f"Fetching {url} without proxy, attempt {attempt + 1}")
            response = requests.get(url, headers=headers, verify=False, timeout=90)
            if response.status_code != 200:
                logging.error(f"No-proxy error {response.status_code} for {url}: {response.text[:500]}")
                raise Exception(f"Status {response.status_code}")
            html = response.text
            if not html:
                logging.error(f"No content returned for {url}")
                raise Exception("Empty content")
            return html
        except Exception as e:
            logging.error(f"No-proxy error fetching {url}, attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(15)
    return None


async def simulate_human_clicks(page):
    try:
        selectors = ['.product-subTitle a', '.tab-nav a', '.product-bullets a', '.footer-nav a', '.product-img img']
        max_clicks, click_prob = 2, 0.3
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


async def solve_capsolver_captcha(page, max_retries=3):
    for attempt in range(max_retries):
        try:
            capsolver.api_key = CAPSOLVER_API_KEY
            if await page.query_selector('div.h-captcha'):
                logging.info(f"Solving hCaptcha with CapSolver, attempt {attempt + 1}")
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
                logging.error("CapSolver returned no solution")
            return False
        except Exception as e:
            logging.error(f"CapSolver error, attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(5)
    return False


async def extract_json_rating(page, url):
    try:
        scripts = await page.query_selector_all('script[type="application/json"]')
        for script in scripts:
            content = await script.inner_text()
            try:
                data = json.loads(content)
                review = data.get('MainItem', {}).get('Review', {})
                rating = review.get('RatingOneDecimal') or review.get('Rating')
                if rating:
                    logging.info(f"Extracted JSON rating for {url}: {rating}")
                    return str(rating)
            except json.JSONDecodeError:
                continue
        logging.debug(f"No JSON rating found for {url}")
        return None
    except Exception as e:
        logging.error(f"Error extracting JSON rating for {url}: {e}")
        return None


async def scrape_product(context, url, batch_index, product_index, is_last_batches=False):
    product_data = {'URL': url, 'Name': '', 'Price': '', 'Rating': '', 'Seller': '', 'Description': ''}
    try:
        html = await fetch_brightdata_page(url)
        if not html:
            logging.warning(f"Proxy failed for {url}, trying no-proxy fetch...")
            html = await fetch_no_proxy(url)
        if html:
            parser = HTMLParser(html)
            product_data['Name'] = parser.css_first('.product-title').text() if parser.css_first('.product-title') else ''
            price_elem = parser.css_first('.price-current')
            price_text = price_elem.text() if price_elem else ''
            price_match = re.search(r'\$?([\d,]+\.\d{2})', price_text.replace(',', ''))
            product_data['Price'] = price_match.group(1) if price_match else ''
            rating_elem = parser.css_first('.product-action-group .product-rating i.rating')
            if not rating_elem:
                rating_elem = parser.css_first('.product-rating i[class*="rating-"]')
            if not rating_elem:
                rating_elem = parser.css_first('.product-rating .rating')
            if not rating_elem:
                rating_elem = parser.css_first('.product-rating [aria-label*="rating"]')
            rating_text = rating_elem.attributes.get('title', '') if rating_elem else ''
            if not rating_text and rating_elem:
                classes = rating_elem.attributes.get('class', '').split()
                for cls in classes:
                    if cls.startswith('rating-'):
                        rating_val = cls.replace('rating-', '').replace('-', '.')
                        if rating_val.replace('.', '').isdigit():
                            rating_text = f"{rating_val} out of 5"
            rating_match = re.search(r'(\d+\.?\d?)(?=\s|$|/)', rating_text)
            product_data['Rating'] = rating_match.group(1) if rating_match else ''
            if not product_data['Rating']:
                rating_html = parser.css_first('.product-rating').html if parser.css_first('.product-rating') else 'No .product-rating'
                logging.warning(f"No HTML rating found for {url}. HTML: {rating_html[:200]}")
                product_data['Rating'] = "No Rating"
            seller_elem = parser.css_first('.product-seller-box .product-seller-sold-by strong')
            if seller_elem:
                product_data['Seller'] = seller_elem.text()
            else:
                seller_elem = parser.css_first('.product-seller a')
                product_data['Seller'] = seller_elem.text() if seller_elem else 'Newegg'
            description_elements = parser.css('.product-bullets li')
            description = ' '.join([elem.text() for elem in description_elements]) if description_elements else ''
            if not description:
                description_elem = parser.css_first('.product-des')
                description = description_elem.text() if description_elem else ''
            product_data['Description'] = description
            logging.info(f"Scraped product {url}: {product_data['Name'][:50]}...")
            await asyncio.sleep(random.uniform(2, 5))
            if is_last_batches:
                await asyncio.sleep(60)
            return product_data
        logging.error(f"Proxy and no-proxy fetch failed for {url}, attempting Playwright...")
        for attempt in range(3):
            page = None
            try:
                page = await context.new_page()
                await page.set_extra_http_headers({
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1'
                })
                await asyncio.sleep(random.uniform(5, 10))
                await page.goto(url, timeout=120000, wait_until='domcontentloaded')
                await page.wait_for_timeout(7000)
                await simulate_human_clicks(page)
                await asyncio.sleep(random.uniform(1, 3))
                button_captcha = await page.query_selector('#cf-hcaptcha-container') or await page.query_selector('text=/Please verify|Human verification/i')
                image_captcha = await page.query_selector('div.h-captcha') or await page.query_selector('iframe[src*="hcaptcha.com"]')
                if button_captcha:
                    logging.warning(f"Button CAPTCHA detected on {url}, attempt {attempt + 1}")
                    try:
                        await page.click('#cf-hcaptcha-container input || button:near(text=/Verify|Human verification/i)')
                        await page.wait_for_timeout(10000)
                    except Error:
                        logging.error("Failed to solve button CAPTCHA")
                        if page:
                            await page.close()
                        if attempt == 2:
                            break
                        await asyncio.sleep(15)
                        continue
                if image_captcha:
                    logging.warning(f"Image CAPTCHA detected on {url}, attempt {attempt + 1}")
                    if await solve_capsolver_captcha(page):
                        logging.info("CapSolver solved CAPTCHA successfully")
                    else:
                        await page.screenshot(path=f'captcha_product_{batch_index}_{product_index}_attempt_{attempt + 1}.png', timeout=30000)
                        print(f"CapSolver failed! Solve CAPTCHA manually at {url}, then press Enter...")
                        input()
                    await page.wait_for_timeout(7000)
                name = await page.query_selector('.product-title')
                if not name:
                    logging.warning(f"No product title found for {url}, reloading page...")
                    await page.reload(timeout=120000)
                    name = await page.query_selector('.product-title')
                product_data['Name'] = await name.inner_text() if name else ''
                price_elem = await page.query_selector('.price-current')
                price_text = await price_elem.inner_text() if price_elem else ''
                price_match = re.search(r'\$?([\d,]+\.\d{2})', price_text.replace(',', ''))
                product_data['Price'] = price_match.group(1) if price_match else ''
                rating_elem = await page.query_selector('.product-action-group .product-rating i.rating')
                if not rating_elem:
                    rating_elem = await page.query_selector('.product-rating i[class*="rating-"]')
                if not rating_elem:
                    rating_elem = await page.query_selector('.product-rating .rating')
                if not rating_elem:
                    rating_elem = await page.query_selector('.product-rating [aria-label*="rating"]')
                rating_text = await rating_elem.get_attribute('title') if rating_elem else ''
                if not rating_text and rating_elem:
                    classes = await rating_elem.get_attribute('class')
                    classes = classes.split() if classes else []
                    for cls in classes:
                        if cls.startswith('rating-'):
                            rating_val = cls.replace('rating-', '').replace('-', '.')
                            if rating_val.replace('.', '').isdigit():
                                rating_text = f"{rating_val} out of 5"
                rating_match = re.search(r'(\d+\.?\d?)(?=\s|$|/)', rating_text)
                product_data['Rating'] = rating_match.group(1) if rating_match else ''
                if not product_data['Rating']:
                    json_rating = await extract_json_rating(page, url)
                    product_data['Rating'] = json_rating if json_rating else ''
                if not product_data['Rating']:
                    product_data['Rating'] = "No Rating"
                    rating_html = await page.evaluate('() => document.querySelector(".product-rating")?.outerHTML || "No .product-rating"')
                    logging.warning(f"No rating found for {url}. HTML: {rating_html[:200]}")
                seller_elem = await page.query_selector('.product-seller-box .product-seller-sold-by strong')
                if seller_elem:
                    product_data['Seller'] = await seller_elem.inner_text()
                else:
                    seller_elem = await page.query_selector('.product-seller a')
                    product_data['Seller'] = await seller_elem.inner_text() if seller_elem else 'Newegg'
                description_elements = await page.query_selector_all('.product-bullets li')
                description = ' '.join([await elem.inner_text() for elem in description_elements]) if description_elements else ''
                if not description:
                    description_elem = await page.query_selector('.product-des')
                    description = await description_elem.inner_text() if description_elem else ''
                product_data['Description'] = description
                logging.info(f"Scraped product {url}: {product_data['Name'][:50]}...")
                if page:
                    await page.close()
                await asyncio.sleep(random.uniform(2, 5))
                if is_last_batches:
                    await asyncio.sleep(60)
                return product_data
            except Error as e:
                logging.error(f"Playwright error scraping {url}, attempt {attempt + 1}: {e}")
                try:
                    if page:
                        await page.screenshot(path=f'error_product_{batch_index}_{product_index}_attempt_{attempt + 1}.png', timeout=30000)
                except Exception as se:
                    logging.error(f"Screenshot failed for {url}: {se}")
                if page:
                    await page.close()
                if attempt == 2:
                    logging.error(f"Skipping {url} after Playwright failures")
                    return product_data
                await asyncio.sleep(15)
            except Exception as e:
                logging.error(f"Unexpected Playwright error scraping {url}, attempt {attempt + 1}: {e}")
                if page:
                    await page.close()
                if attempt == 2:
                    logging.error(f"Skipping {url} after Playwright failures")
                    return product_data
        logging.error(f"Skipping {url} after Playwright failures")
        return product_data
    except Exception as e:
        logging.error(f"Unexpected error scraping {url}: {e}")
        return product_data


async def scrape_products(context, urls, output_file, batch_size=3):
    fieldnames = ['URL', 'Name', 'Price', 'Rating', 'Seller', 'Description']
    if not os.path.exists(output_file):
        for attempt in range(3):
            try:
                with open(output_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                logging.info(f"Created {output_file} with headers")
                break
            except PermissionError as e:
                logging.error(f"Permission denied creating {output_file}, attempt {attempt + 1}: {e}")
                logging.info(f"Ensure '{output_file}' is not open in Excel or other programs. Close all programs and try again.")
                if attempt == 2:
                    raise PermissionError(f"Failed to create {output_file}: {e}")
                time.sleep(5)
    for batch_index, i in enumerate(range(0, len(urls), batch_size)):
        batch_urls = urls[i:i + batch_size]
        is_last_batches = i >= len(urls) - 24
        logging.info(f"Processing batch {batch_index + 1} with {len(batch_urls)} URLs")
        batch_products = []
        for product_index, url in enumerate(batch_urls):
            product_data = await scrape_product(context, url, batch_index, product_index, is_last_batches)
            batch_products.append(product_data)
        if batch_products:
            for attempt in range(3):
                try:
                    with open(output_file, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        for product in batch_products:
                            writer.writerow(product)
                    logging.info(f"Appended {len(batch_products)} products to {output_file}")
                    break
                except PermissionError as e:
                    logging.error(f"Permission denied writing to {output_file}, attempt {attempt + 1}: {e}")
                    logging.info(f"Ensure '{output_file}' is not open in Excel or other programs. Close all programs and try again.")
                    if attempt == 2:
                        raise PermissionError(f"Failed to write to {output_file}: {e}")
                    time.sleep(5)
        else:
            logging.warning(f"No products scraped for batch {batch_index + 1}")
        if i + batch_size < len(urls):
            pause_duration = 600 if is_last_batches else 300
            logging.info(f"Pausing for {pause_duration//60} minutes before next batch...")
            await asyncio.sleep(pause_duration)


def read_urls_from_csv(csv_file):
    urls = []
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                urls.append(row['URL'])
        logging.info(f"Read {len(urls)} URLs from {csv_file}")
        return urls
    except Exception as e:
        logging.error(f"Error reading {csv_file}: {e}")
        return []


async def main():
    if len(sys.argv) != 2:
        print("Usage: python scrape_products.py <input_csv>")
        sys.exit(1)
    input_csv = sys.argv[1]
    output_csv = f"products_{input_csv.split('_')[-1]}"
    urls = read_urls_from_csv(input_csv)
    if not urls:
        logging.error("No URLs to scrape. Exiting.")
        sys.exit(1)
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
                ignore_https_errors=True,
                bypass_csp=True,
                java_script_enabled=True,
                extra_http_headers={
                    'Sec-Ch-Ua': '"Chromium";v="91", " Not A;Brand";v="99"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"'
                }
            )
            await scrape_products(context, urls, output_csv, batch_size=10)
            await context.close()
            await browser.close()
    except Exception as e:
        logging.error(f"Main execution error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
