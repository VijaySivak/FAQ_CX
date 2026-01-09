#!/usr/bin/env python3
"""
Rebuild FAQ database with proper crawling strategy:
1. planning_tools: Topic → FAQ List → Individual Q&A pages (depth 3 if deferred)
2. end_of_lease: Questions on page + accordion answers (depth 3 if deferred)
"""

import sqlite3
from pathlib import Path
import sys
import hashlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re

sys.path.insert(0, str(Path(__file__).parent))
from src.content_extractor import FAQExtractor
from src.config import Config
from src.database import DatabaseManager

def rebuild_faqs_properly():
    """Rebuild FAQs with proper crawling and extraction strategy."""
    
    # Initialize
    config = Config()
    db = DatabaseManager(config.db_path)
    extractor = FAQExtractor(config, db)
    
    conn = sqlite3.connect('./data/faq_scraper.db')
    cur = conn.cursor()
    
    # Clear existing FAQs
    cur.execute("DELETE FROM faqs")
    conn.commit()
    print("Cleared all existing FAQs")
    
    # Get all pages
    cur.execute("""
        SELECT id, url, raw_html_path
        FROM pages
        WHERE raw_html_path IS NOT NULL
        AND extraction_status = 'completed'
        ORDER BY id
    """)
    
    pages = cur.fetchall()
    print(f"Processing {len(pages)} pages...")
    
    total_faqs = 0
    pages_with_faqs = 0
    
    for page_id, url, html_path in pages:
        if not Path(html_path).exists():
            continue
        
        try:
            # Read HTML
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Extract FAQs based on URL pattern
            faqs = []
            
            if '/understanding_credit/' in url or '/financing_options/' in url:
                # Strategy 3: Content pages with questions as headings
                faqs = extract_from_content_page(html_content, url, extractor)
            
            elif '/planning_tools/faq/' in url:
                # Strategy 1: planning_tools
                if url.count('/') >= 6:  # Individual FAQ page (e.g., /topic/subtopic/question.html)
                    faqs = extract_from_individual_faq_page(html_content, url, extractor)
                elif url.endswith('.html') and url.count('/') == 5:  # FAQ listing page
                    faqs = extract_from_faq_listing_page(html_content, url, extractor)
                    
            elif '/end_of_lease_options/' in url:
                # Strategy 2: end_of_lease - questions on page with accordion answers
                faqs = extract_from_lease_page(html_content, url, extractor)
            
            if faqs:
                pages_with_faqs += 1
                total_faqs += len(faqs)
                
                # Insert FAQs into database
                for faq in faqs:
                    # Use normalized question hash for consistency
                    normalized_question = extractor.normalize_question(faq['question'])
                    question_hash = extractor.hash_content(normalized_question)
                    
                    cur.execute("""
                        INSERT INTO faqs (
                            page_id, question, answer, answer_mode, 
                            confidence_score, link_depth_to_answer, question_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(page_id, question_hash) DO UPDATE SET
                            page_id = excluded.page_id,
                            question = excluded.question,
                            answer = excluded.answer,
                            answer_mode = excluded.answer_mode,
                            confidence_score = excluded.confidence_score,
                            link_depth_to_answer = excluded.link_depth_to_answer
                    """, (
                        page_id,
                        faq['question'],
                        faq['answer'],
                        faq['answer_mode'],
                        faq.get('confidence', 0.8),
                        faq.get('link_depth_to_answer', 0),
                        question_hash
                    ))
                
                conn.commit()
                print(f"✓ Page {page_id} ({url}): {len(faqs)} FAQs")
        
        except Exception as e:
            print(f"✗ Error processing page {page_id}: {e}")
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"✅ Extraction Complete")
    print(f"{'='*60}")
    print(f"Pages processed: {len(pages)}")
    print(f"Pages with FAQs: {pages_with_faqs}")
    print(f"Total FAQs extracted: {total_faqs}")
    
    return total_faqs

