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

    @retry_with_backoff(retries=3, backoff_factor=2)
    def _fetch_with_requests(self, url, timeout=10):
        """Fetch page content using requests with retry logic.

        timeout is set to 10 seconds to prevent hanging on cloud deployments.
        """
        response = requests.get(url, headers=self._get_headers(), timeout=timeout)
        response.raise_for_status()
        return response.content

    def scrape_pracuj_pl(self, keyword):
        """Scrape jobs from pracuj.pl using requests."""
        jobs = []
        url = f"https://www.pracuj.pl/praca/{quote(keyword)};kw"
        logger.info(f"Scraping pracuj.pl for keyword: {keyword}")

        try:
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

        pracuj_jobs = self.scrape_pracuj_pl(keyword)
        linkedin_jobs = self.scrape_linkedin(keyword)

        total = len(pracuj_jobs) + len(linkedin_jobs)
        result = {
            'pracuj_pl': pracuj_jobs,
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
