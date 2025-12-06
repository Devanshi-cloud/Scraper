import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from datetime import datetime
import time
import random
import logging
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not set in .env file")

DB_NAME = 'ccube_research'
COLLECTION_NAME = 'apartment'
RUN_DURATION_HOURS = 1
MAX_PAGES = 50
CHROMEDRIVER_PATH = "/Users/devanshi/WebScrapperMongoDB-master/chromedriver/mac_arm-142.0.7444.176/chromedriver-mac-arm64/chromedriver"

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]


def get_mongodb_connection(max_retries=3):
    """Establish robust MongoDB connection with retry logic"""
    for attempt in range(max_retries):
        try:
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            # Test connection
            client.admin.command('ping')
            db = client[DB_NAME]
            collection = db[COLLECTION_NAME]
            
            # Create indexes for faster lookups
            collection.create_index([('Listing URL', 1)], unique=True, background=True)
            collection.create_index([('Apartment Name', 1), ('Location', 1)], background=True)
            
            logger.info(f"✓ Connected to MongoDB - Database: {DB_NAME}, Collection: {COLLECTION_NAME}")
            return client, collection
        except Exception as e:
            logger.error(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


def convert_price_to_number(price_str):
    """Convert price string to numeric value"""
    if not price_str or price_str == "N/A":
        return 0
    
    # Remove common text
    price_str = price_str.replace('₹', '').replace(',', '').replace('Starting From', '').strip().upper()
    
    try:
        if 'CR' in price_str:
            value = float(price_str.replace('CR', '').strip())
            return int(value * 10000000)
        elif 'LAC' in price_str:
            value = float(price_str.replace('LAC', '').strip())
            return int(value * 100000)
        elif 'K' in price_str:
            value = float(price_str.replace('K', '').strip())
            return int(value * 1000)
        elif 'PRICE ON REQUEST' in price_str:
            return -1
        else:
            return int(float(price_str))
    except (ValueError, AttributeError):
        return 0


def extract_per_sqft_price(text):
    """Extract per square foot price from text"""
    if not text:
        return "N/A"
    
    try:
        # Remove currency symbol and other text
        text = text.replace('₹', '').replace(',', '').replace('/ Sq. Ft', '').strip()
        return float(text)
    except (ValueError, AttributeError):
        return "N/A"


def scrape_detail_page_info(detail_url, max_retries=2):
    """Scrape additional information from detail page"""
    for attempt in range(max_retries):
        try:
            logger.info(f"Fetching detail page: {detail_url}")
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            response = requests.get(detail_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Initialize data
            data = {
                'amenities': [],
                'latitude': "N/A",
                'longitude': "N/A"
            }
            
            # Extract amenities
            amenities_modal = soup.find('div', id='amenitiesModalBox')
            if amenities_modal:
                for item in amenities_modal.find_all('div', class_='accordion-item'):
                    table = item.find('table', class_='amenities-popup-table')
                    if table:
                        for span in table.find_all('span'):
                            amenity = span.text.strip()
                            if amenity and amenity not in data['amenities']:
                                data['amenities'].append(amenity)
            else:
                amenities_box = soup.find('div', class_='amenities-list-box')
                if amenities_box:
                    for li in amenities_box.find_all('li'):
                        span = li.find('span')
                        if span and 'More' not in span.text:
                            amenity = span.text.strip()
                            if amenity and amenity not in data['amenities']:
                                data['amenities'].append(amenity)
            
            # Extract coordinates
            lat_input = soup.find('input', id='hd_plat')
            long_input = soup.find('input', id='hd_plang')
            if lat_input and 'value' in lat_input.attrs:
                try:
                    data['latitude'] = float(lat_input['value'].strip())
                except ValueError:
                    pass
            if long_input and 'value' in long_input.attrs:
                try:
                    data['longitude'] = float(long_input['value'].strip())
                except ValueError:
                    pass
            
            # Add delay to avoid rate limiting
            time.sleep(random.uniform(1.5, 3))
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
        except Exception as e:
            logger.error(f"Error scraping detail page: {e}")
            return None


def scrape_listing(listing, collection):
    """Extract data from a single listing element"""
    try:
        # Extract apartment name and URL
        title_h2 = listing.find('h2', class_='title')
        if not title_h2:
            logger.warning("No title found in listing, skipping")
            return None
        
        link_tag = title_h2.find('a', class_='projectDetailUrl')
        if not link_tag:
            logger.warning("No link found in listing, skipping")
            return None
        
        strong_tag = link_tag.find('strong')
        apartment_name = strong_tag.text.strip() if strong_tag else "N/A"
        
        listing_url = link_tag.get('href', '').strip()
        if not listing_url:
            logger.warning(f"No URL for {apartment_name}, skipping")
            return None
        
        # Make URL absolute
        if not listing_url.startswith('http'):
            listing_url = f"https://www.squareyards.com{listing_url}"
        
        # Check for duplicates
        if collection.find_one({'Listing URL': listing_url}):
            logger.info(f"⊘ Duplicate found: {apartment_name}")
            return None
        
        # Extract location
        city_map_div = title_h2.find('div', class_='city-map')
        location = "N/A"
        latitude = "N/A"
        longitude = "N/A"
        
        if city_map_div:
            city_span = city_map_div.find('span', class_='city')
            location = city_span.text.strip() if city_span else "N/A"
            
            # Extract coordinates from map data
            map_cta = city_map_div.find('small', class_='map-cta')
            if map_cta:
                try:
                    latitude = float(map_cta.get('data-lat', 'N/A'))
                    longitude = float(map_cta.get('data-long', 'N/A'))
                except (ValueError, TypeError):
                    pass
        
        # Extract price information
        price_ul = listing.find('ul', class_='price-area')
        min_price = 0
        per_sqft_cost = "N/A"
        
        if price_ul:
            price_li = price_ul.find('li', class_='price')
            if price_li:
                strong = price_li.find('strong')
                price_text = strong.text.strip() if strong else ""
                min_price = convert_price_to_number(price_text)
            
            # Extract per sqft price
            area_li = price_ul.find('li', class_='area')
            if area_li:
                per_sqft_cost = extract_per_sqft_price(area_li.text.strip())
        
        # Extract photo URL
        photo_url = "N/A"
        figure = listing.find('figure', class_='project-img')
        if figure:
            # Try multiple possible image locations
            img = figure.find('img', class_='img-responsive')
            if img:
                photo_url = img.get('src', img.get('data-src', 'N/A'))
        
        # Extract project information
        num_units = "N/A"
        total_area = "N/A"
        project_status = "N/A"
        
        info_ul = listing.find('ul', class_='project-information')
        if info_ul:
            for li in info_ul.find_all('li'):
                span = li.find('span')
                if span:
                    text = span.text.strip()
                    strong = span.find('strong')
                    
                    if 'No. of Units' in text and strong:
                        try:
                            num_units = int(strong.text.strip())
                        except ValueError:
                            num_units = strong.text.strip()
                    elif 'Total area' in text and strong:
                        total_area = strong.text.strip()
                    elif 'Project Status' in text and strong:
                        project_status = strong.text.strip()
        
        # Scrape detail page for amenities and additional info
        amenities = []
        detail_data = scrape_detail_page_info(listing_url)
        if detail_data:
            amenities = detail_data['amenities']
            # Override coordinates if detail page has better data
            if detail_data['latitude'] != "N/A":
                latitude = detail_data['latitude']
            if detail_data['longitude'] != "N/A":
                longitude = detail_data['longitude']
        
        # Prepare document
        apartment_data = {
            'Apartment Name': apartment_name,
            'Location': location,
            'Minimum Price': min_price,
            'Maximum Price': min_price,  # Can be updated if range is found
            'Per Sqft Cost': per_sqft_cost,
            'Number of Units': num_units,
            'Total Area': total_area,
            'Project Status': project_status,
            'Photo URL': photo_url,
            'Listing URL': listing_url,
            'Amenities': amenities,
            'Latitude': latitude,
            'Longitude': longitude,
            'Scraped At': datetime.now()
        }
        
        return apartment_data
        
    except Exception as e:
        logger.error(f"Error processing listing: {e}")
        logger.debug(traceback.format_exc())
        return None


def scrape_page(html_content, collection, start_time, run_duration_seconds):
    """Process all listings on current page"""
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Try both possible selectors
    listings = soup.find_all('article', class_='project-card')
    if not listings:
        listings = soup.find_all('div', class_='npTile')
    
    logger.info(f"Found {len(listings)} listings on page")
    
    if len(listings) == 0:
        logger.warning("No listings found! Page structure may have changed.")
        # Save HTML for debugging
        with open('debug_page.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info("Saved page HTML to debug_page.html for inspection")
    
    inserted_count = 0
    skipped_count = 0
    
    for idx, listing in enumerate(listings, 1):
        # Check time limit
        elapsed = time.time() - start_time
        if elapsed > run_duration_seconds:
            logger.info(f"Time limit reached ({run_duration_seconds/60:.1f} minutes)")
            return inserted_count, skipped_count, True
        
        logger.info(f"Processing listing {idx}/{len(listings)}")
        
        apartment_data = scrape_listing(listing, collection)
        
        if apartment_data:
            try:
                result = collection.insert_one(apartment_data)
                logger.info(f"✓ Inserted: {apartment_data['Apartment Name']} (ID: {result.inserted_id})")
                inserted_count += 1
            except DuplicateKeyError:
                logger.info(f"⊘ Duplicate: {apartment_data['Apartment Name']}")
                skipped_count += 1
            except Exception as e:
                logger.error(f"Error inserting document: {e}")
        else:
            skipped_count += 1
        
        # Add small delay between listings
        time.sleep(random.uniform(0.5, 1.5))
    
    return inserted_count, skipped_count, False


def setup_driver():
    """Configure and initialize Chrome driver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Execute CDP commands to hide automation
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver


def navigate_to_next_page(driver, page_number):
    """Navigate to next page using pagination"""
    try:
        # Scroll to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Try numbered pagination button
        selector = f'li.applyPagination[data-page="{page_number}"]'
        buttons = driver.find_elements(By.CSS_SELECTOR, selector)
        
        if buttons:
            driver.execute_script("arguments[0].click();", buttons[0])
            logger.info(f"Clicked page {page_number} button")
            time.sleep(random.uniform(3, 5))
            return True
        
        # Try next arrow
        arrow_selector = 'li.applyPagination span em.icon-arrow-right'
        arrows = driver.find_elements(By.CSS_SELECTOR, arrow_selector)
        
        if arrows:
            driver.execute_script("arguments[0].click();", arrows[0])
            logger.info("Clicked next arrow")
            time.sleep(random.uniform(3, 5))
            return True
        
        logger.warning("No pagination controls found")
        return False
        
    except Exception as e:
        logger.error(f"Pagination error: {e}")
        return False


def main():
    """Main scraping workflow"""
    logger.info("=" * 60)
    logger.info("Starting SquareYards Scraper")
    logger.info("=" * 60)
    
    # Connect to MongoDB
    try:
        client, collection = get_mongodb_connection()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return
    
    # Setup Selenium driver
    driver = None
    try:
        driver = setup_driver()
        logger.info("✓ Chrome driver initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        if client:
            client.close()
        return
    
    # Start scraping
    start_time = time.time()
    run_duration_seconds = RUN_DURATION_HOURS * 3600
    
    total_inserted = 0
    total_skipped = 0
    page_number = 1
    
    try:
        # Load initial page
        url = "https://www.squareyards.com/ready-to-move-projects-in-bangalore"
        logger.info(f"Loading: {url}")
        driver.get(url)
        
        # Wait for page to load - try multiple selectors
        wait = WebDriverWait(driver, 30)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.project-card")))
        except:
            logger.warning("article.project-card not found, trying alternative selector")
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.npTile")))
            except:
                logger.error("Could not find any listings. Saving page source for debugging.")
                with open('error_page.html', 'w', encoding='utf-8') as f:
                    f.write(driver.page_source)
                raise Exception("No listings found on page")
        
        logger.info("✓ Page loaded successfully")
        
        # Main scraping loop
        while page_number <= MAX_PAGES:
            elapsed = time.time() - start_time
            
            # Check time limit
            if elapsed > run_duration_seconds:
                logger.info(f"Time limit reached: {RUN_DURATION_HOURS} hour(s)")
                break
            
            logger.info(f"\n{'='*60}")
            logger.info(f"Page {page_number}/{MAX_PAGES} | Elapsed: {int(elapsed//60)}m {int(elapsed%60)}s")
            logger.info(f"{'='*60}")
            
            # Scroll to load dynamic content
            last_height = driver.execute_script("return document.body.scrollHeight")
            for _ in range(5):
                driver.execute_script("window.scrollBy(0, 1000);")
                time.sleep(1.5)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            
            # Get page HTML and scrape
            html_content = driver.page_source
            inserted, skipped, time_exceeded = scrape_page(
                html_content, collection, start_time, run_duration_seconds
            )
            
            total_inserted += inserted
            total_skipped += skipped
            
            logger.info(f"Page {page_number} complete: {inserted} inserted, {skipped} skipped")
            
            if time_exceeded:
                break
            
            # Navigate to next page
            page_number += 1
            if page_number <= MAX_PAGES:
                if not navigate_to_next_page(driver, page_number):
                    logger.info("No more pages available")
                    break
            else:
                logger.info(f"Reached max page limit: {MAX_PAGES}")
                break
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.debug(traceback.format_exc())
    
    finally:
        # Cleanup
        if driver:
            driver.quit()
            logger.info("✓ Chrome driver closed")
        
        if client:
            client.close()
            logger.info("✓ MongoDB connection closed")
        
        # Final statistics
        total_time = time.time() - start_time
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total Time: {int(total_time//60)}m {int(total_time%60)}s")
        logger.info(f"Total Inserted: {total_inserted}")
        logger.info(f"Total Skipped: {total_skipped}")
        logger.info(f"Pages Processed: {page_number}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()