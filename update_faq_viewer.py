"""
Update faq_viewer.db with current data from faq_scraper.db
Maintains the format: id, question, answer, answer_mode, source_url
"""

import sqlite3
from pathlib import Path

def update_faq_viewer():
    """Update faq_viewer.db with current FAQs from faq_scraper.db"""
    
    # Database paths
    scraper_db = Path("data/faq_scraper.db")
    viewer_db = Path("data/faq_viewer.db")
    
    if not scraper_db.exists():
        print(f"Error: {scraper_db} not found")
        return
    
    # Connect to both databases
    scraper_conn = sqlite3.connect(scraper_db)
    viewer_conn = sqlite3.connect(viewer_db)
    
    try:
        # Get FAQs with their source URLs from the main database
        query = """
            SELECT 
                f.id,
                f.question,
                f.answer,
                f.answer_mode,
                p.url as source_url
            FROM faqs f
            JOIN pages p ON f.page_id = p.id
            ORDER BY f.id
        """
        
        scraper_cursor = scraper_conn.cursor()
        scraper_cursor.execute(query)
        faqs = scraper_cursor.fetchall()
        
        print(f"Found {len(faqs)} FAQs in faq_scraper.db")
        
        # Clear existing data in faq_viewer
        viewer_cursor = viewer_conn.cursor()
        viewer_cursor.execute("DELETE FROM faqs_view")
        print("Cleared existing data from faqs_view")
        
        # Insert updated data
        viewer_cursor.executemany("""
            INSERT INTO faqs_view (id, question, answer, answer_mode, source_url)
            VALUES (?, ?, ?, ?, ?)
        """, faqs)
        
        viewer_conn.commit()
        
        # Verify the update
        viewer_cursor.execute("SELECT COUNT(*) FROM faqs_view")
        count = viewer_cursor.fetchone()[0]
        print(f"Successfully updated faq_viewer.db with {count} FAQs")
        
        # Show answer_mode distribution
        viewer_cursor.execute("""
            SELECT answer_mode, COUNT(*) 
            FROM faqs_view 
            GROUP BY answer_mode
        """)
        distribution = viewer_cursor.fetchall()
        
        print("\nAnswer Mode Distribution:")
        for mode, count in distribution:
            print(f"  {mode}: {count}")
        
    except Exception as e:
        print(f"Error updating faq_viewer: {e}")
        viewer_conn.rollback()
    finally:
        scraper_conn.close()
        viewer_conn.close()

if __name__ == "__main__":
    update_faq_viewer()
