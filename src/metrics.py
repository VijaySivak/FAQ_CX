"""
Metrics computation and analysis for FAQ scraper.
Generates comprehensive CX metrics and business insights.
"""

import sqlite3
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
import logging
from datetime import datetime
import pandas as pd

from src.database import DatabaseManager
from src.config import Config


class MetricsAnalyzer:
    """Analyzes scraped data to generate CX metrics and business insights."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
    
    def get_overall_statistics(self) -> Dict[str, Any]:
        """Get overall crawl and processing statistics."""
        with self.db._connect() as conn:
            cursor = conn.cursor()
            
            # Page statistics
            cursor.execute("SELECT COUNT(*) FROM pages")
            total_pages = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM pages WHERE extraction_status = 'completed'")
            successful_pages = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM pages WHERE extraction_status = 'failed'")
            failed_pages = cursor.fetchone()[0]
            
            # FAQ statistics
            cursor.execute("SELECT COUNT(*) FROM faqs")
            total_faqs = cursor.fetchone()[0]
            
            # PDF statistics - count unique PDFs by source_url
            cursor.execute("SELECT COUNT(DISTINCT source_url) FROM pdfs")
            total_pdfs = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT source_url) FROM pdfs WHERE extraction_status = 'completed'")
            processed_pdfs = cursor.fetchone()[0]
            
            # Video statistics - count unique videos by video_url
            cursor.execute("SELECT COUNT(DISTINCT video_url) FROM videos")
            total_videos = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT video_url) FROM videos WHERE extraction_status = 'completed'")
            processed_videos = cursor.fetchone()[0]
            
            # Link statistics
            cursor.execute("SELECT SUM(internal_links), SUM(external_links) FROM pages")
            internal_links, external_links = cursor.fetchone()
            
            return {
                'pages': {
                    'total': total_pages,
                    'successful': successful_pages,
                    'failed': failed_pages,
                    'success_rate': (successful_pages / total_pages * 100) if total_pages > 0 else 0
                },
                'faqs': {
                    'total': total_faqs,
                    'avg_per_page': (total_faqs / successful_pages) if successful_pages > 0 else 0
                },
                'pdfs': {
                    'total': total_pdfs,
                    'processed': processed_pdfs,
                    'success_rate': (processed_pdfs / total_pdfs * 100) if total_pdfs > 0 else 0
                },
                'videos': {
                    'total': total_videos,
                    'processed': processed_videos,
                    'success_rate': (processed_videos / total_videos * 100) if total_videos > 0 else 0
                },
                'links': {
                    'internal': internal_links or 0,
                    'external': external_links or 0,
                    'total': (internal_links or 0) + (external_links or 0)
                }
            }
    
    def get_answer_mode_distribution(self) -> Dict[str, Any]:
        """Analyze distribution of answer modes (key CX metric)."""
        with self.db._connect() as conn:
            cursor = conn.cursor()
            
            # Get answer mode counts
            cursor.execute("""
                SELECT answer_mode, COUNT(*) as count
                FROM faqs
                GROUP BY answer_mode
                ORDER BY count DESC
            """)
            
            mode_counts = dict(cursor.fetchall())
            
            # Calculate percentages
            total_faqs = sum(mode_counts.values())
            
            distribution = {}
            for mode, count in mode_counts.items():
                distribution[mode] = {
                    'count': count,
                    'percentage': (count / total_faqs * 100) if total_faqs > 0 else 0
                }
            
            return {
                'distribution': distribution,
                'total_faqs': total_faqs,
                'direct_answer_rate': distribution.get('DIRECT_TEXT', {}).get('percentage', 0),
                'escalation_required_rate': sum(
                    dist.get('percentage', 0) for mode, dist in distribution.items()
                    if mode in ['PHONE_ESCALATION', 'LINK_OUT', 'PORTAL_REDIRECT']
                )
            }
    
    def get_content_depth_analysis(self) -> Dict[str, Any]:
        """Analyze content depth and navigation complexity."""
        with self.db._connect() as conn:
            cursor = conn.cursor()
            
            # Depth distribution for pages
            cursor.execute("""
                SELECT depth, COUNT(*) as count
                FROM pages
                GROUP BY depth
                ORDER BY depth
            """)
            
            depth_distribution = dict(cursor.fetchall())
            
            # Average depth to answer
            cursor.execute("""
                SELECT AVG(link_depth_to_answer), MAX(link_depth_to_answer)
                FROM faqs
                WHERE link_depth_to_answer > 0
            """)
            
            avg_depth, max_depth = cursor.fetchone()
            
            # Pages with phone numbers
            cursor.execute("""
                SELECT COUNT(*) FROM pages 
                WHERE phone_numbers IS NOT NULL 
                AND phone_numbers != '[]'
            """)
            
            pages_with_phones = cursor.fetchone()[0]
            
            return {
                'page_depth_distribution': depth_distribution,
                'avg_depth_to_answer': avg_depth or 0,
                'max_depth_to_answer': max_depth or 0,
                'pages_with_phone_numbers': pages_with_phones
            }
    
    def get_content_type_analysis(self) -> Dict[str, Any]:
        """Analyze content types and media distribution."""
        with self.db._connect() as conn:
            cursor = conn.cursor()
            
            # Content types in pages
            cursor.execute("""
                SELECT content_type, COUNT(*) as count
                FROM pages
                GROUP BY content_type
                ORDER BY count DESC
            """)
            
            content_types = dict(cursor.fetchall())
            
            # PDF analysis
            cursor.execute("""
                SELECT AVG(page_count), SUM(page_count)
                FROM pdfs
                WHERE extraction_status = 'completed'
            """)
            
            avg_pdf_pages, total_pdf_pages = cursor.fetchone()
            
            # Video analysis
            cursor.execute("""
                SELECT AVG(duration_seconds), SUM(duration_seconds)
                FROM videos
                WHERE extraction_status = 'completed'
            """)
            
            avg_video_duration, total_video_duration = cursor.fetchone()
            
            return {
                'page_content_types': content_types,
                'pdfs': {
                    'avg_pages': avg_pdf_pages or 0,
                    'total_pages': total_pdf_pages or 0
                },
                'videos': {
                    'avg_duration_seconds': avg_video_duration or 0,
                    'total_duration_seconds': total_video_duration or 0,
                    'avg_duration_minutes': (avg_video_duration or 0) / 60
                }
            }
    
    def get_customer_experience_metrics(self) -> Dict[str, Any]:
        """Generate CX-focused metrics for business narrative."""
        answer_modes = self.get_answer_mode_distribution()
        depth_analysis = self.get_content_depth_analysis()
        stats = self.get_overall_statistics()
        
        # Key CX metrics
        direct_answer_pct = answer_modes.get('direct_answer_rate', 0)
        escalation_pct = answer_modes.get('escalation_required_rate', 0)
        phone_escalation_pct = answer_modes.get('distribution', {}).get('PHONE_ESCALATION', {}).get('percentage', 0)
        pdf_dependency_pct = answer_modes.get('distribution', {}).get('PDF_ATTACHMENT', {}).get('percentage', 0)
        video_dependency_pct = answer_modes.get('distribution', {}).get('VIDEO', {}).get('percentage', 0)
        
        # Calculate "effort score" - lower is better
        # Direct answer = 1 effort, Link/Portal = 2 effort, Phone = 3 effort, PDF/Video = 2.5 effort
        distribution = answer_modes.get('distribution', {})
        total_faqs = answer_modes.get('total_faqs', 1)
        
        effort_score = (
            (distribution.get('DIRECT_TEXT', {}).get('count', 0) * 1) +
            (distribution.get('LINK_OUT', {}).get('count', 0) * 2) +
            (distribution.get('PORTAL_REDIRECT', {}).get('count', 0) * 2) +
            (distribution.get('PHONE_ESCALATION', {}).get('count', 0) * 3) +
            (distribution.get('PDF_ATTACHMENT', {}).get('count', 0) * 2.5) +
            (distribution.get('VIDEO', {}).get('count', 0) * 2.5)
        ) / total_faqs
        
        # Fragmentation score - higher means more fragmented
        fragmentation_score = 100 - direct_answer_pct
        
        return {
            'direct_answers': {
                'percentage': direct_answer_pct,
                'count': distribution.get('DIRECT_TEXT', {}).get('count', 0),
                'assessment': 'Good' if direct_answer_pct > 70 else 'Poor' if direct_answer_pct < 40 else 'Moderate'
            },
            'customer_effort': {
                'score': effort_score,
                'assessment': 'Low' if effort_score < 1.5 else 'High' if effort_score > 2.0 else 'Moderate'
            },
            'escalation_required': {
                'percentage': escalation_pct,
                'phone_specific': phone_escalation_pct,
                'assessment': 'Low' if escalation_pct < 20 else 'High' if escalation_pct > 40 else 'Moderate'
            },
            'media_dependency': {
                'pdf_percentage': pdf_dependency_pct,
                'video_percentage': video_dependency_pct,
                'total_media_dependency': pdf_dependency_pct + video_dependency_pct,
                'assessment': 'Low' if (pdf_dependency_pct + video_dependency_pct) < 15 else 'High'
            },
            'fragmentation': {
                'score': fragmentation_score,
                'assessment': 'Low' if fragmentation_score < 30 else 'High' if fragmentation_score > 60 else 'Moderate'
            },
            'navigation_complexity': {
                'avg_depth_to_answer': depth_analysis.get('avg_depth_to_answer', 0),
                'assessment': 'Simple' if depth_analysis.get('avg_depth_to_answer', 0) < 1.5 else 'Complex'
            }
        }
    
    def generate_business_insights(self) -> List[Dict[str, Any]]:
        """Generate actionable business insights from metrics."""
        cx_metrics = self.get_customer_experience_metrics()
        stats = self.get_overall_statistics()
        
        insights = []
        
        # Direct answer rate insight
        direct_rate = cx_metrics['direct_answers']['percentage']
        if direct_rate < 40:
            insights.append({
                'type': 'critical',
                'category': 'content_quality',
                'title': 'Low Direct Answer Rate',
                'description': f'Only {direct_rate:.1f}% of FAQs provide direct answers. {100-direct_rate:.1f}% require customers to take additional actions.',
                'impact': 'High',
                'recommendation': 'Focus on providing complete answers directly in FAQ content to reduce customer effort.'
            })
        elif direct_rate > 70:
            insights.append({
                'type': 'positive',
                'category': 'content_quality',
                'title': 'Good Direct Answer Coverage',
                'description': f'{direct_rate:.1f}% of FAQs provide direct answers, indicating good content completeness.',
                'impact': 'Positive',
                'recommendation': 'Maintain current content quality standards.'
            })
        
        # Phone escalation insight
        phone_rate = cx_metrics['escalation_required']['phone_specific']
        if phone_rate > 15:
            insights.append({
                'type': 'warning',
                'category': 'operational_efficiency',
                'title': 'High Phone Escalation Rate',
                'description': f'{phone_rate:.1f}% of FAQs require phone calls, potentially increasing call center volume.',
                'impact': 'Medium',
                'recommendation': 'Review phone-requiring FAQs and enhance online self-service options.'
            })
        
        # Media dependency insight
        media_dep = cx_metrics['media_dependency']['total_media_dependency']
        if media_dep > 25:
            insights.append({
                'type': 'info',
                'category': 'accessibility',
                'title': 'High Media Dependency',
                'description': f'{media_dep:.1f}% of answers require PDFs or videos, which may not be accessible to all users.',
                'impact': 'Medium',
                'recommendation': 'Provide text summaries for PDF/video content to improve accessibility.'
            })
        
        # Fragmentation insight
        frag_score = cx_metrics['fragmentation']['score']
        if frag_score > 60:
            insights.append({
                'type': 'critical',
                'category': 'user_experience',
                'title': 'High Content Fragmentation',
                'description': f'Content is highly fragmented with {frag_score:.1f}% of answers requiring external resources.',
                'impact': 'High',
                'recommendation': 'Consolidate fragmented content into comprehensive FAQ entries.'
            })
        
        # Navigation complexity insight
        nav_complexity = cx_metrics['navigation_complexity']['avg_depth_to_answer']
        if nav_complexity > 2.0:
            insights.append({
                'type': 'warning',
                'category': 'navigation',
                'title': 'Complex Navigation Required',
                'description': f'Average depth of {nav_complexity:.1f} clicks needed to reach answers.',
                'impact': 'Medium',
                'recommendation': 'Improve information architecture to reduce navigation depth.'
            })
        
        return insights
    
    def generate_metrics_report(self) -> Dict[str, Any]:
        """Generate comprehensive metrics report."""
        self.logger.info("Generating comprehensive metrics report")
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'overall_statistics': self.get_overall_statistics(),
            'answer_mode_distribution': self.get_answer_mode_distribution(),
            'content_depth_analysis': self.get_content_depth_analysis(),
            'content_type_analysis': self.get_content_type_analysis(),
            'customer_experience_metrics': self.get_customer_experience_metrics(),
            'business_insights': self.generate_business_insights()
        }
        
        # Store metrics snapshot in database
        metrics = self.db.compute_metrics()
        report['database_metrics'] = metrics
        
        return report
    
    def export_metrics_to_json(self, output_path: Optional[str] = None) -> str:
        """Export metrics report to JSON file."""
        if output_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = Path(self.config.processed_dir) / f"metrics_report_{timestamp}.json"
        
        report = self.generate_metrics_report()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)
        
        self.logger.info(f"Metrics report exported to: {output_path}")
        return str(output_path)
    
    def print_metrics_summary(self):
        """Print a concise metrics summary to console."""
        cx_metrics = self.get_customer_experience_metrics()
        stats = self.get_overall_statistics()
        
        print("\n" + "="*60)
        print("FAQ ANALYSIS - METRICS SUMMARY")
        print("="*60)
        
        print(f"\n📊 CONTENT OVERVIEW:")
        print(f"   • Pages crawled: {stats['pages']['total']}")
        print(f"   • FAQs extracted: {stats['faqs']['total']}")
        print(f"   • PDFs processed: {stats['pdfs']['processed']}/{stats['pdfs']['total']}")
        print(f"   • Videos processed: {stats['videos']['processed']}/{stats['videos']['total']}")
        
        print(f"\n🎯 CUSTOMER EXPERIENCE METRICS:")
        print(f"   • Direct answers: {cx_metrics['direct_answers']['percentage']:.1f}%")
        print(f"   • Requires escalation: {cx_metrics['escalation_required']['percentage']:.1f}%")
        print(f"   • Phone escalation: {cx_metrics['escalation_required']['phone_specific']:.1f}%")
        print(f"   • Media dependency: {cx_metrics['media_dependency']['total_media_dependency']:.1f}%")
        print(f"   • Customer effort score: {cx_metrics['customer_effort']['score']:.2f}/3.0")
        print(f"   • Content fragmentation: {cx_metrics['fragmentation']['score']:.1f}%")
        
        print(f"\n📈 ASSESSMENTS:")
        print(f"   • Content quality: {cx_metrics['direct_answers']['assessment']}")
        print(f"   • Customer effort: {cx_metrics['customer_effort']['assessment']}")
        print(f"   • Escalation level: {cx_metrics['escalation_required']['assessment']}")
        print(f"   • Media dependency: {cx_metrics['media_dependency']['assessment']}")
        print(f"   • Navigation complexity: {cx_metrics['navigation_complexity']['assessment']}")
        
        print("\n" + "="*60)
