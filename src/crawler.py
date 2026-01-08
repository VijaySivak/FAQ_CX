"""
BFS Web Crawler with robots.txt compliance.
Implements depth-limited, domain-restricted crawling with rate limiting.
"""

import time
import requests
import re
import sqlite3
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Set, Dict, Optional, Tuple
import logging
from collections import deque
import hashlib

from src.database import DatabaseManager
from src.config import Config


class RobotsCache:
    """Cache for robots.txt files to avoid repeated requests."""
    
    def __init__(self):
        self.cache: Dict[str, RobotFileParser] = {}
        self.user_agent = "FAQ-Scraper/1.0"
    
    def get_robots_parser(self, base_url: str) -> RobotFileParser:
        """Get or create a robots.txt parser for the given domain."""
        parsed = urlparse(base_url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        if domain not in self.cache:
            robots_url = urljoin(domain, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                logging.info(f"Loaded robots.txt for {domain}")
            except Exception as e:
                logging.warning(f"Failed to load robots.txt for {domain}: {e}")
                # Default to allowing everything if robots.txt fails
                rp.allow_all = True
            
            self.cache[domain] = rp
        
        return self.cache[domain]


class FAQCrawler:
    """BFS crawler for FAQ pages."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.robots_cache = RobotsCache()
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': config.user_agent})
        
        # Rate limiting
        self.last_request_time = 0
        self.request_interval = 1.0 / config.request_rate_limit
        
        # URL normalization
        self.allowed_domains = set(config.allowed_domains)
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, config.log_level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(config.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def is_allowed_domain(self, url: str) -> bool:
        """Check if URL belongs to allowed domains."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain in self.allowed_domains
    
    def normalize_url(self, url: str, base_url: Optional[str] = None) -> Optional[str]:
        """Normalize and validate URL."""
        try:
            if base_url:
                url = urljoin(base_url, url)
            
            parsed = urlparse(url)
            
            # Remove fragments and normalize
            url = urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                parsed.path,
                parsed.params,
                parsed.query,
                ''  # Remove fragment
            ))
            
            # Only allow HTTP/HTTPS
            if parsed.scheme not in ['http', 'https']:
                return None
            
            return url
        except Exception as e:
            self.logger.warning(f"URL normalization failed for {url}: {e}")
            return None
    
    def can_fetch_url(self, url: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        try:
            rp = self.robots_cache.get_robots_parser(url)
            return rp.can_fetch(self.robots_cache.user_agent, url)
        except Exception as e:
            self.logger.warning(f"Robots.txt check failed for {url}: {e}")
            return True  # Allow if robots.txt check fails
    
    def respect_rate_limit(self):
        """Implement rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.request_interval:
            sleep_time = self.request_interval - time_since_last
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def extract_links(self, html: str, base_url: str) -> List[Dict[str, any]]:
        """Extract all links from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            if not href or href.startswith('#'):
                continue
            
            normalized = self.normalize_url(href, base_url)
            if not normalized:
                continue
            
            link_text = link.get_text(strip=True)
            is_internal = self.is_allowed_domain(normalized)
            
            links.append({
                'url': normalized,
                'text': link_text,
                'is_internal': is_internal
            })
        
        return links
    
    def extract_metadata(self, html: str, url: str) -> Dict[str, any]:
        """Extract metadata from HTML content."""
        soup = BeautifulSoup(html, 'lxml')
        
        # Title
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ""
        
        # Phone numbers (US format)
        phone_pattern = r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'
        phones = re.findall(phone_pattern, html)
        phone_numbers = [''.join(filter(str.isdigit, phone)) for phone in phones if phone]
        
        # Email addresses
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, html)
        
        # Word count
        text = soup.get_text()
        words = len(text.split())
        
        # Content type detection
        content_type = 'text/html'
        if 'pdf' in url.lower():
            content_type = 'application/pdf'
        elif any(video in url.lower() for video in ['video', 'watch', 'youtube', 'vimeo']):
            content_type = 'video'
        
        return {
            'title': title,
            'word_count': words,
            'phone_numbers': phone_numbers,
            'email_addresses': emails,
            'content_type': content_type
        }
    
    def save_raw_content(self, content: str, url: str, content_type: str = 'html') -> str:
        """Save raw content to filesystem."""
        # Create filename from URL hash
        url_hash = hashlib.md5(url.encode()).hexdigest()
        extension = 'html' if content_type == 'html' else 'txt'
        filename = f"{url_hash}.{extension}"
        
        file_path = Path(self.config.raw_dir) / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return str(file_path)
    
    def fetch_page(self, url: str) -> Tuple[Optional[str], Optional[Dict[str, any]]]:
        """Fetch a single page with error handling."""
        try:
            self.respect_rate_limit()
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Check if we got HTML
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                self.logger.warning(f"Non-HTML content at {url}: {content_type}")
                return None, {'status_code': response.status_code, 'content_type': content_type}
            
            # Save raw HTML
            raw_path = self.save_raw_content(response.text, url, 'html')
            
            # Extract metadata
            metadata = self.extract_metadata(response.text, url)
            metadata.update({
                'status_code': response.status_code,
                'raw_html_path': raw_path
            })
            
            return response.text, metadata
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return None, {'error': str(e)}
        except Exception as e:
            self.logger.error(f"Unexpected error fetching {url}: {e}")
            return None, {'error': str(e)}
    
    def process_page(self, url: str, depth: int, parent_url: Optional[str] = None) -> bool:
        """Process a single page and extract links."""
        self.logger.info(f"Processing page at depth {depth}: {url}")
        
        # Check if already processed
        if self.db.get_page_by_url(url):
            self.logger.debug(f"Page already processed: {url}")
            return True
        
        # Check robots.txt
        if not self.can_fetch_url(url):
            self.logger.warning(f"Robots.txt disallows: {url}")
            return False
        
        # Fetch page
        html_content, metadata = self.fetch_page(url)
        
        if html_content is None:
            # Record failed page
            page_data = {
                'url': url,
                'depth': depth,
                'parent_url': parent_url,
                'is_internal': self.is_allowed_domain(url),
                'extraction_status': 'failed',
                'extraction_error': metadata.get('error', 'Unknown error')
            }
            self.db.insert_page(page_data)
            return False
        
        # Extract links
        links = self.extract_links(html_content, url)
        
        # Count internal vs external links
        internal_count = sum(1 for link in links if link['is_internal'])
        external_count = len(links) - internal_count
        
        # Update page data
        page_data = {
            'url': url,
            'title': metadata.get('title', ''),
            'depth': depth,
            'parent_url': parent_url,
            'is_internal': self.is_allowed_domain(url),
            'content_type': metadata.get('content_type', 'text/html'),
            'status_code': metadata.get('status_code'),
            'raw_html_path': metadata.get('raw_html_path'),
            'word_count': metadata.get('word_count', 0),
            'internal_links': internal_count,
            'external_links': external_count,
            'phone_numbers': metadata.get('phone_numbers', []),
            'email_addresses': metadata.get('email_addresses', []),
            'extraction_status': 'completed'
        }
        
        page_id = self.db.insert_page(page_data)
        
        # Add internal links to crawl queue if within depth limit
        if depth < self.config.crawl_depth:
            internal_links = [
                link['url'] for link in links 
                if link['is_internal'] and depth + 1 <= self.config.crawl_depth
            ]
            
            if internal_links:
                queue_ids = self.db.add_to_crawl_queue(internal_links, depth + 1, url)
                self.logger.info(f"Added {len(internal_links)} internal links to queue")
                
                # Record links in database
                links_data = []
                for link in links:
                    links_data.append({
                        'from_page_id': page_id,
                        'to_url': link['url'],
                        'link_text': link['text'],
                        'is_internal': link['is_internal'],
                        'is_followed': link['is_internal'] and depth + 1 <= self.config.crawl_depth,
                        'follow_depth': depth + 1 if link['is_internal'] else None
                    })
                
                self.db.insert_links(links_data)
        
        return True
    
    def run_crawl(self) -> Dict[str, any]:
        """Run the complete BFS crawl process."""
        self.logger.info("Starting FAQ crawl")
        
        # Add seed URLs to queue
        queue_ids = self.db.add_to_crawl_queue(self.config.seed_urls, 0)
        self.logger.info(f"Added {len(self.config.seed_urls)} seed URLs to queue")
        
        pages_processed = 0
        pages_failed = 0
        max_pages_reached = False
        
        while pages_processed < self.config.max_pages:
            # Get next batch of URLs
            batch = self.db.get_next_crawl_urls(batch_size=5)
            
            if not batch:
                self.logger.info("No more URLs in crawl queue")
                break
            
            for item in batch:
                if pages_processed >= self.config.max_pages:
                    max_pages_reached = True
                    break
                
                success = self.process_page(
                    item['url'], 
                    item['depth'], 
                    item['parent_url']
                )
                
                if success:
                    pages_processed += 1
                else:
                    pages_failed += 1
                
                # Mark queue item as completed
                status = 'completed' if success else 'failed'
                self.db.mark_crawl_completed(item['id'], status)
            
            if max_pages_reached:
                self.logger.warning(f"Reached max pages limit: {self.config.max_pages}")
                break
        
        # Compute final statistics
        stats = self.db.get_crawl_statistics()
        
        crawl_summary = {
            'pages_processed': pages_processed,
            'pages_failed': pages_failed,
            'max_pages_reached': max_pages_reached,
            'stats': stats
        }
        
        self.logger.info(f"Crawl completed: {pages_processed} processed, {pages_failed} failed")
        return crawl_summary


# Add missing method to DatabaseManager
def get_page_by_url(self, url: str) -> Optional[Dict[str, any]]:
    """Get page by URL."""
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pages WHERE url = ?", (url,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
    return None

# Monkey patch the method
DatabaseManager.get_page_by_url = get_page_by_url
