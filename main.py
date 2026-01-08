#!/usr/bin/env python3
"""
FAQ Scraper + RAG Chatbot
Main entry point for the application.

This script orchestrates the complete pipeline:
1. Web crawling with BFS and robots.txt compliance
2. Content extraction (FAQs, PDFs, videos)
3. Metrics computation and CX analysis
4. Vector indexing for RAG
5. Streamlit UI launch

Usage:
    python main.py --help
    python main.py crawl                    # Run crawling only
    python main.py process                  # Process content only
    python main.py metrics                  # Generate metrics only
    python main.py ui                       # Launch UI only
    python main.py full                     # Run complete pipeline
"""

import argparse
import sys
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.config import Config
from src.database import DatabaseManager
from src.crawler import FAQCrawler
from src.content_extractor import ContentProcessor
from src.pdf_processor import PDFProcessor
from src.video_processor import VideoProcessor
from src.metrics import MetricsAnalyzer
from src.vector_store import RAGSystem
from src.ui import main as ui_main


def setup_logging(config: Config):
    """Setup logging configuration."""
    Path(config.log_file).parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(config.log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )


def run_crawl(config: Config, db_manager: DatabaseManager) -> dict:
    """Run the web crawling process."""
    print("🔍 Starting web crawling...")
    
    crawler = FAQCrawler(config, db_manager)
    crawl_results = crawler.run_crawl()
    
    print(f"✅ Crawling completed:")
    print(f"   • Pages processed: {crawl_results['pages_processed']}")
    print(f"   • Pages failed: {crawl_results['pages_failed']}")
    print(f"   • Max pages reached: {crawl_results['max_pages_reached']}")
    
    return crawl_results


def run_content_processing(config: Config, db_manager: DatabaseManager) -> dict:
    """Run content extraction and processing."""
    print("📄 Starting content processing...")
    
    # Process HTML content and extract FAQs
    content_processor = ContentProcessor(config, db_manager)
    content_results = content_processor.process_all_pages()
    
    print(f"✅ Content processing completed:")
    print(f"   • Pages processed: {content_results['pages_processed']}")
    print(f"   • FAQs extracted: {content_results['total_faqs_extracted']}")
    print(f"   • Avg FAQs per page: {content_results['avg_faqs_per_page']:.1f}")
    
    # Process PDFs
    pdf_processor = PDFProcessor(config, db_manager)
    pdf_results = pdf_processor.process_all_pdfs()
    
    print(f"   • PDFs discovered: {pdf_results.get('pdfs_discovered', 0)}")
    print(f"   • PDFs processed: {pdf_results.get('pdfs_processed', 0)}")
    
    # Process videos
    video_processor = VideoProcessor(config, db_manager)
    video_results = video_processor.process_all_videos()
    
    print(f"   • Videos discovered: {video_results.get('videos_discovered', 0)}")
    print(f"   • Videos processed: {video_results.get('videos_processed', 0)}")
    
    return {
        'content': content_results,
        'pdfs': pdf_results,
        'videos': video_results
    }


def run_metrics(config: Config, db_manager: DatabaseManager) -> dict:
    """Generate metrics and analysis."""
    print("📊 Generating metrics and analysis...")
    
    metrics_analyzer = MetricsAnalyzer(config, db_manager)
    
    # Generate comprehensive report
    report = metrics_analyzer.generate_metrics_report()
    
    # Export metrics
    export_path = metrics_analyzer.export_metrics_to_json()
    
    # Print summary
    metrics_analyzer.print_metrics_summary()
    
    print(f"✅ Metrics completed:")
    print(f"   • Report exported to: {export_path}")
    
    return report


def run_vector_indexing(config: Config, db_manager: DatabaseManager, fresh: bool = False) -> dict:
    """Build vector index for RAG system."""
    print("🔗 Building vector index...")
    
    rag_system = RAGSystem(config, db_manager)
    
    # Rebuild index from scratch if fresh flag is set
    if fresh:
        print("   🔄 Clearing old index for fresh rebuild...")
        build_stats = rag_system.rebuild_index()
    else:
        # Build index (this will happen automatically if empty)
        build_stats = rag_system.build_index()
    
    print(f"✅ Vector indexing completed:")
    print(f"   • Total chunks: {build_stats['total_chunks']}")
    print(f"   • FAQ chunks: {build_stats['faq_chunks']}")
    print(f"   • PDF chunks: {build_stats['pdf_chunks']}")
    print(f"   • Video chunks: {build_stats['video_chunks']}")
    print(f"   • Page chunks: {build_stats['page_chunks']}")
    
    return build_stats


