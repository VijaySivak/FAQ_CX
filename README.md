# Toyota Financial Services FAQ Scraper + RAG Chatbot (PoC)

A comprehensive local PoC application that crawls Toyota Financial Services FAQ sections, extracts content, processes PDFs and videos, and provides a RAG-powered chatbot with CX metrics analysis.

## 🎯 Purpose

This PoC demonstrates the fragmentation and complexity of Toyota Financial Services' FAQ content by:
- Crawling public FAQ sections with strict compliance
- Extracting and analyzing FAQ question-answer pairs
- Processing PDFs and videos as knowledge sources
- Generating measurable CX metrics
- Providing a RAG chatbot with source citations
- Creating business insights for FAQ optimization

## 🚀 Features

### Web Crawling
- **BFS traversal** with depth limit (max 3 levels)
- **Domain restriction** to toyotafinancial.com only
- **Robots.txt compliance** mandatory
- **Rate limiting** respectful crawling
- **Configurable seed URLs** (exactly 2 required)

### Content Extraction
- **FAQ pair extraction** with multiple strategies
- **Answer mode classification** (Direct, Phone, PDF, Video, etc.)
- **Link depth analysis** for navigation complexity
- **Phone number and email detection**
- **Content type identification**

### Media Processing
- **PDF text extraction** using PyPDF2 and pdfplumber
- **Video subtitle extraction** when available
- **Speech-to-text** using Whisper (local)
- **Media dependency tracking**

### Metrics & Analytics
- **Customer Experience metrics** (effort scores, escalation rates)
- **Content fragmentation analysis**
- **Navigation complexity assessment**
- **Business insights generation**
- **Exportable reports** (JSON)

### RAG Chatbot
- **Vector similarity search** using FAISS
- **Source citation** for all answers
- **Multi-modal content** (FAQs, PDFs, videos, pages)
- **Confidence scoring**
- **Interactive UI**

## 📋 Requirements

### System Requirements
- Python 3.8+
- 8GB+ RAM recommended
- 10GB+ free disk space
- Local VM environment (no cloud dependencies)

### Python Dependencies
```bash
pip install -r requirements.txt
```

### External Tools (optional)
- **ffmpeg** (for video processing)
- **whisper.cpp** (alternative speech-to-text)

## ⚙️ Configuration

Edit `config.yaml` to customize settings:

```yaml
# Seed URLs (EXACTLY these two - no changes allowed)
seed_urls:
  - https://www.toyotafinancial.com/us/en/planning_tools/faq.html
  - https://www.toyotafinancial.com/us/en/end_of_lease_options/faqs.html

# Crawling constraints
crawl_depth: 3              # Max depth (1-3)
max_pages: 1000            # Safety cap
request_rate_limit: 1.0    # Requests per second

# Processing
pdf_enabled: true          # Enable PDF processing
video_enabled: true        # Enable video processing
whisper_model_size: "base" # Whisper model size

# Vector store
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
vector_dim: 384

# UI
ui_host: "localhost"
ui_port: 8501
```

## 🏗️ Project Structure

```
TFS/
├── config.yaml              # Configuration file
├── requirements.txt         # Python dependencies
├── main.py                  # Main entry point
├── README.md               # This file
├── src/                    # Source code
│   ├── __init__.py
│   ├── config.py           # Configuration management
│   ├── database.py         # SQLite schema and operations
│   ├── crawler.py          # BFS web crawler
│   ├── content_extractor.py # FAQ and content extraction
│   ├── pdf_processor.py    # PDF processing
│   ├── video_processor.py   # Video processing
│   ├── metrics.py          # Metrics and analytics
│   ├── vector_store.py     # RAG vector store
│   └── ui.py              # Streamlit UI
├── data/                   # Data storage
│   ├── raw/               # Raw downloaded content
│   └── processed/         # Processed text and transcriptions
└── logs/                  # Application logs
```

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Clone or extract the project
cd TFS

# Install dependencies
pip install -r requirements.txt

# Verify configuration
cat config.yaml
```

### 2. Run Complete Pipeline
```bash
# Run everything (crawling, processing, indexing, metrics)
python main.py full

# This will:
# 1. Crawl the 2 seed URLs up to depth 3
# 2. Extract FAQs and process media
# 3. Build vector index for RAG
# 4. Generate CX metrics
# 5. Print summary and next steps
```

### 3. Launch UI
```bash
# Launch the Streamlit interface
python main.py ui

# Or run directly with streamlit
streamlit run src/ui.py
```

### 4. Access the Application
Open your browser to: **http://localhost:8501**

## 📊 Using the Application

### Metrics Dashboard
- **Customer Experience Overview**: Direct answer rates, effort scores
- **Answer Mode Distribution**: Pie chart of answer types
- **Business Insights**: Automated recommendations
- **Navigation Analysis**: Depth and complexity metrics

### FAQ Chatbot
- Ask questions about Toyota Financial Services
- Get answers with source citations
- View confidence scores and similarity metrics
- Trace answers back to original sources

### Detailed Analytics
- Content type breakdown
- Media processing statistics
- Depth distribution analysis
- Export capabilities

## 🛠️ Advanced Usage

### Individual Commands
```bash
# Run only crawling
python main.py crawl

# Process content only (after crawling)
python main.py process

# Generate metrics only
python main.py metrics

# Build vector index only
python main.py index

