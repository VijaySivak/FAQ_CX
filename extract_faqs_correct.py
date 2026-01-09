#!/usr/bin/env python3
"""
Extract FAQs using the correct pattern to match the correct database.
"""

import sqlite3
from pathlib import Path
import sys
import hashlib
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from src.content_extractor import FAQExtractor
from src.config import Config
from src.database import DatabaseManager

def extract_faqs_correct_pattern():
    """Extract FAQs using the correct HTML pattern."""
    
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
    
    # Get all pages with HTML
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
            
            # Extract FAQs using the correct pattern
            soup = BeautifulSoup(html_content, 'lxml')
            faqs = []
            
            # Look for accordion-card pattern (the correct one)
            accordion_cards = soup.find_all('div', class_='accordion-card')
            
            for card in accordion_cards:
                # Find the question in the button div
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
                print(f"✓ Page {page_id}: {len(faqs)} FAQs")
        
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

if __name__ == "__main__":
    try:
        count = extract_faqs_correct_pattern()
        print(f"\n✅ Successfully extracted {count} FAQs using correct pattern")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