def extract_from_individual_faq_page(html_content: str, url: str, extractor) -> list:
    """Extract FAQ from individual FAQ page."""
    faqs = []
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Look for the specific FAQ structure
    question_elem = soup.find('p', class_='faq_ques_text')
    if question_elem:
        # Remove the link element if present
        link = question_elem.find('a', class_='faq-ques')
        if link:
            link.decompose()
        
        question = extractor.clean_text(question_elem.get_text())
        
        # Find the answer
        answer_div = soup.find('div', class_='faq-ans')
        if answer_div:
            answer_html = str(answer_div)
            answer = extractor.clean_text(answer_html, preserve_links=True)
            
            # Validate the FAQ
            if extractor.is_valid_faq_question(question) and len(answer) > 20:
                faqs.append({
                    'question': question,
                    'answer': answer,
                    'answer_mode': extractor.detect_answer_mode(question, answer, url),
                    'confidence': 0.9
                })
    
    return faqs

def extract_from_faq_listing_page(html_content: str, url: str, extractor) -> list:
    """Extract FAQ links from listing page - these don't have answers yet."""
    # This is just for finding links, not extracting FAQs
    # The actual FAQs will be extracted from individual pages
    return []

def extract_from_lease_page(html_content: str, url: str, extractor) -> list:
    """Extract FAQs from lease pages with questions and accordion answers."""
    faqs = []
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Look for accordion-card pattern
    accordion_cards = soup.find_all('div', class_='accordion-card')
    
    for card in accordion_cards:
        # Find the question in the button/div
        question_elem = card.find('div')
        if question_elem:
            question = extractor.clean_text(question_elem.get_text())
            
            # Find the answer in the collapse div
            collapse_div = card.find('div', class_='collapse')
            if collapse_div:
                answer_div = collapse_div.find('div', class_='card-body')
                if answer_div:
                    answer_html = str(answer_div)
                    answer = extractor.clean_text(answer_html, preserve_links=True)
                    
                    # Validate the FAQ
                    if extractor.is_valid_faq_question(question) and len(answer) > 20:
                        faqs.append({
                            'question': question,
                            'answer': answer,
                            'answer_mode': extractor.detect_answer_mode(question, answer, url),
                            'confidence': 0.8
                        })
    
    # Also look for questions in headings followed by content
    # This catches cases where questions are h3/h4 tags
    headings = soup.find_all(['h3', 'h4'])
    for heading in headings:
        question = extractor.clean_text(heading.get_text())
        
        # Check if it's a valid question
        if extractor.is_valid_faq_question(question):
            # Get all content until next heading or end
            content = []
            next_elem = heading.next_sibling
            
            while next_elem:
                if next_elem.name in ['h3', 'h4']:
                    break
                if hasattr(next_elem, 'get_text'):
                    text = extractor.clean_text(next_elem.get_text())
                    if text:
                        content.append(text)
                next_elem = next_elem.next_sibling
            
            answer = '\n'.join(content)
            
            if len(answer) > 20:
                faqs.append({
                    'question': question,
                    'answer': answer,
                    'answer_mode': extractor.detect_answer_mode(question, answer, url),
                    'confidence': 0.7
                })
    
    return faqs

def extract_from_content_page(html_content: str, url: str, extractor) -> list:
    """Extract FAQs from content pages where questions are in headings."""
    faqs = []
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Look for questions in headings followed by content
    headings = soup.find_all(['h2', 'h3', 'h4'])
    for heading in headings:
        question = extractor.clean_text(heading.get_text())
        
        # Check if it's a valid question
        if extractor.is_valid_faq_question(question):
            # Get all content until next heading of same or higher level
            content = []
            next_elem = heading.next_sibling
            
            while next_elem:
                # Stop if we hit a heading of the same or higher level
                if next_elem.name in ['h2', 'h3', 'h4']:
                    # Compare levels
                    current_level = int(heading.name[1])
                    next_level = int(next_elem.name[1])
                    if next_level <= current_level:
                        break
                
                if hasattr(next_elem, 'get_text'):
                    text = extractor.clean_text(next_elem.get_text())
                    if text:
                        content.append(text)
                next_elem = next_elem.next_sibling
            
            answer = '\n'.join(content)
            
            if len(answer) > 20:
                faqs.append({
                    'question': question,
                    'answer': answer,
                    'answer_mode': extractor.detect_answer_mode(question, answer, url),
                    'confidence': 0.7
                })
    
    return faqs

if __name__ == "__main__":
    try:
        count = rebuild_faqs_properly()
        print(f"\n✅ Successfully extracted {count} FAQs with proper strategy")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
