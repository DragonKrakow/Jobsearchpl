import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import json

class JobScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def scrape_pracuj_pl(self, keyword):
        """Scrape jobs from pracuj.pl"""
        jobs = []
        try:
            url = f"https://www.pracuj.pl/praca?keywords={quote(keyword)}"
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job listings
            job_items = soup.find_all('a', {'data-test': 'link-offer'})
            
            for item in job_items[:10]:  # Limit to 10 results
                try:
                    title = item.get_text(strip=True)
                    link = item.get('href', '')
                    if link and not link.startswith('http'):
                        link = 'https://www.pracuj.pl' + link
                    
                    if title and link:
                        jobs.append({
                            'title': title,
                            'url': link,
                            'source': 'pracuj.pl'
                        })
                except:
                    continue
        except Exception as e:
            print(f"Error scraping pracuj.pl: {e}")
        
        return jobs
    
    def scrape_olx_pl(self, keyword):
        """Scrape jobs from OLX.pl"""
        jobs = []
        try:
            url = f"https://www.olx.pl/d/search/?q={quote(keyword)}&category_id=6100"
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find job listings
            job_items = soup.find_all('a', {'data-testid': 'listing-grid-item'})
            
            for item in job_items[:10]:  # Limit to 10 results
                try:
                    title = item.get_text(strip=True)
                    link = item.get('href', '')
                    
                    if title and link:
                        jobs.append({
                            'title': title,
                            'url': link,
                            'source': 'OLX.pl'
                        })
                except:
                    continue
        except Exception as e:
            print(f"Error scraping OLX.pl: {e}")
        
        return jobs
    
    def scrape_linkedin(self, keyword):
        """Scrape jobs from LinkedIn"""
        jobs = []
        try:
            # LinkedIn requires more complex handling, so we'll provide direct search links
            url = f"https://www.linkedin.com/jobs/search/?keywords={quote(keyword)}&location=Poland"
            
            jobs.append({
                'title': f'{keyword} - Search on LinkedIn',
                'url': url,
                'source': 'LinkedIn'
            })
            
            # Try to get some additional info
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # LinkedIn structure is complex, so we'll focus on providing the search link
        except Exception as e:
            print(f"Error with LinkedIn: {e}")
        
        return jobs
    
    def search_jobs(self, keyword):
        """Search for jobs across all platforms"""
        if not keyword or len(keyword.strip()) == 0:
            return {'error': 'Keyword cannot be empty'}
        
        keyword = keyword.strip()
        
        all_jobs = {
            'pracuj_pl': self.scrape_pracuj_pl(keyword),
            'olx_pl': self.scrape_olx_pl(keyword),
            'linkedin': self.scrape_linkedin(keyword),
            'keyword': keyword,
            'total_results': 0
        }
        
        total = sum(len(v) for k, v in all_jobs.items() if isinstance(v, list))
        all_jobs['total_results'] = total
        
        return all_jobs
