"""
Export faq_viewer.db to a CSV spreadsheet
"""

import sqlite3
import csv
from pathlib import Path

def export_faq_viewer_to_csv():
    """Export faq_viewer.db to CSV format"""
    
    viewer_db = Path("data/faq_viewer.db")
    output_csv = Path("faq_viewer_export.csv")
    
    if not viewer_db.exists():
        print(f"Error: {viewer_db} not found")
        return
    
    conn = sqlite3.connect(viewer_db)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, question, answer, answer_mode, source_url
            FROM faqs_view
            ORDER BY id
        """)
        
        rows = cursor.fetchall()
        
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            writer.writerow(['ID', 'Question', 'Answer', 'Answer Mode', 'Source URL'])
            
            writer.writerows(rows)
        
        print(f"Successfully exported {len(rows)} FAQs to {output_csv}")
        print(f"File saved at: {output_csv.absolute()}")
        
    except Exception as e:
        print(f"Error exporting data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_faq_viewer_to_csv()