# Launch UI only
python main.py ui
```

### Verbose Mode
```bash
# Enable detailed logging
python main.py full --verbose
```

### Custom Configuration
```bash
# Use custom config file
python main.py full --config my_config.yaml
```

## 📈 Key Metrics Generated

### Customer Experience Metrics
- **Direct Answer Rate**: % of FAQs with complete answers
- **Customer Effort Score**: 1-3 scale (lower is better)
- **Escalation Rate**: % requiring phone/external resources
- **Media Dependency**: % requiring PDFs/videos
- **Fragmentation Score**: Content dispersion metric

### Content Metrics
- **FAQ Density**: Average FAQs per page
- **Navigation Depth**: Average clicks to answer
- **Media Processing**: PDF/video success rates
- **Link Analysis**: Internal vs external link ratios

### Business Insights
- **Critical Issues**: High phone escalation, low direct answers
- **Optimization Opportunities**: Content consolidation areas
- **Accessibility Concerns**: Media dependency analysis
- **Navigation Improvements**: Depth reduction opportunities

## 🔍 Compliance & Constraints

### Crawling Rules
- ✅ **BFS traversal only** (no random crawling)
- ✅ **Depth limited to 3** from seed URLs
- ✅ **Domain restricted** to toyotafinancial.com
- ✅ **Robots.txt respected** always
- ✅ **Rate limited** to 1 request/second
- ❌ **No authentication bypass**
- ❌ **No external link following**
- ❌ **No JavaScript rendering**

### Content Processing
- ✅ **Store all raw artifacts**
- ✅ **Extract clean text content**
- ✅ **Process PDFs and videos**
- ✅ **Generate comprehensive metadata**
- ❌ **No OCR of images**
- ❌ **No change detection**

### Technical Constraints
- ✅ **Local VM only** (no cloud services)
- ✅ **Free/open-source tools** only
- ✅ **No paid APIs**
- ✅ **SQLite storage** (no external databases)

## 🐛 Troubleshooting

### Common Issues

#### Crawling Problems
```bash
# Check robots.txt compliance
python -c "from urllib.robotparser import RobotFileParser; rp = RobotFileParser(); rp.set_url('https://www.toyotafinancial.com/robots.txt'); rp.read(); print(rp.can_fetch('*', 'https://www.toyotafinancial.com/us/en/planning_tools/faq.html'))"

# Test network connectivity
curl -I https://www.toyotafinancial.com/us/en/planning_tools/faq.html
```

#### PDF Processing Issues
```bash
# Verify PDF libraries
python -c "import PyPDF2, pdfplumber; print('PDF libraries OK')"

# Check PDF URLs manually
# Look for 403/404 errors in logs
```

#### Video Processing Issues
```bash
# Verify yt-dlp installation
yt-dlp --version

# Test video URL extraction
yt-dlp --list-formats "VIDEO_URL_HERE"
```

#### Vector Store Issues
```bash
# Verify FAISS installation
python -c "import faiss; print(faiss.__version__)"

# Check embedding model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

### Performance Optimization

#### Memory Usage
- Reduce `max_pages` in config.yaml
- Use smaller Whisper model (`tiny` instead of `base`)
- Clear vector cache regularly

#### Disk Space
- Monitor `data/` directory size
- Clean old raw files: `rm -rf data/raw/*`
- Compress processed files

#### Network Issues
- Increase `request_rate_limit` for faster crawling
- Check corporate proxy settings
- Verify DNS resolution

## 📊 Sample Output

### Crawl Summary
```
🔍 Starting web crawling...
✅ Crawling completed:
   • Pages processed: 47
   • Pages failed: 2
   • Max pages reached: False

📄 Starting content processing...
✅ Content processing completed:
   • Pages processed: 47
   • FAQs extracted: 156
   • Avg FAQs per page: 3.3
   • PDFs discovered: 8
   • PDFs processed: 7
   • Videos discovered: 3
   • Videos processed: 2

🔗 Building vector index...
✅ Vector indexing completed:
   • Total chunks: 892
   • FAQ chunks: 312
   • PDF chunks: 234
   • Video chunks: 156
   • Page chunks: 190

📊 Generating metrics and analysis...

============================================================
TOYOTA FINANCIAL SERVICES FAQ ANALYSIS - METRICS SUMMARY
============================================================

📊 CONTENT OVERVIEW:
   • Pages crawled: 47
   • FAQs extracted: 156
   • PDFs processed: 7/8
   • Videos processed: 2/3

🎯 CUSTOMER EXPERIENCE METRICS:
   • Direct answers: 34.6%
   • Requires escalation: 65.4%
   • Phone escalation: 12.2%
   • Media dependency: 18.3%
   • Customer effort score: 2.1/3.0
   • Content fragmentation: 65.4%

📈 ASSESSMENTS:
   • Content quality: Poor
   • Customer effort: High
   • Escalation level: High
   • Media dependency: Moderate
   • Navigation complexity: Complex
```

## 🤝 Contributing

This is a PoC project. For improvements:
1. Follow the existing code style
2. Update configuration schema if needed
3. Add comprehensive logging
4. Test with the exact seed URLs
5. Document compliance with constraints

## 📄 License

This project is for educational/demonstration purposes only.
Please respect Toyota Financial Services' terms of service and robots.txt.

## 🆘 Support

For issues:
1. Check the troubleshooting section
2. Review logs in `logs/scraper.log`
3. Verify configuration matches requirements
4. Test individual components separately

---

**⚠️ Important**: This PoC is designed for local VM use only. Do not run in production environments or scale beyond the configured limits without proper authorization.
