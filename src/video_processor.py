"""
Video processing and transcription for Toyota FAQ scraper.
Handles video downloads, subtitle extraction, and speech-to-text.
"""

import requests
import hashlib
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging
import sqlite3
from urllib.parse import urlparse, urljoin

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logging.warning("yt-dlp not available. Video processing disabled.")

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logging.warning("faster-whisper not available. Speech-to-text disabled.")

from src.database import DatabaseManager
from src.config import Config


class VideoProcessor:
    """Processes video files for transcription and content extraction."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
        
        if not YTDLP_AVAILABLE:
            self.logger.error("yt-dlp not installed")
            raise ImportError("Install yt-dlp for video processing")
        
        # Initialize Whisper model if available
        self.whisper_model = None
        if WHISPER_AVAILABLE and config.video_enabled:
            try:
                self.whisper_model = WhisperModel(
                    config.whisper_model_size, 
                    device="cpu", 
                    compute_type="int8"
                )
                self.logger.info(f"Whisper model loaded: {config.whisper_model_size}")
            except Exception as e:
                self.logger.warning(f"Failed to load Whisper model: {e}")
        
        # yt-dlp options
        self.ydl_opts = {
            'format': 'best[height<=720]/best',  # Limit to 720p for efficiency
            'outtmpl': str(Path(config.raw_dir) / '%(id)s.%(ext)s'),
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en'],
            'skip_download': False,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
    
    def is_video_url(self, url: str) -> bool:
        """Check if URL points to a video."""
        video_indicators = [
            'youtube.com', 'youtu.be', 'vimeo.com',
            'video', 'watch', 'embed', '.mp4', '.avi', 
            '.mov', '.wmv', '.flv', '.webm'
        ]
        
        url_lower = url.lower()
        return any(indicator in url_lower for indicator in video_indicators)
    
    def get_video_info(self, video_url: str) -> Optional[Dict[str, any]]:
        """Get video information without downloading."""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                
                return {
                    'id': info.get('id', ''),
                    'title': info.get('title', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'webpage_url': info.get('webpage_url', video_url)
                }
        except Exception as e:
            self.logger.error(f"Failed to get video info for {video_url}: {e}")
            return None
    
    def download_video(self, video_url: str, source_page_id: Optional[int] = None) -> Optional[Dict[str, any]]:
        """Download video and extract subtitles."""
        try:
            self.logger.info(f"Processing video: {video_url}")
            
            # Get video info first
            video_info = self.get_video_info(video_url)
            if not video_info:
                return None
            
            # Download video with subtitles
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                
                # Get downloaded file paths
                video_file = None
                subtitle_file = None
                
                if 'requested_subtitles' in info and 'en' in info['requested_subtitles']:
                    subtitle_file = info['requested_subtitles']['en'].get('filepath')
                
                # Find the video file
                if 'requested_downloads' in info:
                    for download in info['requested_downloads']:
                        if download.get('vcodec') != 'none':  # Video file (not just audio)
                            video_file = download.get('filepath')
                            break
                
                return {
                    'video_info': video_info,
                    'video_file': video_file,
                    'subtitle_file': subtitle_file,
                    'has_subtitles': subtitle_file is not None
                }
        
        except Exception as e:
            self.logger.error(f"Failed to download video {video_url}: {e}")
            return None
    
    def extract_subtitles(self, subtitle_file: str) -> Optional[str]:
        """Extract text from subtitle file."""
        if not subtitle_file or not Path(subtitle_file).exists():
            return None
        
        try:
            subtitle_path = Path(subtitle_file)
            
            if subtitle_path.suffix.lower() in ['.vtt', '.srt']:
                # Read subtitle file
                with open(subtitle_path, 'r', encoding='utf-8') as f:
                    subtitle_content = f.read()
                
                # Extract text from subtitles (remove timestamps and formatting)
                import re
                
                # Remove VTT timestamps and formatting
                text = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}', '', subtitle_content)
                text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
                text = re.sub(r'^\d+$', '', text, flags=re.MULTILINE)  # Remove line numbers
                text = re.sub(r'^\s*WEBVTT.*$', '', text, flags=re.MULTILINE)  # Remove WEBVTT header
                
                # Clean up whitespace
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                clean_text = ' '.join(lines)
                
                return clean_text
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to extract subtitles from {subtitle_file}: {e}")
            return None
    
    def transcribe_audio(self, video_file: str) -> Optional[str]:
        """Transcribe video audio using Whisper."""
        if not self.whisper_model or not video_file or not Path(video_file).exists():
            return None
        
        try:
            self.logger.info(f"Transcribing audio from: {video_file}")
            
            # Transcribe using Whisper
            segments, info = self.whisper_model.transcribe(
                video_file, 
                language="en",
                beam_size=1
            )
            
            # Combine all segments
            transcription = " ".join(segment.text for segment in segments)
            
            self.logger.info(f"Transcription completed: {info.language} detected")
            return transcription.strip()
            
        except Exception as e:
            self.logger.error(f"Failed to transcribe audio from {video_file}: {e}")
            return None
    
    def save_transcription(self, transcription: str, video_url: str) -> str:
        """Save transcription to file."""
        url_hash = hashlib.md5(video_url.encode()).hexdigest()
        transcription_filename = f"{url_hash}_transcription.txt"
        transcription_path = Path(self.config.processed_dir) / transcription_filename
        
        with open(transcription_path, 'w', encoding='utf-8') as f:
            f.write(transcription)
        
        return str(transcription_path)
    
    def process_video(self, video_url: str, source_page_id: Optional[int] = None) -> Optional[int]:
        """Process a single video: download, extract subtitles/transcribe, and store."""
        try:
            # Download video
            download_result = self.download_video(video_url, source_page_id)
            if not download_result:
                return None
            
            video_info = download_result['video_info']
            video_file = download_result['video_file']
            subtitle_file = download_result['subtitle_file']
            has_subtitles = download_result['has_subtitles']
            
            # Extract text from subtitles or transcribe
            transcription_text = None
            transcription_method = None
            
            if has_subtitles and subtitle_file:
                transcription_text = self.extract_subtitles(subtitle_file)
                if transcription_text:
                    transcription_method = 'subtitle'
                    self.logger.info("Used subtitles for transcription")
            
            # Fallback to Whisper if no subtitles or subtitle extraction failed
            if not transcription_text and self.whisper_model and video_file:
                transcription_text = self.transcribe_audio(video_file)
                if transcription_text:
                    transcription_method = 'whisper'
                    self.logger.info("Used Whisper for transcription")
            
            # Save transcription if successful
            transcription_path = None
            extraction_status = 'failed'
            extraction_error = None
            
            if transcription_text and len(transcription_text.strip()) > 50:
                transcription_path = self.save_transcription(transcription_text, video_url)
                extraction_status = 'completed'
                self.logger.info(f"Transcription saved: {len(transcription_text)} characters")
            else:
                extraction_error = "No usable transcription could be extracted"
                self.logger.warning(f"No transcription extracted for {video_url}")
            
            # Store in database
            video_data = {
                'source_url': video_url,
                'source_page_id': source_page_id,
                'video_url': video_info.get('webpage_url', video_url),
                'title': video_info.get('title', ''),
                'duration_seconds': video_info.get('duration', 0),
                'file_path': video_file,
                'subtitle_path': subtitle_file,
                'transcription_path': transcription_path,
                'has_subtitles': has_subtitles,
                'transcription_method': transcription_method,
                'extraction_status': extraction_status,
                'extraction_error': extraction_error
            }
            
            video_id = self.db.insert_video(video_data)
            
            if video_id:
                self.logger.info(f"Video processed successfully: {video_url}")
                return video_id
            else:
                self.logger.warning(f"Video already exists in database: {video_url}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error processing video {video_url}: {e}")
            
            # Store failed attempt
            video_data = {
                'source_url': video_url,
                'source_page_id': source_page_id,
                'video_url': video_url,
                'title': '',
                'duration_seconds': 0,
                'file_path': None,
                'subtitle_path': None,
                'transcription_path': None,
                'has_subtitles': False,
                'transcription_method': None,
                'extraction_status': 'failed',
                'extraction_error': str(e)
            }
            
            self.db.insert_video(video_data)
            return None
    
    def discover_videos_from_pages(self) -> List[Dict[str, any]]:
        """Discover video URLs from already crawled pages."""
        videos_found = []
        
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            
            # Get pages with raw HTML
            cursor.execute("""
                SELECT id, url, raw_html_path 
                FROM pages 
                WHERE extraction_status = 'completed' 
                AND raw_html_path IS NOT NULL
            """)
            
            pages = cursor.fetchall()
            
            for page_id, page_url, html_path in pages:
                try:
                    # Read HTML content
                    with open(html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    
                    # Find video links
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, 'lxml')
                    
                    # Check iframe tags (common for embedded videos)
                    for iframe in soup.find_all('iframe', src=True):
                        src = iframe['src']
                        if self.is_video_url(src):
                            video_url = urljoin(page_url, src)
                            videos_found.append({
                                'video_url': video_url,
                                'source_page_id': page_id,
                                'source_page_url': page_url,
                                'link_text': iframe.get('title', '') or 'Embedded video'
                            })
                    
                    # Check anchor tags with video URLs
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if self.is_video_url(href):
                            video_url = urljoin(page_url, href)
                            videos_found.append({
                                'video_url': video_url,
                                'source_page_id': page_id,
                                'source_page_url': page_url,
                                'link_text': link.get_text(strip=True)
                            })
                    
                    # Check for video elements
                    for video in soup.find_all('video', src=True):
                        src = video['src']
                        if self.is_video_url(src):
                            video_url = urljoin(page_url, src)
                            videos_found.append({
                                'video_url': video_url,
                                'source_page_id': page_id,
                                'source_page_url': page_url,
                                'link_text': video.get('title', '') or 'Video element'
                            })
                
                except Exception as e:
                    self.logger.error(f"Error discovering videos in page {page_url}: {e}")
        
        # Remove duplicates
        unique_videos = []
        seen_urls = set()
        
        for video in videos_found:
            if video['video_url'] not in seen_urls:
                seen_urls.add(video['video_url'])
                unique_videos.append(video)
        
        self.logger.info(f"Discovered {len(unique_videos)} unique video URLs")
        return unique_videos
    
    def process_all_videos(self) -> Dict[str, any]:
        """Process all videos discovered from crawled pages."""
        if not self.config.video_enabled:
            self.logger.info("Video processing disabled in config")
            return {'status': 'disabled'}
        
        self.logger.info("Starting video processing")
        
        # Discover videos
        videos_to_process = self.discover_videos_from_pages()
        
        if not videos_to_process:
            self.logger.info("No videos found to process")
            return {'videos_discovered': 0, 'videos_processed': 0}
        
        # Process each video
        processed_count = 0
        failed_count = 0
        
        for video_info in videos_to_process:
            video_id = self.process_video(
                video_info['video_url'], 
                video_info['source_page_id']
            )
            
            if video_id:
                processed_count += 1
            else:
                failed_count += 1
        
        processing_summary = {
            'videos_discovered': len(videos_to_process),
            'videos_processed': processed_count,
            'videos_failed': failed_count,
            'success_rate': (processed_count / len(videos_to_process)) * 100 if videos_to_process else 0
        }
        
        self.logger.info(f"Video processing completed: {processing_summary}")
        return processing_summary
