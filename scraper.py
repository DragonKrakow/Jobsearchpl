import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import logging
import time
import random
from functools import wraps

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) Gecko/20100101 Firefox/122.0',
]


def retry_with_backoff(retries=3, backoff_factor=2, exceptions=(requests.RequestException,)):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries - 1:
                        logger.error(f"All {retries} attempts failed for {func.__name__}: {e}")
                        raise
                    wait_time = backoff_factor ** attempt + random.uniform(0, 1)
                    logger.warning(
                        f"Attempt {attempt + 1}/{retries} failed for {func.__name__}: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
        return wrapper
    return decorator


class JobScraper:
    def __init__(self):
        self._driver = None

    def _get_headers(self):
        """Get request headers with a random user agent."""
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def _get_selenium_driver(self):
        """Create and return a Selenium WebDriver with headless Chrome."""
        if self._driver is not None:
            return self._driver
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            self._driver = driver
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize Selenium WebDriver: {e}")
            return None

    def _close_driver(self):
        """Close Selenium WebDriver if open."""
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception as e:
                logger.debug(f"Error closing WebDriver: {e}")
            self._driver = None

    def _fetch_with_selenium(self, url, wait_time=3):
        """Fetch page content using Selenium WebDriver (for JS-rendered pages)."""
        driver = self._get_selenium_driver()
        if driver is None:
            raise RuntimeError("Selenium WebDriver is not available")
        driver.get(url)
        time.sleep(wait_time)
        return driver.page_source

    @retry_with_backoff(retries=3, backoff_factor=2)
    def _fetch_with_requests(self, url, timeout=15):
        """Fetch page content using requests with retry logic."""
        response = requests.get(url, headers=self._get_headers(), timeout=timeout)
        response.raise_for_status()
        return response.content

    def scrape_pracuj_pl(self, keyword):
        """Scrape jobs from pracuj.pl using Selenium for JavaScript rendering."""
        jobs = []
        url = f"https://www.pracuj.pl/praca/{quote(keyword)};kw"
        logger.info(f"Scraping pracuj.pl for keyword: {keyword}")

        try:
            try:
                page_source = self._fetch_with_selenium(url, wait_time=5)
            except Exception as selenium_err:
                logger.warning(f"Selenium unavailable for pracuj.pl, falling back to requests: {selenium_err}")
                page_source = self._fetch_with_requests(url)

            soup = BeautifulSoup(page_source, 'lxml')

            # Updated selectors for current pracuj.pl structure
            job_items = (
                soup.find_all('div', {'data-test': 'default-offer'})
                or soup.find_all('article', {'data-test': True})
                or soup.find_all('div', class_=re.compile(r'offer', re.I))
            )

            for item in job_items[:10]:
                try:
                    title_el = (
                        item.find(['h2', 'h3'], {'data-test': True})
                        or item.find('h2')
                        or item.find('a')
                    )
                    title = title_el.get_text(strip=True) if title_el else ''

                    link_el = item.find('a', href=True)
                    link = link_el['href'] if link_el else ''
                    if link and not link.startswith('http'):
                        link = 'https://www.pracuj.pl' + link

                    if title and link:
                        jobs.append({'title': title, 'url': link, 'source': 'pracuj.pl'})
                except Exception as e:
                    logger.debug(f"Error parsing pracuj.pl job item: {e}")
                    continue

            if not jobs:
                logger.warning("No jobs found on pracuj.pl - page structure may have changed")
        except Exception as e:
            logger.error(f"Error scraping pracuj.pl: {e}")

        logger.info(f"Found {len(jobs)} jobs on pracuj.pl")
        return jobs

    def scrape_olx_pl(self, keyword):
        """Scrape jobs from OLX.pl"""
        jobs = []
        url = f"https://www.olx.pl/praca/?q={quote(keyword)}"
        logger.info(f"Scraping OLX.pl for keyword: {keyword}")

        try:
            content = self._fetch_with_requests(url)
            soup = BeautifulSoup(content, 'lxml')

            # Updated selectors for current OLX.pl structure
            job_items = (
                soup.find_all('div', {'data-cy': 'l-card'})
                or soup.find_all('li', {'data-cy': 'offer'})
                or soup.select('div[data-testid*="card"]')
            )

            for item in job_items[:10]:
                try:
                    title_el = item.find(['h6', 'h4', 'h3', 'strong'])
                    title = title_el.get_text(strip=True) if title_el else ''

                    link_el = item.find('a', href=True)
                    link = link_el['href'] if link_el else ''
                    if link and not link.startswith('http'):
                        link = 'https://www.olx.pl' + link

                    if title and link:
                        jobs.append({'title': title, 'url': link, 'source': 'OLX.pl'})
                except Exception as e:
                    logger.debug(f"Error parsing OLX.pl job item: {e}")
                    continue

            if not jobs:
                logger.warning("No jobs found on OLX.pl - page structure may have changed")
        except Exception as e:
            logger.error(f"Error scraping OLX.pl: {e}")

        logger.info(f"Found {len(jobs)} jobs on OLX.pl")
        return jobs

    def scrape_linkedin(self, keyword):
        """Scrape jobs from LinkedIn (public listings) with search link fallback."""
        jobs = []
        search_url = f"https://www.linkedin.com/jobs/search/?keywords={quote(keyword)}&location=Poland"
        logger.info(f"Scraping LinkedIn for keyword: {keyword}")

        try:
            content = self._fetch_with_requests(search_url)
            soup = BeautifulSoup(content, 'lxml')

            # LinkedIn public job listings selectors
            job_items = (
                soup.find_all('div', class_='base-card')
                or soup.find_all('li', class_='result-card')
                or soup.find_all('div', {'data-job-id': True})
            )

            for item in job_items[:10]:
                try:
                    title_el = (
                        item.find('h3', class_=re.compile(r'title', re.I))
                        or item.find('span', class_=re.compile(r'title', re.I))
                        or item.find('h3')
                    )
                    title = title_el.get_text(strip=True) if title_el else ''

                    link_el = item.find('a', href=True)
                    link = link_el['href'] if link_el else ''
                    if link and not link.startswith('http'):
                        link = 'https://www.linkedin.com' + link

                    if title and link:
                        jobs.append({'title': title, 'url': link, 'source': 'LinkedIn'})
                except Exception as e:
                    logger.debug(f"Error parsing LinkedIn job item: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error scraping LinkedIn: {e}")

        # Always include direct search link as a fallback result
        jobs.append({
            'title': f'Search "{keyword}" jobs on LinkedIn',
            'url': search_url,
            'source': 'LinkedIn',
            'note': 'Direct search link'
        })

        logger.info(f"Found {len(jobs)} jobs on LinkedIn")
        return jobs

    def search_jobs(self, keyword):
        """Search for jobs across all platforms"""
        if not keyword or len(keyword.strip()) == 0:
            return {'error': 'Keyword cannot be empty'}

        keyword = keyword.strip()
        logger.info(f"Starting job search for keyword: {keyword}")

        try:
            pracuj_jobs = self.scrape_pracuj_pl(keyword)
            olx_jobs = self.scrape_olx_pl(keyword)
            linkedin_jobs = self.scrape_linkedin(keyword)
        finally:
            self._close_driver()

        total = len(pracuj_jobs) + len(olx_jobs) + len(linkedin_jobs)
        result = {
            'pracuj_pl': pracuj_jobs,
            'olx_pl': olx_jobs,
            'linkedin': linkedin_jobs,
            'keyword': keyword,
            'total_results': total,
        }

        if total == 0:
            result['message'] = (
                'No results found. The scrapers may be blocked or the page structure has changed.'
            )

        logger.info(f"Search complete. Total results: {total}")
        return result
