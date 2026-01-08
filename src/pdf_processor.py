"""
PDF processing and text extraction for Toyota FAQ scraper.
Downloads PDFs and extracts text content for RAG ingestion.
"""

import requests
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging
import sqlite3
from urllib.parse import urlparse

try:
    import PyPDF2
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logging.warning("PDF libraries not available. PDF processing disabled.")

from src.database import DatabaseManager
from src.config import Config


class PDFProcessor:
    """Processes PDF files found during crawling."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
        
        if not PDF_AVAILABLE:
            self.logger.error("PDF processing libraries not installed")
            raise ImportError("Install PyPDF2 and pdfplumber for PDF processing")
        
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': config.user_agent})
    
    def is_pdf_url(self, url: str) -> bool:
        """Check if URL points to a PDF file."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        return path.endswith('.pdf') or 'pdf' in path
    
    def download_pdf(self, pdf_url: str, source_page_id: Optional[int] = None) -> Optional[str]:
        """Download PDF from URL and return local file path."""
        try:
            self.logger.info(f"Downloading PDF: {pdf_url}")
            
            response = self.session.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and not pdf_url.lower().endswith('.pdf'):
                self.logger.warning(f"URL may not be a PDF: {content_type}")
            
            # Generate filename
            url_hash = hashlib.md5(pdf_url.encode()).hexdigest()
            filename = f"{url_hash}.pdf"
            file_path = Path(self.config.raw_dir) / filename
            
            # Save PDF
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.logger.info(f"PDF downloaded to: {file_path}")
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"Failed to download PDF {pdf_url}: {e}")
            return None
    
    def extract_text_with_pypdf2(self, file_path: str) -> Tuple[str, int]:
        """Extract text using PyPDF2."""
        text = ""
        page_count = 0
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                page_count = len(pdf_reader.pages)
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text.strip():
                            text += page_text + "\n"
                    except Exception as e:
                        self.logger.warning(f"Error extracting page {page_num}: {e}")
            
            return text.strip(), page_count
            
        except Exception as e:
            self.logger.error(f"PyPDF2 extraction failed: {e}")
            return "", 0
    
    def extract_text_with_pdfplumber(self, file_path: str) -> Tuple[str, int]:
        """Extract text using pdfplumber (better layout preservation)."""
        text = ""
        page_count = 0
        
        try:
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            text += page_text + "\n"
                    except Exception as e:
                        self.logger.warning(f"Error extracting page {page_num} with pdfplumber: {e}")
            
            return text.strip(), page_count
            
        except Exception as e:
            self.logger.error(f"pdfplumber extraction failed: {e}")
            return "", 0
    
    def clean_extracted_text(self, text: str) -> str:
        """Clean and normalize extracted PDF text."""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Fix common PDF extraction artifacts
        text = text.replace('ﬁ', 'fi')
        text = text.replace('ﬂ', 'fl')
        text = text.replace('ﬀ', 'ff')
        
        # Remove page numbers and headers/footers patterns
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip likely page numbers (short lines with numbers)
            if len(line) < 10 and line.isdigit():
                continue
            
            # Skip very short lines that are likely headers/footers
            if len(line) < 20:
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def extract_text(self, file_path: str) -> Tuple[str, int, str]:
        """Extract text from PDF using multiple methods."""
        self.logger.info(f"Extracting text from: {file_path}")
        
        # Try pdfplumber first (usually better quality)
        text, page_count = self.extract_text_with_pdfplumber(file_path)
        method = "pdfplumber"
        
        # Fallback to PyPDF2 if pdfplumber fails
        if not text or len(text) < 100:
            self.logger.debug("Trying PyPDF2 as fallback")
            text_fallback, page_count_fallback = self.extract_text_with_pypdf2(file_path)
            
            if len(text_fallback) > len(text):
                text = text_fallback
                page_count = page_count_fallback
                method = "pypdf2"
        
        # Clean the extracted text
        cleaned_text = self.clean_extracted_text(text)
        
        self.logger.info(f"Extracted {len(cleaned_text)} characters from {page_count} pages using {method}")
        
        return cleaned_text, page_count, method
    
    def save_extracted_text(self, text: str, pdf_url: str) -> str:
        """Save extracted text to file."""
        url_hash = hashlib.md5(pdf_url.encode()).hexdigest()
        text_filename = f"{url_hash}_extracted.txt"
        text_path = Path(self.config.processed_dir) / text_filename
        
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        return str(text_path)
    
    def process_pdf(self, pdf_url: str, source_page_id: Optional[int] = None) -> Optional[int]:
        """Process a single PDF: download, extract text, and store in database."""
        try:
            # Download PDF
            file_path = self.download_pdf(pdf_url, source_page_id)
            if not file_path:
                return None
            
            # Get file size
            file_size = Path(file_path).stat().st_size
            
            # Extract text
            extracted_text, page_count, extraction_method = self.extract_text(file_path)
            
            if not extracted_text:
                self.logger.warning(f"No text extracted from PDF: {pdf_url}")
                extraction_status = 'failed'
                extraction_error = 'No text could be extracted'
                text_path = None
            else:
                # Save extracted text
                text_path = self.save_extracted_text(extracted_text, pdf_url)
                extraction_status = 'completed'
                extraction_error = None
            
            # Store in database
            pdf_data = {
                'source_url': pdf_url,
                'source_page_id': source_page_id,
                'filename': Path(file_path).name,
                'file_path': file_path,
                'file_size': file_size,
                'page_count': page_count,
                'extracted_text_path': text_path,
                'extraction_status': extraction_status,
                'extraction_error': extraction_error
            }
            
            pdf_id = self.db.insert_pdf(pdf_data)
            
            if pdf_id:
                self.logger.info(f"PDF processed successfully: {pdf_url}")
                return pdf_id
            else:
                self.logger.warning(f"PDF already exists in database: {pdf_url}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error processing PDF {pdf_url}: {e}")
            
            # Store failed attempt
            pdf_data = {
                'source_url': pdf_url,
                'source_page_id': source_page_id,
                'filename': '',
                'file_path': '',
                'file_size': 0,
                'page_count': 0,
                'extracted_text_path': None,
                'extraction_status': 'failed',
                'extraction_error': str(e)
            }
            
            self.db.insert_pdf(pdf_data)
            return None
    
    def discover_pdfs_from_pages(self) -> List[Dict[str, any]]:
        """Discover PDF URLs from already crawled pages."""
        pdfs_found = []
        
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            
            # Get pages with raw HTML
            cursor.execute("""
                SELECT id, url, raw_html_path 
                FROM pages 
                WHERE extraction_status = 'completed' 
                AND raw_html_path IS NOT NULL
            """)
            
            pages = cursor.fetchall()
            
            for page_id, page_url, html_path in pages:
                try:
                    # Read HTML content
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    
                    # Find PDF links
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'lxml')
                    
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if self.is_pdf_url(href):
                            # Convert to absolute URL
                            from urllib.parse import urljoin
                            pdf_url = urljoin(page_url, href)
                            
                            pdfs_found.append({
                                'pdf_url': pdf_url,
                                'source_page_id': page_id,
                                'source_page_url': page_url,
                                'link_text': link.get_text(strip=True)
                            })
                
                except Exception as e:
                    self.logger.error(f"Error discovering PDFs in page {page_url}: {e}")
        
        self.logger.info(f"Discovered {len(pdfs_found)} PDF URLs")
        return pdfs_found
    
    def process_all_pdfs(self) -> Dict[str, any]:
        """Process all PDFs discovered from crawled pages."""
        if not self.config.pdf_enabled:
            self.logger.info("PDF processing disabled in config")
            return {'status': 'disabled'}
        
        self.logger.info("Starting PDF processing")
        
        # Discover PDFs
        pdfs_to_process = self.discover_pdfs_from_pages()
        
        if not pdfs_to_process:
            self.logger.info("No PDFs found to process")
            return {'pdfs_discovered': 0, 'pdfs_processed': 0}
        
        # Process each PDF
        processed_count = 0
        failed_count = 0
        
        for pdf_info in pdfs_to_process:
            pdf_id = self.process_pdf(
                pdf_info['pdf_url'], 
                pdf_info['source_page_id']
            )
            
            if pdf_id:
                processed_count += 1
            else:
                failed_count += 1
        
        processing_summary = {
            'pdfs_discovered': len(pdfs_to_process),
            'pdfs_processed': processed_count,
            'pdfs_failed': failed_count,
            'success_rate': (processed_count / len(pdfs_to_process)) * 100 if pdfs_to_process else 0
        }
        
        self.logger.info(f"PDF processing completed: {processing_summary}")
        return processing_summary
