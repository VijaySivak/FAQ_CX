"""
Extract missed FAQs from specific pages and append to database.
This script targets pages that were crawled but had 0 FAQs extracted.
"""

import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.content_extractor import FAQExtractor
from src.config import Config
from src.database import DatabaseManager

def extract_missed_faqs():
    """Extract FAQs from pages that should have content but don't."""
    
    # Initialize
    config = Config()
    db_path = config.db_path
    db = DatabaseManager(db_path)
    extractor = FAQExtractor(config, db)
    
    # Connect to database
    db_path = Path('./data/faq_scraper.db')
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # Get the current max FAQ ID to know where new FAQs start
    cur.execute("SELECT MAX(id) FROM faqs")
    max_id_before = cur.fetchone()[0] or 0
    
    print(f"📊 Current FAQ count: {max_id_before}")
    print(f"🔍 Finding pages with 0 FAQs that should have content...\n")
    
    # Get pages that:
    # 1. Have raw HTML
    # 2. Have extraction_status = 'completed'
    # 3. Have 0 FAQs extracted
    # 4. Are individual FAQ pages (contain '/faq/' in URL)
    cur.execute("""
        SELECT p.id, p.url, p.raw_html_path
        FROM pages p
        LEFT JOIN (
            SELECT page_id, COUNT(*) as faq_count
            FROM faqs
            GROUP BY page_id
        ) f ON p.id = f.page_id
        WHERE p.extraction_status = 'completed'
        AND p.raw_html_path IS NOT NULL
        AND (f.faq_count IS NULL OR f.faq_count = 0)
        AND (p.url LIKE '%/faq/%' OR p.url LIKE '%/faqs.html')
        ORDER BY p.id
    """)
    
    pages_to_process = cur.fetchall()
    
    print(f"Found {len(pages_to_process)} pages to process\n")
    
    total_extracted = 0
    pages_with_faqs = 0
    
    for page_id, url, html_path in pages_to_process:
        if not Path(html_path).exists():
            continue
        
        # Read HTML
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Extract FAQs
        faqs, help_sections = extractor.extract_all_faqs(html_content, url, page_id)
        
        if faqs:
            pages_with_faqs += 1
            total_extracted += len(faqs)
            
            print(f"✓ {url.split('/')[-1][:60]}")
            print(f"  Extracted {len(faqs)} FAQ(s)")
            
            # Insert FAQs into database (allow duplicates for business metrics)
            for faq in faqs:
                # Generate unique hash including page_id to allow duplicates across pages
                import hashlib
                import time
                unique_hash = hashlib.md5(f"{faq['question']}_{page_id}_{time.time()}".encode()).hexdigest()
                
                cur.execute("""
                    INSERT INTO faqs (
                        page_id, question, answer, answer_mode, 
                        confidence_score, link_depth_to_answer, question_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    page_id,
                    faq['question'],
                    faq['answer'],
                    faq['answer_mode'],
                    faq.get('confidence', 0.8),
                    faq.get('link_depth_to_answer', 0),
                    unique_hash  # Unique hash to bypass UNIQUE constraint
                ))
            
            conn.commit()
    
    # Get new FAQ IDs
    cur.execute("SELECT MAX(id) FROM faqs")
    max_id_after = cur.fetchone()[0] or 0
    
    new_faqs_count = max_id_after - max_id_before
    
    print(f"\n{'='*60}")
    print(f"✅ Extraction Complete")
    print(f"{'='*60}")
    print(f"Pages processed: {len(pages_to_process)}")
    print(f"Pages with FAQs: {pages_with_faqs}")
    print(f"Total FAQs extracted: {total_extracted}")
    print(f"New FAQ IDs: {max_id_before + 1} to {max_id_after}")
    print(f"\n📊 Final FAQ count: {max_id_after}")
    
    # Show sample of newly extracted FAQs
    if new_faqs_count > 0:
        print(f"\n📋 Sample of newly extracted FAQs:")
        cur.execute("""
            SELECT id, question 
            FROM faqs 
            WHERE id > ? 
            ORDER BY id 
            LIMIT 10
        """, (max_id_before,))
        
        for faq_id, question in cur.fetchall():
            print(f"  {faq_id:4d}. {question[:70]}")
    
    conn.close()
    
    return new_faqs_count

if __name__ == "__main__":
    try:
        new_count = extract_missed_faqs()
        print(f"\n✅ Successfully extracted {new_count} new FAQs")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
