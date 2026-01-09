#!/usr/bin/env python3
"""
Rebuild ALL FAQs by re-extracting from HTML to fix corrupted answers.
"""

import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
import sys
import hashlib
import time

sys.path.insert(0, str(Path(__file__).parent))
from src.content_extractor import FAQExtractor
from src.config import Config
from src.database import DatabaseManager

def rebuild_all_faqs():
    """Rebuild ALL FAQs from HTML to fix corrupted answers."""
    
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
            
            # Extract FAQs
            faqs, help_sections = extractor.extract_all_faqs(html_content, url, page_id)
            
            if faqs:
                pages_with_faqs += 1
                total_faqs += len(faqs)
                
                # Insert FAQs into database using the proper deduplication
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
    print(f"✅ Rebuild Complete")
    print(f"{'='*60}")
    print(f"Pages processed: {len(pages)}")
    print(f"Pages with FAQs: {pages_with_faqs}")
    print(f"Total FAQs extracted: {total_faqs}")
    
    return total_faqs

if __name__ == "__main__":
    try:
        count = rebuild_all_faqs()
        print(f"\n✅ Successfully rebuilt {count} FAQs")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