def run_ui(config: Config):
    """Launch the Streamlit UI."""
    print("🖥️  Launching Streamlit UI...")
    
    # Import and run UI
    import subprocess
    import os
    
    # Set environment variables
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path(__file__).parent)
    
    # Launch Streamlit
    cmd = [
        'streamlit', 'run', 
        str(Path(__file__).parent / 'src' / 'ui.py'),
        '--server.address', config.ui_host,
        '--server.port', str(config.ui_port),
        '--server.headless', 'false'
    ]
    
    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n👋 UI stopped by user")
    except Exception as e:
        print(f"❌ Error launching UI: {e}")


def run_full_pipeline(config: Config, db_manager: DatabaseManager, fresh: bool = False):
    """Run the complete pipeline."""
    print("🚀 Starting full pipeline...")
    if fresh:
        print("   🔄 Fresh mode: will rebuild vector index from scratch")
    print("=" * 60)
    
    # Step 1: Crawling
    crawl_results = run_crawl(config, db_manager)
    print()
    
    # Step 2: Content processing
    content_results = run_content_processing(config, db_manager)
    print()
    
    # Step 3: Vector indexing (always rebuild fresh after a full pipeline)
    vector_results = run_vector_indexing(config, db_manager, fresh=True)
    print()
    
    # Step 4: Metrics
    metrics_results = run_metrics(config, db_manager)
    print()
    
    print("=" * 60)
    print("🎉 Full pipeline completed successfully!")
    print()
    print("📋 SUMMARY:")
    print(f"   • Pages crawled: {crawl_results['pages_processed']}")
    print(f"   • FAQs extracted: {content_results['content']['total_faqs_extracted']}")
    print(f"   • PDFs processed: {content_results['pdfs'].get('pdfs_processed', 0)}")
    print(f"   • Videos processed: {content_results['videos'].get('videos_processed', 0)}")
    print(f"   • Vector chunks: {vector_results['total_chunks']}")
    print()
    print("🖥️  To launch the UI, run:")
    print(f"   python main.py ui")
    print()
    print("🌐 The UI will be available at:")
    print(f"   http://{config.ui_host}:{config.ui_port}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="FAQ Scraper + RAG Chatbot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py full                    # Run complete pipeline
  python main.py crawl                    # Web crawling only
  python main.py process                  # Content processing only
  python main.py metrics                  # Generate metrics only
  python main.py ui                       # Launch UI only
  python main.py index                    # Build vector index only
        """
    )
    
    parser.add_argument(
        'command',
        choices=['crawl', 'process', 'metrics', 'ui', 'full', 'index'],
        help='Command to run'
    )
    
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Clear existing data and start fresh (for re-crawling)'
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = Config(args.config)
        
        # Override log level if verbose
        if args.verbose:
            config._config['log_level'] = 'DEBUG'
        
        # Setup logging
        setup_logging(config)
        logger = logging.getLogger(__name__)
        
        # Initialize database
        db_manager = DatabaseManager(config.db_path)
        logger.info(f"Database initialized: {config.db_path}")
        
        # Run command
        if args.command == 'crawl':
            run_crawl(config, db_manager)
        
        elif args.command == 'process':
            run_content_processing(config, db_manager)
        
        elif args.command == 'metrics':
            run_metrics(config, db_manager)
        
        elif args.command == 'index':
            run_vector_indexing(config, db_manager, fresh=args.fresh)
        
        elif args.command == 'ui':
            run_ui(config)
        
        elif args.command == 'full':
            run_full_pipeline(config, db_manager, fresh=args.fresh)
        
        logger.info(f"Command '{args.command}' completed successfully")
        
    except KeyboardInterrupt:
        print("\n👋 Process interrupted by user")
        sys.exit(0)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
