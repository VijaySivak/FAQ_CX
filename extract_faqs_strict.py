#!/usr/bin/env python3
"""
Extract FAQs with stricter filtering to match the correct database.
"""

import sqlite3
from pathlib import Path
import sys
import hashlib
import re

sys.path.insert(0, str(Path(__file__).parent))
from src.content_extractor import FAQExtractor
from src.config import Config
from src.database import DatabaseManager

def extract_faqs_strict():
    """Extract FAQs with stricter filtering."""
    
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
    
    # Override the validation to be stricter
    original_is_valid = extractor.is_valid_faq_question
    
    def is_strict_faq_question(question: str) -> bool:
        """Stricter validation for FAQ questions."""
        if not original_is_valid(question):
            return False
        
        # Must be at least 15 characters
        if len(question) < 15:
            return False
        
        # Must end with a question mark or be a clear question
        question_lower = question.lower()
        
        # Must start with a question word
        question_starters = ['what', 'how', 'when', 'where', 'why', 'who', 'which', 'can', 'do', 'does', 'is', 'are', 'will', 'should', 'may', 'if']
        starts_with_question = any(question_lower.startswith(word) for word in question_starters)
        
        if not starts_with_question and not question.endswith('?'):
            return False
        
        # Reject very specific sub-questions
        sub_question_patterns = [
            r'once i have',
            r'after i have',
            r'if i already',
            r'how do i (enable|disable|add|remove|set|reset)',
            r'what (if|should|happens|do) i',
            r'where (is|do|can) i',
            r'which (.*) (compatible|devices)',
            r'are there fees',
            r'do i have to',
            r'can i (use|make|get|buy|claim|attach)',
        ]
        
        # Allow these patterns only if they're the main question (not sub-questions)
        for pattern in sub_question_patterns:
            if re.search(pattern, question_lower, re.I):
                # Only allow if it's a substantial question (not a sub-question)
                if len(question.split()) < 8:
                    return False
        
        return True
    
    # Replace the validation method
    extractor.is_valid_faq_question = is_strict_faq_question
    
    for page_id, url, html_path in pages:
        if not Path(html_path).exists():
            continue
        
        try:
            # Read HTML
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Extract FAQs using only accordion strategy with strict filtering
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'lxml')
            faqs, help_sections = extractor.extract_faqs_from_accordions(soup, url)
            
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
        count = extract_faqs_strict()
        print(f"\n✅ Successfully extracted {count} FAQs with strict filtering")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
