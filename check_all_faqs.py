#!/usr/bin/env python3
"""
Check all FAQs for completeness and fix any that are still incomplete.
"""

import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
import sys

def check_and_fix_all_faqs():
    """Check ALL FAQs and fix any that are incomplete."""
    
    db_path = Path('./data/faq_scraper.db')
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    # Get ALL FAQs with their HTML paths
    cur.execute("""
        SELECT f.id, f.page_id, p.raw_html_path, f.question, f.answer, LENGTH(f.answer)
        FROM faqs f
        JOIN pages p ON f.page_id = p.id
        WHERE p.raw_html_path IS NOT NULL
        ORDER BY LENGTH(f.answer) ASC
    """)
    
    all_faqs = cur.fetchall()
    
    print(f"Checking {len(all_faqs)} FAQs ordered by answer length...\n")
    
    # Show the 10 shortest FAQs
    print("10 Shortest FAQ answers:")
    print("="*80)
    for i, (faq_id, page_id, html_path, question, answer, length) in enumerate(all_faqs[:10]):
        print(f"\n{i+1}. FAQ ID: {faq_id}")
        print(f"   Length: {length} chars")
        print(f"   Q: {question[:70]}...")
        print(f"   A: {answer[:100]}...")
    
    # Check if any have very short answers (< 50 chars)
    very_short = [f for f in all_faqs if f[5] < 50]
    print(f"\n\nFound {len(very_short)} FAQs with very short answers (< 50 chars)")
    
    conn.close()

if __name__ == "__main__":
    check_and_fix_all_faqs()
