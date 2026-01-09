"""
SQLite database schema and operations for FAQ Scraper.
Stores all raw content, metadata, and metrics for analysis.
"""

import sqlite3
import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path


class DatabaseManager:
    """Manages SQLite database operations for the FAQ scraper."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _with_retry(self, fn, *, max_attempts: int = 5):
        attempt = 0
        while True:
            try:
                return fn()
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if 'locked' not in msg:
                    raise
                attempt += 1
                if attempt >= max_attempts:
                    raise
                time.sleep(0.2 * (2 ** (attempt - 1)))
    
    def init_database(self):
        """Initialize all database tables with required schema."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript("""
                -- Pages table - stores all crawled pages
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT,
                    depth INTEGER NOT NULL,
                    parent_url TEXT,
                    is_internal BOOLEAN NOT NULL,
                    content_type TEXT NOT NULL,
                    status_code INTEGER,
                    crawl_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    raw_html_path TEXT,
                    cleaned_text_path TEXT,
                    word_count INTEGER,
                    internal_links INTEGER DEFAULT 0,
                    external_links INTEGER DEFAULT 0,
                    phone_numbers TEXT, -- JSON array
                    email_addresses TEXT, -- JSON array
                    extraction_status TEXT DEFAULT 'pending',
                    extraction_error TEXT
                );

                -- FAQs table - stores extracted FAQ pairs
                CREATE TABLE IF NOT EXISTS faqs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    question_hash TEXT,
                    answer_hash TEXT,
                    answer_mode TEXT NOT NULL, -- DIRECT_TEXT, LINK_OUT, PHONE_ESCALATION, PDF_ATTACHMENT, VIDEO, PORTAL_REDIRECT
                    link_depth_to_answer INTEGER DEFAULT 0,
                    confidence_score REAL DEFAULT 0.0,
                    FOREIGN KEY (page_id) REFERENCES pages (id),
                    UNIQUE(page_id, question_hash)  -- Unique per page, not globally
                );

                -- PDFs table - stores PDF metadata and content
                CREATE TABLE IF NOT EXISTS pdfs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT,
                    source_page_id INTEGER,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    page_count INTEGER,
                    extracted_text_path TEXT,
                    extraction_status TEXT DEFAULT 'pending',
                    extraction_error TEXT,
                    download_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_page_id) REFERENCES pages (id)
                );

                -- Videos table - stores video metadata and transcriptions
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_url TEXT,
                    source_page_id INTEGER,
                    video_url TEXT NOT NULL,
                    title TEXT,
                    duration_seconds INTEGER,
                    file_path TEXT,
                    subtitle_path TEXT,
                    transcription_path TEXT,
                    has_subtitles BOOLEAN DEFAULT FALSE,
                    transcription_method TEXT, -- subtitle, whisper
                    extraction_status TEXT DEFAULT 'pending',
                    extraction_error TEXT,
                    download_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_page_id) REFERENCES pages (id)
                );

                -- Links table - tracks all discovered and followed links
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_page_id INTEGER NOT NULL,
                    to_url TEXT NOT NULL,
                    link_text TEXT,
                    is_internal BOOLEAN NOT NULL,
                    is_followed BOOLEAN DEFAULT FALSE,
                    follow_depth INTEGER,
                    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_page_id) REFERENCES pages (id)
                );

                -- Content blocks table - stores processed text chunks for RAG
                CREATE TABLE IF NOT EXISTS content_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL, -- page, pdf, video
                    source_id INTEGER NOT NULL,
                    block_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT UNIQUE,
                    metadata TEXT, -- JSON with additional context
                    embedding_vector BLOB, -- FAISS vector stored as blob
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES pages (id)
                );

                -- Metrics table - stores computed metrics snapshots
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_pages INTEGER,
                    total_faqs INTEGER,
                    total_pdfs INTEGER,
                    total_videos INTEGER,
                    direct_answer_percentage REAL,
                    phone_escalation_percentage REAL,
                    pdf_attachment_percentage REAL,
                    video_percentage REAL,
                    avg_click_depth_to_answer REAL,
                    internal_link_percentage REAL,
                    external_link_percentage REAL,
                    extraction_success_rate REAL,
                    content_blocks_processed INTEGER,
                    unique_domains INTEGER
                );

                -- Crawl queue table - manages BFS crawling
                CREATE TABLE IF NOT EXISTS crawl_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    depth INTEGER NOT NULL,
                    parent_url TEXT,
                    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
                    priority INTEGER DEFAULT 0,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processed_at DATETIME
                );

                -- Create indexes for performance
                CREATE INDEX IF NOT EXISTS idx_pages_url ON pages(url);
                CREATE INDEX IF NOT EXISTS idx_pages_depth ON pages(depth);
                CREATE INDEX IF NOT EXISTS idx_pages_status ON pages(extraction_status);
                CREATE INDEX IF NOT EXISTS idx_faqs_page_id ON faqs(page_id);
                CREATE INDEX IF NOT EXISTS idx_faqs_answer_mode ON faqs(answer_mode);
                CREATE INDEX IF NOT EXISTS idx_links_from_page ON links(from_page_id);
                CREATE INDEX IF NOT EXISTS idx_links_internal ON links(is_internal);
                CREATE INDEX IF NOT EXISTS idx_content_blocks_source ON content_blocks(source_type, source_id);
                CREATE INDEX IF NOT EXISTS idx_crawl_queue_status ON crawl_queue(status);
                CREATE INDEX IF NOT EXISTS idx_crawl_queue_depth ON crawl_queue(depth);
            """)
    
    def add_to_crawl_queue(self, urls: List[str], depth: int, parent_url: Optional[str] = None) -> List[int]:
        """Add URLs to the crawl queue for BFS processing."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                inserted_ids = []
                
                for url in urls:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO crawl_queue (url, depth, parent_url, priority)
                            VALUES (?, ?, ?, ?)
                        """, (url, depth, parent_url, -depth))  # Negative priority for BFS (shallower first)
                        
                        if cursor.lastrowid:
                            inserted_ids.append(cursor.lastrowid)
                    except sqlite3.Error as e:
                        print(f"Error adding URL to queue: {e}")
                
                conn.commit()
                return inserted_ids

        return self._with_retry(_op)
    
    def get_next_crawl_urls(self, batch_size: int = 10) -> List[Dict[str, Any]]:
        """Get next batch of URLs to crawl (BFS order)."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE crawl_queue 
                SET status = 'processing' 
                WHERE id IN (
                    SELECT id FROM crawl_queue 
                    WHERE status = 'pending' 
                    ORDER BY priority ASC, added_at ASC 
                    LIMIT ?
                )
            """, (batch_size,))
            
            cursor.execute("""
                SELECT id, url, depth, parent_url 
                FROM crawl_queue 
                WHERE status = 'processing' 
                ORDER BY priority ASC, added_at ASC
            """)
            
            return [
                {
                    'id': row[0],
                    'url': row[1], 
                    'depth': row[2],
                    'parent_url': row[3]
                }
                for row in cursor.fetchall()
            ]
    
    def mark_crawl_completed(self, queue_id: int, status: str = 'completed'):
        """Mark a crawl queue item as completed or failed."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE crawl_queue 
                    SET status = ?, processed_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (status, queue_id))
                conn.commit()

        self._with_retry(_op)
    
    def insert_page(self, page_data: Dict[str, Any]) -> int:
        """Insert a new page record."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO pages (
                        url, title, depth, parent_url, is_internal, content_type,
                        status_code, raw_html_path, cleaned_text_path, word_count,
                        internal_links, external_links, phone_numbers, email_addresses,
                        extraction_status, extraction_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    page_data.get('url'),
                    page_data.get('title'),
                    page_data.get('depth'),
                    page_data.get('parent_url'),
                    page_data.get('is_internal', True),
                    page_data.get('content_type', 'text/html'),
                    page_data.get('status_code'),
                    page_data.get('raw_html_path'),
                    page_data.get('cleaned_text_path'),
                    page_data.get('word_count'),
                    page_data.get('internal_links', 0),
                    page_data.get('external_links', 0),
                    json.dumps(page_data.get('phone_numbers', [])),
                    json.dumps(page_data.get('email_addresses', [])),
                    page_data.get('extraction_status', 'pending'),
                    page_data.get('extraction_error')
                ))
                return cursor.lastrowid

        return self._with_retry(_op)
    
    def insert_faq(self, faq_data: Dict[str, Any]) -> int:
        """Insert a new FAQ record."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO faqs (
                        page_id, question, answer, question_hash, answer_hash,
                        answer_mode, link_depth_to_answer, confidence_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(page_id, question_hash) DO UPDATE SET
                        question = excluded.question,
                        answer = excluded.answer,
                        answer_hash = excluded.answer_hash,
                        answer_mode = excluded.answer_mode,
                        link_depth_to_answer = excluded.link_depth_to_answer,
                        confidence_score = excluded.confidence_score
                """, (
                    faq_data.get('page_id'),
                    faq_data.get('question'),
                    faq_data.get('answer'),
                    faq_data.get('question_hash'),
                    faq_data.get('answer_hash'),
                    faq_data.get('answer_mode', 'DIRECT_TEXT'),
                    faq_data.get('link_depth_to_answer', 0),
                    faq_data.get('confidence_score', 0.0)
                ))
                return cursor.lastrowid

        return self._with_retry(_op)
    
    def insert_pdf(self, pdf_data: Dict[str, Any]) -> int:
        """Insert a new PDF record."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO pdfs (
                        source_url, source_page_id, filename, file_path, file_size,
                        page_count, extracted_text_path, extraction_status, extraction_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pdf_data.get('source_url'),
                    pdf_data.get('source_page_id'),
                    pdf_data.get('filename'),
                    pdf_data.get('file_path'),
                    pdf_data.get('file_size'),
                    pdf_data.get('page_count'),
                    pdf_data.get('extracted_text_path'),
                    pdf_data.get('extraction_status', 'pending'),
                    pdf_data.get('extraction_error')
                ))
                return cursor.lastrowid

        return self._with_retry(_op)
    
    def insert_video(self, video_data: Dict[str, Any]) -> int:
        """Insert a new video record."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO videos (
                        source_url, source_page_id, video_url, title, duration_seconds,
                        file_path, subtitle_path, transcription_path, has_subtitles,
                        transcription_method, extraction_status, extraction_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    video_data.get('source_url'),
                    video_data.get('source_page_id'),
                    video_data.get('video_url'),
                    video_data.get('title'),
                    video_data.get('duration_seconds'),
                    video_data.get('file_path'),
                    video_data.get('subtitle_path'),
                    video_data.get('transcription_path'),
                    video_data.get('has_subtitles', False),
                    video_data.get('transcription_method'),
                    video_data.get('extraction_status', 'pending'),
                    video_data.get('extraction_error')
                ))
                return cursor.lastrowid

        return self._with_retry(_op)
    
    def insert_links(self, links_data: List[Dict[str, Any]]):
        """Insert multiple link records."""
        def _op():
            with self._connect() as conn:
                cursor = conn.cursor()
                for link in links_data:
                    cursor.execute("""
                        INSERT OR IGNORE INTO links (
                            from_page_id, to_url, link_text, is_internal, is_followed, follow_depth
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        link.get('from_page_id'),
                        link.get('to_url'),
                        link.get('link_text'),
                        link.get('is_internal', True),
                        link.get('is_followed', False),
                        link.get('follow_depth')
                    ))
                conn.commit()

        self._with_retry(_op)
    
    def get_crawl_statistics(self) -> Dict[str, Any]:
        """Get current crawl statistics."""
        with self._connect() as conn:
            cursor = conn.cursor()
            
            # Basic counts
            cursor.execute("SELECT COUNT(*) FROM pages WHERE extraction_status = 'completed'")
            pages_completed = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM faqs")
            total_faqs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM pdfs WHERE extraction_status = 'completed'")
            pdfs_completed = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos WHERE extraction_status = 'completed'")
            videos_completed = cursor.fetchone()[0]
            
            # Answer mode distribution
            cursor.execute("""
                SELECT answer_mode, COUNT(*) 
                FROM faqs 
                GROUP BY answer_mode
            """)
            answer_modes = dict(cursor.fetchall())
            
            return {
                'pages_completed': pages_completed,
                'total_faqs': total_faqs,
                'pdfs_completed': pdfs_completed,
                'videos_completed': videos_completed,
                'answer_modes': answer_modes
            }
    
    def compute_metrics(self) -> Dict[str, Any]:
        """Compute comprehensive metrics for CX analysis."""
        with self._connect() as conn:
            cursor = conn.cursor()
            
            # Total counts
            cursor.execute("SELECT COUNT(*) FROM pages")
            total_pages = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM faqs")
            total_faqs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM pdfs")
            total_pdfs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM videos")
            total_videos = cursor.fetchone()[0]
            
            # Answer mode percentages
            if total_faqs > 0:
                cursor.execute("""
                    SELECT answer_mode, COUNT(*) 
                    FROM faqs 
                    GROUP BY answer_mode
                """)
                mode_counts = dict(cursor.fetchall())
                
                direct_answer_pct = (mode_counts.get('DIRECT_TEXT', 0) / total_faqs) * 100
                phone_escalation_pct = (mode_counts.get('PHONE_ESCALATION', 0) / total_faqs) * 100
                pdf_attachment_pct = (mode_counts.get('PDF_ATTACHMENT', 0) / total_faqs) * 100
                video_pct = (mode_counts.get('VIDEO', 0) / total_faqs) * 100
            else:
                direct_answer_pct = phone_escalation_pct = pdf_attachment_pct = video_pct = 0
            
            # Average click depth to answer
            cursor.execute("SELECT AVG(link_depth_to_answer) FROM faqs WHERE link_depth_to_answer > 0")
            avg_click_depth = cursor.fetchone()[0] or 0
            
            # Link percentages
            cursor.execute("SELECT SUM(internal_links), SUM(external_links) FROM pages")
            internal_total, external_total = cursor.fetchone()
            total_links = internal_total + external_total
            
            if total_links > 0:
                internal_link_pct = (internal_total / total_links) * 100
                external_link_pct = (external_total / total_links) * 100
            else:
                internal_link_pct = external_link_pct = 0
            
            # Extraction success rate
            cursor.execute("""
                SELECT COUNT(*) FROM pages 
                WHERE extraction_status = 'completed'
            """)
            successful_extractions = cursor.fetchone()[0]
            
            extraction_success_rate = (successful_extractions / total_pages * 100) if total_pages > 0 else 0
            
            # Content blocks processed
            cursor.execute("SELECT COUNT(*) FROM content_blocks")
            content_blocks = cursor.fetchone()[0]
            
            # Unique domains
            cursor.execute("SELECT COUNT(DISTINCT SUBSTR(url, 1, INSTR(url, '/') - 1)) FROM pages")
            unique_domains = cursor.fetchone()[0] or 1
            
            metrics = {
                'total_pages': total_pages,
                'total_faqs': total_faqs,
                'total_pdfs': total_pdfs,
                'total_videos': total_videos,
                'direct_answer_percentage': direct_answer_pct,
                'phone_escalation_percentage': phone_escalation_pct,
                'pdf_attachment_percentage': pdf_attachment_pct,
                'video_percentage': video_pct,
                'avg_click_depth_to_answer': avg_click_depth,
                'internal_link_percentage': internal_link_pct,
                'external_link_percentage': external_link_pct,
                'extraction_success_rate': extraction_success_rate,
                'content_blocks_processed': content_blocks,
                'unique_domains': unique_domains
            }
            
            # Store metrics snapshot
            cursor.execute("""
                INSERT INTO metrics (
                    total_pages, total_faqs, total_pdfs, total_videos,
                    direct_answer_percentage, phone_escalation_percentage,
                    pdf_attachment_percentage, video_percentage,
                    avg_click_depth_to_answer, internal_link_percentage,
                    external_link_percentage, extraction_success_rate,
                    content_blocks_processed, unique_domains
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(metrics.values()))
            
            conn.commit()
            return metrics
