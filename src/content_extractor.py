"""
Content extraction and processing for FAQ pages.
Extracts FAQ pairs, cleans text, and determines answer modes.
"""

import re
import hashlib
import sqlite3
from typing import List, Dict, Tuple, Optional, Set
from pathlib import Path
from bs4 import BeautifulSoup, Tag
import logging
from urllib.parse import urljoin, urlparse

from src.database import DatabaseManager
from src.config import Config


class FAQExtractor:
    """Extracts FAQ question-answer pairs from HTML content."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
        
        # FAQ detection patterns
        self.question_patterns = [
            r'^\s*[Qq][:\.\-]\s*',  # Q: or Q. or Q-
            r'^\s*[Qq]uestion\s*\d*[:\.\-]\s*',
            r'^\s*\d+\.\s*',
            r'^\s*[Qq]u\s*\d*[:\.\-]\s*',
            r'^\s*[Ff][Aa][Qq][:\.\-]\s*',
        ]
        
        # Patterns to reject (non-FAQ content)
        self.reject_patterns = [
            r'^\s*(extremely|very|somewhat|not at all)\s+(poor|good|satisfied|likely)',  # Rating scales
            r'^\s*your\s+secure\s+session',  # Session warnings
            r'^\s*(error|sorry|apologize|oops)',  # Error messages
            r'^\s*(click|tap|select|choose)\s+(here|below|above)',  # UI instructions
            r'^\s*\d+\s*$',  # Just numbers
            r'^\s*[a-z]{1,3}\s*$',  # Very short words
            r'^\s*(yes|no|ok|cancel|submit|continue)\s*$',  # Button text
            r'^\s*(home|about|contact|login|logout|sign in|sign out)\s*$',  # Nav items
        ]
        
        self.answer_patterns = [
            r'^\s*[Aa][:\.\-]\s*',  # A: or A. or A-
            r'^\s*[Aa]nswer\s*\d*[:\.\-]\s*',
            r'^\s*[Aa]ns\s*\d*[:\.\-]\s*',
        ]
        
        # Phone number patterns
        self.phone_patterns = [
            r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
            r'\b\(\d{3}\)[-\s]?\d{3}[-.\s]?\d{4}\b',
            r'\b1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
        ]
        
        # Link patterns
        self.link_out_patterns = [
            r'click\s+here',
            r'learn\s+more',
            r'visit\s+our',
            r'see\s+more',
            r'view\s+details',
            r'read\s+more',
        ]
    
    def clean_text(self, text: str, preserve_links: bool = False) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""
        
        # If preserving links, convert HTML links to markdown format
        if preserve_links:
            # Convert <a href="url">text</a> to [text](url)
            text = re.sub(r'<a\s+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', r'[\2](\1)', text, flags=re.IGNORECASE)
        
        # For list content, extract list items and join with newlines
        if '<ul' in text or '<ol' in text:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, 'html.parser')
            
            # Extract list items
            list_items = []
            for li in soup.find_all('li'):
                li_text = li.get_text().strip()
                if li_text:
                    list_items.append(li_text)
            
            if list_items:
                # Join list items with newlines
                return '\n'.join(list_items)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove HTML entities
        text = re.sub(r'&[a-zA-Z]+;', '', text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep basic punctuation and markdown links
        if preserve_links:
            text = re.sub(r'[^\w\s\.\?\!\,\:\;\-\(\)\/\&\@\#\%\[\]\(\)]', '', text)
        else:
            text = re.sub(r'[^\w\s\.\?\!\,\:\;\-\(\)\/\&\@\#\$\%]', '', text)
        
        return text
    
    def normalize_question(self, question: str) -> str:
        """Normalize question text for better deduplication."""
        if not question:
            return ""
        
        # Convert to lowercase
        question = question.lower()
        
        # Remove leading/trailing whitespace
        question = question.strip()
        
        # Collapse multiple spaces to single space
        question = re.sub(r'\s+', ' ', question)
        
        # Normalize quotes
        question = question.replace('"', '"').replace('"', '"')
        question = question.replace(''', "'").replace(''', "'")
        
        # Remove trailing question mark if present (for consistency)
        if question.endswith('?'):
            question = question[:-1].strip()
        
        return question
    
    def hash_content(self, content: str) -> str:
        """Generate hash for content deduplication."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def detect_answer_mode(self, question: str, answer: str, page_url: str) -> str:
        """
        Determine the answer mode based on content analysis.
        Returns one of: DIRECT_TEXT, LINK_OUT, PHONE_ESCALATION, PDF_ATTACHMENT, VIDEO, PORTAL_REDIRECT
         """
        answer_lower = answer.lower()
        question_lower = question.lower()
        
        # Check for phone escalation
        for pattern in self.phone_patterns:
            if re.search(pattern, answer):
                return 'PHONE_ESCALATION'
        
        # Check for PDF attachment
        if 'pdf' in answer_lower or any(ext in answer_lower for ext in ['.pdf', 'download pdf']):
            return 'PDF_ATTACHMENT'
        
        # Check for video content
        video_keywords = ['video', 'watch', 'youtube', 'vimeo', 'tutorial']
        if any(keyword in answer_lower for keyword in video_keywords):
            return 'VIDEO'
        
        # Check for portal/login redirect - but be more specific
        portal_keywords = ['login', 'portal', 'account', 'sign in', 'authenticate']
        portal_triggers = ['click here', 'visit', 'go to', 'access your']
        
        # Only classify as PORTAL_REDIRECT if it has both portal keywords AND action triggers
        has_portal_keywords = any(keyword in answer_lower for keyword in portal_keywords)
        has_action_triggers = any(trigger in answer_lower for trigger in portal_triggers)
        
        if has_portal_keywords and has_action_triggers:
            return 'PORTAL_REDIRECT'
        
        # Check for link out patterns
        for pattern in self.link_out_patterns:
            if re.search(pattern, answer_lower):
                return 'LINK_OUT'
        
        # Default to direct text
        return 'DIRECT_TEXT'
    
    def is_valid_faq_question(self, question: str) -> bool:
        """Check if text is a valid FAQ question (not UI text, error, or marketing copy)."""
        if not question or len(question) < 10:
            return False
        
        question_lower = question.lower()
        
        # Reject based on patterns
        for pattern in self.reject_patterns:
            if re.search(pattern, question_lower, re.I):
                return False
        
        # Must contain question words or end with ?
        question_indicators = ['what', 'how', 'when', 'where', 'why', 'who', 'which', 'can', 'do', 'does', 'is', 'are', 'will', 'should', 'may', '?']
        has_question_indicator = any(word in question_lower for word in question_indicators)
        
        # Reject pure marketing/title text without question indicators
        words = question.split()
        
        # Short phrases (<=6 words) without question indicators are likely titles/headers
        if len(words) <= 6 and not has_question_indicator:
            return False
        
        # Reject common marketing phrases and section headers
        marketing_phrases = [
            'miles on the road',
            'youve got options',
            'exclusively available',
            'youll receive',
            'what you need to know',
            'there are',
            'receive 24-hour',
            'when it comes to',
            'youre in the drivers seat',
            'in the drivers seat',
        ]
        
        if any(phrase in question_lower for phrase in marketing_phrases):
            return False
        
        # Reject single-word or very short "questions" that are actually section headers
        # These often don't have punctuation and are just labels
        if len(words) <= 2 and '?' not in question:
            # Single or two-word phrases without ? are likely headers
            # Examples: "Cancellation", "Coverage Details", "Important Information"
            return False
        
        # Reject company/organization names (typically end with Inc., LLC, Corp., Ltd.)
        if re.search(r'\b(inc\.?|llc\.?|corp\.?|corporation|ltd\.?|limited)\s*$', question_lower):
            return False
        
        # Reject "Organizational Documents of..." pattern (common in legal/corporate sections)
        if 'organizational documents' in question_lower or 'articles of incorporation' in question_lower:
            return False
        
        # Reject product names and service names (even if they contain "is", "are", "care", etc.)
        # These are typically short phrases ending with product/service identifiers
        product_patterns = [
            r'roadside assistance\s*\d*$',  # "Roadside Assistance 4"
            r'^\s*\d*-hour roadside',  # "24-Hour Roadside Assistance"
            r'\w+care\s*(plus|service)?',  # Product care services
            r'\w+\s+(auto|service)\s+care$',  # Auto/service care products
            r'coverage\s+exclusions?\s+may\s+apply',  # "Coverage exclusions may apply"
            r'platinum\s+protection$',  # "Platinum Protection"
            r'^\s*cancellation\s*$',  # Just "Cancellation"
        ]
        
        for pattern in product_patterns:
            if re.search(pattern, question_lower, re.I):
                return False
        
        # Reject phrases that end with just a number (likely section headers)
        # Example: "Roadside Assistance 4", "Coverage exclusions may apply: 2"
        if re.search(r'\s+\d+\s*$', question):
            return False
        
        # Reject phrases ending with colon (section headers)
        if question.strip().endswith(':'):
            return False
        
        # Reject imperative commands/instructions (not questions)
        # Examples: "Register Your Account", "Compare Vehicle Service Agreements"
        imperative_patterns = [
            r'^(register|compare|download|upload|submit|contact|call|visit|click|select)\s+',
            r'^agent-assisted\s+',
        ]
        
        for pattern in imperative_patterns:
            if re.search(pattern, question_lower):
                return False
        
        # Reject "What/How to [verb]" without question mark (incomplete questions)
        # Example: "What to expect at the dealer" vs "What should I expect at the dealer?"
        if re.search(r'^(what|how)\s+to\s+\w+', question_lower) and '?' not in question:
            # These are often section headers, not complete questions
            return False
        
        # Reject call-to-action prompts (short questions that are prompts, not info-seeking)
        # Examples: "Ready to file a claim?", "Shopping for a vehicle?", "Looking for more?"
        cta_patterns = [
            r'^ready\s+to\s+',  # "Ready to..."
            r'^shopping\s+for\s+',  # "Shopping for..."
            r'^looking\s+for\s+',  # "Looking for..."
            r'^have\s+questions\??$',  # "Have questions?"
            r'^come\s+challenge\s+',  # "Come challenge..."
            r'^what\s+about\s+you\??',  # "What about you?"
            r'^not\s+sure\s+which\s+',  # "Not Sure Which..."
        ]
        
        for pattern in cta_patterns:
            if re.search(pattern, question_lower):
                return False
        
        # Reject legal disclaimers and policy statements (long sentences without typical question structure)
        if len(words) > 15 and '?' not in question and 'may have' in question_lower:
            return False
        
        # Reject very generic prompts (2-4 words ending with ?)
        # Examples: "Have questions?", "Looking for more?"
        if len(words) <= 4 and question.strip().endswith('?'):
            # Check if it's too generic (doesn't ask for specific information)
            generic_words = ['questions', 'more', 'help', 'info', 'information']
            if any(word in question_lower for word in generic_words) and len(words) <= 3:
                return False
        
        return has_question_indicator
    
    def extract_faqs_from_accordions(self, soup: BeautifulSoup, page_url: str) -> Tuple[List[Dict[str, any]], List[Dict[str, any]]]:
        """Extract FAQs from accordion/FAQ sections."""
        faqs = []
        help_sections = []
        
        # Look for specific FAQ structure first
        question_elements = soup.find_all('p', class_='faq_ques_text')
        for q_elem in question_elements:
            # Get the question text - it's NOT in the link, it's after the link
            # Remove the link element first, then get clean text
            question_link = q_elem.find('a', class_='faq-ques')
            if question_link:
                question_link.decompose()  # Remove the link element
            
            question_text = self.clean_text(q_elem.get_text(), preserve_links=False)
            
            # Validate question
            if not self.is_valid_faq_question(question_text):
                continue
            
            # Look for answer in the next div with faq-ans class
            answer_div = q_elem.find_next('div', class_='faq-ans')
            if answer_div:
                # Get the answer content, preserving lists
                answer_html = str(answer_div)
                answer_text = self.clean_text(answer_html, preserve_links=True)
                
                # Skip if answer is too short
                if len(answer_text) < 20:
                    continue
                
                # Check if this is a "Still need help" section
                if re.search(r'still\s+need\s+help|contact\s+us|need\s+more\s+help', answer_text, re.I):
                    help_sections.append({
                        'section_text': answer_text,
                        'section_html': answer_html,
                        'page_url': page_url
                    })
                    continue
                
                faqs.append({
                    'question': question_text,
                    'answer': answer_text,
                    'answer_mode': self.detect_answer_mode(question_text, answer_text, page_url),
                    'confidence': 0.9  # High confidence for this specific structure
                })
        
        # Look for common FAQ patterns (fallback)
        faq_containers = soup.find_all(['div', 'section', 'article'], 
                                     class_=re.compile(r'faq|accordion|question', re.I))
        
        for container in faq_containers:
            # Look for question-answer pairs
            questions = container.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                                         'div', 'span', 'p'], 
                                         class_=re.compile(r'question|title|header', re.I))
            
            for q_elem in questions:
                # Get the question text
                question_text = self.clean_text(q_elem.get_text())
                
                # Validate question (includes length check)
                if not self.is_valid_faq_question(question_text) or 'btn' in str(q_elem.get('class', [])):
                    continue
                
                # Look for answer in next sibling or following elements
                answer_elem = q_elem.find_next_sibling()
                if not answer_elem:
                    # Look for answer in parent's next sibling
                    parent = q_elem.parent
                    if parent:
                        answer_elem = parent.find_next_sibling()
                
                if answer_elem:
                    # Get answer text with HTML preserved for link extraction
                    answer_html = str(answer_elem)
                    answer_text = self.clean_text(answer_html, preserve_links=True)
                    
                    # Skip if answer is too short or contains mostly HTML
                    if len(answer_text) < 20 or '<' in answer_text and '>' in answer_text:
                        continue
                    
                    # Check if this is a "Still need help" section
                    if re.search(r'still\s+need\s+help|contact\s+us|need\s+more\s+help', answer_text, re.I):
                        help_sections.append({
                            'section_text': answer_text,
                            'section_html': answer_html,
                            'page_url': page_url
                        })
                        continue
                    
                    if len(question_text) > 10 and len(answer_text) > 20:  # Minimum length filter
                        faqs.append({
                            'question': question_text,
                            'answer': answer_text,
                            'answer_mode': self.detect_answer_mode(question_text, answer_text, page_url),
                            'confidence': 0.8
                        })
        
        return faqs, help_sections
    
    def extract_faqs_from_lists(self, soup: BeautifulSoup, page_url: str) -> Tuple[List[Dict[str, any]], List[Dict[str, any]]]:
        """Extract FAQs from definition lists and ordered lists."""
        faqs = []
        help_sections = []
        
        # Check for definition lists (dt/dd)
        dts = soup.find_all('dt')
        for dt in dts:
            dd = dt.find_next_sibling('dd')
            if dd:
                question = self.clean_text(dt.get_text())
                answer_html = str(dd)
                answer = self.clean_text(answer_html, preserve_links=True)
                
                # Check if this is a "Still need help" section
                if re.search(r'still\s+need\s+help|contact\s+us|need\s+more\s+help', answer, re.I):
                    help_sections.append({
                        'section_text': answer,
                        'section_html': answer_html,
                        'page_url': page_url
                    })
                    continue
                
                if self.is_valid_faq_question(question) and len(answer) > 20:
                    faqs.append({
                        'question': question,
                        'answer': answer,
                        'answer_mode': self.detect_answer_mode(question, answer, page_url),
                        'confidence': 0.7
                    })
        
        # Check for ordered lists with Q/A pattern
        ols = soup.find_all('ol')
        for ol in ols:
            items = ol.find_all('li', recursive=False)
            for i, item in enumerate(items):
                text = self.clean_text(item.get_text())
                
                # Try to split question and answer within list item
                for q_pattern in self.question_patterns:
                    if re.match(q_pattern, text):
                        # Remove question pattern
                        question = re.sub(q_pattern, '', text).strip()
                        
                        # Look for answer in next item or following content
                        answer = ""
                        if i + 1 < len(items):
                            next_item = items[i + 1]
                            next_text = self.clean_text(next_item.get_text())
                            for a_pattern in self.answer_patterns:
                                if re.match(a_pattern, next_text):
                                    answer = re.sub(a_pattern, '', next_text).strip()
                                    break
                        
                        if answer and self.is_valid_faq_question(question) and len(answer) > 20:
                            faqs.append({
                                'question': question,
                                'answer': answer,
                                'answer_mode': self.detect_answer_mode(question, answer, page_url),
                                'confidence': 0.6
                            })
                        break
        
        return faqs, help_sections
    
    def extract_faqs_from_headings(self, soup: BeautifulSoup, page_url: str) -> List[Dict[str, any]]:
        """Extract FAQs from heading patterns."""
        faqs = []
        
        # Look for headings followed by paragraphs
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        
        for heading in headings:
            heading_text = self.clean_text(heading.get_text())
            
            # Validate as FAQ question
            if self.is_valid_faq_question(heading_text):
                
                # Look for answer in following elements (including lists)
                answer_elem = heading.find_next_sibling()
                answer_lines: List[str] = []

                while answer_elem and answer_elem.name not in ['h1', 'h2', 'h3']:
                    if answer_elem.name in ['ul', 'ol']:
                        items = answer_elem.find_all('li')
                        for li in items:
                            li_text = self.clean_text(str(li), preserve_links=True)
                            if li_text:
                                answer_lines.append(li_text)
                    elif answer_elem.name in ['p', 'div', 'section', 'h4', 'h5', 'h6']:
                        text = self.clean_text(str(answer_elem), preserve_links=True)
                        if text:
                            answer_lines.append(text)

                    # Collect all meaningful content
                    # Only stop if we hit a new heading or have substantial content
                    if sum(len(x) for x in answer_lines) > 2000:
                        break

                    answer_elem = answer_elem.find_next_sibling()

                answer_text = "\n".join([x for x in answer_lines if x])
                
                if answer_text and len(answer_text) > 20:
                    faqs.append({
                        'question': heading_text,
                        'answer': answer_text,
                        'answer_mode': self.detect_answer_mode(heading_text, answer_text, page_url),
                        'confidence': 0.5
                    })
        
        return faqs
    
    def extract_faqs_from_tables(self, soup: BeautifulSoup, page_url: str) -> List[Dict[str, any]]:
        """Extract FAQs from table structures."""
        faqs = []
        
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                
                if len(cells) >= 2:
                    # Assume first column is question, second is answer
                    question = self.clean_text(cells[0].get_text())
                    answer = self.clean_text(cells[1].get_text())
                    
                    if self.is_valid_faq_question(question) and len(answer) > 20:
                        faqs.append({
                            'question': question,
                            'answer': answer,
                            'answer_mode': self.detect_answer_mode(question, answer, page_url),
                            'confidence': 0.4
                        })
        
        return faqs
    
    def extract_all_faqs(self, html_content: str, page_url: str, page_id: int) -> Tuple[List[Dict[str, any]], List[Dict[str, any]]]:
        """Extract all FAQ pairs and help sections from HTML content using multiple strategies."""
        soup = BeautifulSoup(html_content, 'lxml')
        all_faqs = []
        all_help_sections = []
        
        # Try different extraction strategies
        strategies = [
            ('accordion', self.extract_faqs_from_accordions),
            ('lists', self.extract_faqs_from_lists),
            ('headings', self.extract_faqs_from_headings),
            ('tables', self.extract_faqs_from_tables),
        ]
        
        for strategy_name, strategy_func in strategies:
            try:
                result = strategy_func(soup, page_url)
                if isinstance(result, tuple) and len(result) == 2:
                    faqs, help_sections = result
                    all_faqs.extend(faqs)
                    all_help_sections.extend(help_sections)
                    self.logger.debug(f"Strategy {strategy_name} found {len(faqs)} FAQs")
                else:
                    faqs = result
                    all_faqs.extend(faqs)
                    self.logger.debug(f"Strategy {strategy_name} found {len(faqs) if isinstance(faqs, list) else 0} FAQs")
            except Exception as e:
                self.logger.warning(f"Error in {strategy_name} strategy: {e}")
        
        # Remove duplicates based on normalized question hash
        seen_questions = set()
        unique_faqs = []
        
        for faq in all_faqs:
            normalized_question = self.normalize_question(faq['question'])
            question_hash = self.hash_content(normalized_question)
            if question_hash not in seen_questions:
                seen_questions.add(question_hash)
                # Store the hash in the faq dict for later use
                faq['question_hash'] = question_hash
                unique_faqs.append(faq)
        
        self.logger.info(f"Extracted {len(unique_faqs)} unique FAQs and {len(all_help_sections)} help sections from {page_url}")
        return unique_faqs, all_help_sections
    
    def process_page_content(self, page_id: int, html_content: str, page_url: str) -> Dict[str, any]:
        """Process page content and extract FAQs."""
        # Extract FAQs and help sections
        faqs, help_sections = self.extract_all_faqs(html_content, page_url, page_id)
        
        # Store FAQs in database
        stored_faqs = 0
        for faq in faqs:
            # Use normalized question hash for consistency
            normalized_question = self.normalize_question(faq['question'])
            question_hash = self.hash_content(normalized_question)
            
            faq_data = {
                'page_id': page_id,
                'question': faq['question'],
                'answer': faq['answer'],
                'question_hash': question_hash,
                'answer_hash': self.hash_content(faq['answer']),
                'answer_mode': faq['answer_mode'],
                'link_depth_to_answer': 0,  # Will be updated later
                'confidence_score': faq['confidence']
            }
            
            faq_id = self.db.insert_faq(faq_data)
            if faq_id:
                stored_faqs += 1
        
        # Store help sections (for now, just log them - could be stored in a separate table)
        for help_section in help_sections:
            self.logger.info(f"Found help section: {help_section['section_text'][:100]}...")
        
        # Extract clean text for RAG
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script, style, and navigation elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()
        
        clean_text = self.clean_text(soup.get_text())
        
        # Save cleaned text
        url_hash = hashlib.md5(page_url.encode()).hexdigest()
        clean_text_path = Path(self.config.processed_dir) / f"{url_hash}_clean.txt"
        
        with open(clean_text_path, 'w', encoding='utf-8') as f:
            f.write(clean_text)
        
        # Update page record
        with self.db._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pages 
                SET cleaned_text_path = ?, extraction_status = 'completed'
                WHERE id = ?
            """, (str(clean_text_path), page_id))
            conn.commit()
        
        return {
            'faqs_extracted': stored_faqs,
            'clean_text_path': str(clean_text_path),
            'clean_text_length': len(clean_text)
        }


class ContentProcessor:
    """Main content processing coordinator."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.faq_extractor = FAQExtractor(config, db_manager)
        self.logger = logging.getLogger(__name__)
    
    def process_all_pages(self) -> Dict[str, any]:
        """Process all crawled pages for content extraction."""
        self.logger.info("Starting content processing for all pages")

        with self.db._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, url, raw_html_path 
                FROM pages 
                WHERE extraction_status = 'completed' 
                AND raw_html_path IS NOT NULL
            """)
            pages = cursor.fetchall()

        total_faqs = 0
        processed_pages = 0

        for page_id, url, raw_html_path in pages:
            try:
                with open(raw_html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                result = self.faq_extractor.process_page_content(page_id, html_content, url)
                total_faqs += result['faqs_extracted']
                processed_pages += 1
                self.logger.debug(f"Processed {url}: {result['faqs_extracted']} FAQs")

            except Exception as e:
                self.logger.error(f"Error processing page {url}: {e}")

                # Mark as failed using a short-lived connection
                try:
                    with self.db._connect() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE pages 
                            SET extraction_status = 'failed', extraction_error = ?
                            WHERE id = ?
                        """, (str(e), page_id))
                        conn.commit()
                except Exception as inner_e:
                    self.logger.error(f"Error marking page failed {url}: {inner_e}")
        
        processing_summary = {
            'pages_processed': processed_pages,
            'total_faqs_extracted': total_faqs,
            'avg_faqs_per_page': total_faqs / processed_pages if processed_pages > 0 else 0
        }
        
        self.logger.info(f"Content processing completed: {processing_summary}")
        return processing_summary
