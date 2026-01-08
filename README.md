# FAQ Crawler + Extractor + RAG Chatbot

A local pipeline to crawl web pages, extract FAQ-style Q/A content (plus PDFs and videos), build a vector index, and provide a Streamlit chat UI with source citations.

## 🚀 Quick Start

### 1) Install
```bash
pip install -r requirements.txt
```

### 2) Set environment variables
```bash
cp .env.example .env
```
If you enable the LLM provider in `config.yaml`, set `OPENAI_API_KEY` in `.env`.

## ⚙️ Configuration

Edit `config.yaml` to customize crawl + processing settings.

```yaml
seed_urls:
  - https://example.com/faq

allowed_domains:
  - example.com

# Crawling
crawl_depth: 3
max_pages: 1000
request_rate_limit: 1.0

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

Note: `src/config.py` may validate `seed_urls`. If you change `seed_urls`, ensure the validation allows your new values.

## ▶️ Run

### Run complete pipeline
```bash
python main.py full
```

### Launch UI
```bash
python main.py ui

streamlit run src/ui.py
```

### Access
Open your browser to: **http://localhost:8501**

## 🛠️ Commands

```bash
python main.py crawl

python main.py process

python main.py metrics

python main.py index

python main.py ui
```

## 🐛 Troubleshooting

### Common Issues

#### Crawling Problems
- Check `logs/` output for HTTP errors
- Confirm your `seed_urls` and `allowed_domains` are correct
- Confirm the target site allows crawling via `robots.txt`

#### PDF Processing Issues
```bash
# Verify PDF libraries
python -c "import PyPDF2, pdfplumber; print('PDF libraries OK')"
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

#### Network Issues
- Increase `request_rate_limit` for faster crawling
- Check corporate proxy settings
- Verify DNS resolution
