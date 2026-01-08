"""
Vector store implementation for RAG system using FAISS.
Handles document chunking, embedding, and similarity search.
"""

import os
import hashlib
import sqlite3
import re
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
import numpy as np
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI not available. LLM-based answer generation disabled.")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("FAISS not available. Vector search disabled.")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available. Embeddings disabled.")

from src.database import DatabaseManager
from src.config import Config


class TextChunker:
    """Chunks documents into smaller pieces for embedding and retrieval."""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.logger = logging.getLogger(__name__)
    
    def chunk_text(self, text: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Split text into overlapping chunks."""
        if not text or len(text) < 20:
            return []
        
        chunks = []
        tokens = re.findall(r'\S+|\n', text)
        
        for i in range(0, len(tokens), self.chunk_size - self.chunk_overlap):
            chunk_tokens = tokens[i:i + self.chunk_size]

            parts: List[str] = []
            for tok in chunk_tokens:
                if tok == "\n":
                    parts.append("\n")
                    continue
                if parts and parts[-1] != "\n":
                    parts.append(" ")
                parts.append(tok)

            chunk_text = ''.join(parts).strip()
            
            if len(chunk_text.strip()) < 20:  # Skip very short chunks
                continue
            
            chunk_metadata = metadata.copy() if metadata else {}
            chunk_metadata.update({
                'chunk_index': len(chunks),
                'word_count': len([t for t in chunk_tokens if t != "\n"]),
                'char_count': len(chunk_text)
            })
            
            chunks.append({
                'content': chunk_text.strip(),
                'metadata': chunk_metadata
            })
            
            # Stop if we've reached the end
            if i + self.chunk_size >= len(tokens):
                break
        
        self.logger.debug(f"Created {len(chunks)} chunks from text")
        return chunks
    
    def chunk_faqs(self, faqs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create chunks from FAQ pairs."""
        chunks = []
        
        for faq in faqs:
            # Create question chunk
            question_metadata = {
                'source_type': 'faq',
                'content_type': 'question',
                'faq_id': faq.get('id'),
                'answer_mode': faq.get('answer_mode'),
                'source_url': faq.get('source_url')
            }
            
            question_chunks = self.chunk_text(faq['question'], question_metadata)
            chunks.extend(question_chunks)
            
            # Create answer chunk
            answer_metadata = {
                'source_type': 'faq',
                'content_type': 'answer',
                'faq_id': faq.get('id'),
                'answer_mode': faq.get('answer_mode'),
                'source_url': faq.get('source_url')
            }
            
            answer_chunks = self.chunk_text(faq['answer'], answer_metadata)
            chunks.extend(answer_chunks)
        
        return chunks


class VectorStore:
    """FAISS-based vector store for document retrieval."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
        
        if not FAISS_AVAILABLE:
            raise ImportError("Install faiss-cpu for vector search")
        
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("Install sentence-transformers for embeddings")
        
        # Initialize embedding model
        self.embedding_model = SentenceTransformer(config.embedding_model)
        self.dimension = config.vector_dim
        
        # Initialize FAISS index
        self.index = faiss.IndexFlatIP(self.dimension)  # Inner product for cosine similarity
        self.documents = []  # Store document metadata
        
        # Load existing index if available
        self.index_path = Path(config.data_dir) / "faiss_index.bin"
        self.docs_path = Path(config.data_dir) / "documents.pkl"
        
        if self.index_path.exists() and self.docs_path.exists():
            self.load_index()
        
        self.chunker = TextChunker()
    
    def normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Normalize embeddings for cosine similarity."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / (norms + 1e-8)
    
    def embed_text(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""
        try:
            embeddings = self.embedding_model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            return self.normalize_embeddings(embeddings)
        except Exception as e:
            self.logger.error(f"Error generating embeddings: {e}")
            return np.array([])
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        """Add documents to the vector store."""
        if not documents:
            return 0
        
        try:
            # Extract text content
            texts = [doc['content'] for doc in documents]
            
            # Generate embeddings
            embeddings = self.embed_text(texts)
            
            if embeddings.size == 0:
                self.logger.error("Failed to generate embeddings")
                return 0
            
            # Add to FAISS index
            start_idx = len(self.documents)
            self.index.add(embeddings.astype('float32'))
            
            # Store document metadata
            for i, doc in enumerate(documents):
                doc['vector_index'] = start_idx + i
                self.documents.append(doc)
            
            self.logger.info(f"Added {len(documents)} documents to vector store")
            return len(documents)
            
        except Exception as e:
            self.logger.error(f"Error adding documents to vector store: {e}")
            return 0
    
    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar documents."""
        try:
            # Embed query
            query_embedding = self.embed_text([query])
            
            if query_embedding.size == 0:
                return []
            
            # Search FAISS index
            scores, indices = self.index.search(query_embedding.astype('float32'), k)
            
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < len(self.documents) and idx >= 0:
                    doc = self.documents[idx].copy()
                    doc['similarity_score'] = float(score)
                    results.append(doc)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error searching vector store: {e}")
            return []
    
    def save_index(self):
        """Save FAISS index and documents to disk."""
        try:
            # Save FAISS index
            faiss.write_index(self.index, str(self.index_path))
            
            # Save documents
            with open(self.docs_path, 'wb') as f:
                pickle.dump(self.documents, f)
            
            self.logger.info(f"Vector index saved to {self.index_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving vector index: {e}")
    
    def load_index(self):
        """Load FAISS index and documents from disk."""
        try:
            # Load FAISS index
            self.index = faiss.read_index(str(self.index_path))
            
            # Load documents
            with open(self.docs_path, 'rb') as f:
                self.documents = pickle.load(f)
            
            self.logger.info(f"Vector index loaded from {self.index_path}")
            self.logger.info(f"Loaded {len(self.documents)} documents")
            
        except Exception as e:
            self.logger.error(f"Error loading vector index: {e}")
            self.index = faiss.IndexFlatIP(self.dimension)
            self.documents = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        return {
            'total_documents': len(self.documents),
            'index_type': str(type(self.index).__name__),
            'dimension': self.dimension,
            'embedding_model': self.config.embedding_model
        }


class RAGSystem:
    """Retrieval-Augmented Generation system for FAQ chatbot."""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
        
        # Initialize vector store
        self.vector_store = VectorStore(config, db_manager)
        
        # Initialize LLM client if enabled
        self.llm_client = None
        if config.llm_enabled and OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                self.llm_client = OpenAI(api_key=api_key)
                self.logger.info(f"LLM enabled with model: {config.llm_model}")
            else:
                self.logger.warning("OPENAI_API_KEY not set. LLM-based answer generation disabled.")
        
        # Load or build index
        self.ensure_index_built()
    
    def ensure_index_built(self):
        """Ensure vector index is built and populated."""
        if len(self.vector_store.documents) == 0:
            self.logger.info("Building vector index from database")
            self.build_index()
        else:
            self.logger.info(f"Vector index already has {len(self.vector_store.documents)} documents")
    
    def clear_index(self):
        """Clear the vector index and documents for a fresh rebuild."""
        self.logger.info("Clearing vector index...")
        self.vector_store.index = faiss.IndexFlatIP(self.vector_store.dimension)
        self.vector_store.documents = []
        
        # Remove saved index files
        if self.vector_store.index_path.exists():
            self.vector_store.index_path.unlink()
        if self.vector_store.docs_path.exists():
            self.vector_store.docs_path.unlink()
        
        # Clear content_blocks table
        with self.db._connect() as conn:
            conn.execute("DELETE FROM content_blocks")
            conn.commit()
        
        self.logger.info("Vector index cleared")
    
    def rebuild_index(self) -> Dict[str, Any]:
        """Clear and rebuild the vector index from scratch."""
        self.clear_index()
        return self.build_index()
    
    def build_index(self) -> Dict[str, Any]:
        """Build vector index from all content in database."""
        self.logger.info("Building vector index from database content")
        
        all_chunks = []
        
        # Process FAQs
        with self.db._connect() as conn:
            cursor = conn.cursor()
            
            # Get FAQs with page URLs
            cursor.execute("""
                SELECT f.id, f.question, f.answer, f.answer_mode, p.url as source_url
                FROM faqs f
                JOIN pages p ON f.page_id = p.id
                WHERE f.question IS NOT NULL AND f.answer IS NOT NULL
            """)
            
            faqs = []
            for row in cursor.fetchall():
                if not row[1] or not row[2]:
                    continue
                answer_text = row[2]
                if '<' in answer_text and '>' in answer_text:
                    answer_text = self._html_to_text_preserve_lists(answer_text)
                faqs.append({
                    'id': row[0],
                    'question': row[1],
                    'answer': answer_text,
                    'answer_mode': row[3],
                    'source_url': row[4]
                })
            
            # Chunk FAQs
            faq_chunks = self.vector_store.chunker.chunk_faqs(faqs)
            all_chunks.extend(faq_chunks)
            
            self.logger.info(f"Processed {len(faqs)} FAQs into {len(faq_chunks)} chunks")
            
            # Process PDF content
            cursor.execute("""
                SELECT id, extracted_text_path, source_url, filename
                FROM pdfs
                WHERE extraction_status = 'completed' AND extracted_text_path IS NOT NULL
            """)
            
            pdf_chunks = []
            for row in cursor.fetchall():
                pdf_id, text_path, source_url, filename = row
                
                try:
                    with open(text_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    
                    metadata = {
                        'source_type': 'pdf',
                        'pdf_id': pdf_id,
                        'source_url': source_url,
                        'filename': filename
                    }
                    
                    chunks = self.vector_store.chunker.chunk_text(text, metadata)
                    pdf_chunks.extend(chunks)
                    
                except Exception as e:
                    self.logger.warning(f"Error processing PDF {pdf_id}: {e}")
            
            all_chunks.extend(pdf_chunks)
            self.logger.info(f"Processed PDFs into {len(pdf_chunks)} chunks")
            
            # Process video transcriptions
            cursor.execute("""
                SELECT id, transcription_path, source_url, title
                FROM videos
                WHERE extraction_status = 'completed' AND transcription_path IS NOT NULL
            """)
            
            video_chunks = []
            for row in cursor.fetchall():
                video_id, transcription_path, source_url, title = row
                
                try:
                    with open(transcription_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    
                    metadata = {
                        'source_type': 'video',
                        'video_id': video_id,
                        'source_url': source_url,
                        'title': title
                    }
                    
                    chunks = self.vector_store.chunker.chunk_text(text, metadata)
                    video_chunks.extend(chunks)
                    
                except Exception as e:
                    self.logger.warning(f"Error processing video {video_id}: {e}")
            
            all_chunks.extend(video_chunks)
            self.logger.info(f"Processed videos into {len(video_chunks)} chunks")
            
            # Process general page content
            cursor.execute("""
                SELECT id, cleaned_text_path, url, title
                FROM pages
                WHERE extraction_status = 'completed' AND cleaned_text_path IS NOT NULL
            """)
            
            page_chunks = []
            for row in cursor.fetchall():
                page_id, text_path, url, title = row
                
                try:
                    with open(text_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                    
                    metadata = {
                        'source_type': 'page',
                        'page_id': page_id,
                        'source_url': url,
                        'title': title
                    }
                    
                    chunks = self.vector_store.chunker.chunk_text(text, metadata)
                    page_chunks.extend(chunks)
                    
                except Exception as e:
                    self.logger.warning(f"Error processing page {page_id}: {e}")
            
            all_chunks.extend(page_chunks)
            self.logger.info(f"Processed pages into {len(page_chunks)} chunks")
        
        # Add all chunks to vector store
        added_count = self.vector_store.add_documents(all_chunks)
        
        # Save index
        self.vector_store.save_index()
        
        # Store content blocks in database
        self.store_content_blocks(all_chunks)
        
        build_stats = {
            'total_chunks': len(all_chunks),
            'added_chunks': added_count,
            'faq_chunks': len(faq_chunks),
            'pdf_chunks': len(pdf_chunks),
            'video_chunks': len(video_chunks),
            'page_chunks': len(page_chunks)
        }
        
        self.logger.info(f"Vector index built: {build_stats}")
        return build_stats
    
    def store_content_blocks(self, chunks: List[Dict[str, Any]]):
        """Store content blocks in database for tracking."""
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            
            for chunk in chunks:
                content_hash = hashlib.md5(chunk['content'].encode()).hexdigest()
                
                cursor.execute("""
                    INSERT OR IGNORE INTO content_blocks (
                        source_type, source_id, block_index, content, 
                        content_hash, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    chunk['metadata'].get('source_type', 'unknown'),
                    chunk['metadata'].get('faq_id') or chunk['metadata'].get('pdf_id') or 
                    chunk['metadata'].get('video_id') or chunk['metadata'].get('page_id') or 0,
                    chunk['metadata'].get('chunk_index', 0),
                    chunk['content'],
                    content_hash,
                    str(chunk['metadata'])
                ))
            
            conn.commit()
    
    def query(self, question: str, k: int = 5) -> List[Dict[str, Any]]:
        """Query the RAG system for relevant content."""
        results = self.vector_store.search(question, k)
        
        # Enhance results with additional context
        for result in results:
            metadata = result.get('metadata', {})
            
            # Add source-specific context
            if metadata.get('source_type') == 'faq':
                result['source_type_display'] = 'FAQ'
                result['answer_mode'] = metadata.get('answer_mode', 'UNKNOWN')
            elif metadata.get('source_type') == 'pdf':
                result['source_type_display'] = 'PDF Document'
                result['filename'] = metadata.get('filename', 'Unknown')
            elif metadata.get('source_type') == 'video':
                result['source_type_display'] = 'Video'
                result['title'] = metadata.get('title', 'Unknown')
            else:
                result['source_type_display'] = 'Web Page'
            
            result['source_url'] = metadata.get('source_url', '')
        
        return results
    
    def generate_answer(self, question: str, k: int = 5) -> Dict[str, Any]:
        """Generate an answer with citations using LLM for natural language."""
        # Retrieve relevant documents
        relevant_docs = self.query(question, k)
        
        if not relevant_docs:
            return {
                'answer': "I couldn't find relevant information to answer your question. Please try rephrasing or contact customer service.",
                'sources': [],
                'confidence': 0.0,
                'help_section': None
            }
        
        # Collect all FAQ answers from the database for the matched questions
        faq_contents = []
        source_urls = []
        
        for doc in relevant_docs:
            md = doc.get('metadata', {})
            if md.get('source_type') == 'faq' and md.get('faq_id'):
                faq_id = md.get('faq_id')
                with self.db._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT f.question, f.answer, f.answer_mode, p.url
                        FROM faqs f
                        JOIN pages p ON f.page_id = p.id
                        WHERE f.id = ?
                        LIMIT 1
                    """, (faq_id,))
                    row = cursor.fetchone()
                
                if row and row[1]:
                    faq_question, raw_answer, answer_mode, source_url = row
                    if '<' in raw_answer and '>' in raw_answer:
                        raw_answer = self._html_to_text_preserve_lists(raw_answer)
                    faq_contents.append({
                        'question': faq_question,
                        'answer': raw_answer,
                        'answer_mode': answer_mode,
                        'source_url': source_url
                    })
                    if source_url not in source_urls:
                        source_urls.append(source_url)
            else:
                # Non-FAQ content (page, pdf, video)
                content = doc.get('content', '')
                if content:
                    faq_contents.append({
                        'question': None,
                        'answer': content,
                        'answer_mode': md.get('source_type', 'page'),
                        'source_url': md.get('source_url', '')
                    })
                    if md.get('source_url') and md.get('source_url') not in source_urls:
                        source_urls.append(md.get('source_url'))
        
        if not faq_contents:
            return {
                'answer': "I couldn't find relevant information to answer your question. Please try rephrasing or contact customer service.",
                'sources': [],
                'confidence': 0.0,
                'help_section': None
            }
        
        # Build context from retrieved content
        context_parts = []
        for i, faq in enumerate(faq_contents[:5], 1):  # Use top 5 sources
            if faq['question']:
                context_parts.append(f"Source {i} (FAQ):\nQ: {faq['question']}\nA: {faq['answer']}")
            else:
                context_parts.append(f"Source {i}:\n{faq['answer']}")
        
        context = "\n\n".join(context_parts)
        
        # Generate answer using LLM if available
        if self.llm_client:
            answer = self._generate_llm_answer(question, context)
        else:
            # Fallback: use the best matching FAQ answer directly
            best_faq = faq_contents[0]
            answer = best_faq['answer']
        
        # Extract help section if present
        help_section = self._extract_help_section(answer)
        if help_section:
            answer = self._remove_help_section_from_answer(answer)
        
        # Build sources list - only show the single best source (highest similarity, deepest depth)
        # The best source is the first FAQ content which has the actual answer
        best_source = None
        best_similarity = 0.0
        
        for i, faq in enumerate(faq_contents):
            url = faq.get('source_url', '')
            if url and faq.get('answer'):
                # Get similarity score from corresponding relevant_doc
                similarity = relevant_docs[i].get('similarity_score', 0.0) if i < len(relevant_docs) else 0.0
                # Prefer FAQ sources (deepest depth where answer exists) with highest similarity
                if faq.get('question') and similarity >= best_similarity:
                    best_similarity = similarity
                    best_source = {
                        'content': faq['answer'][:200] + '...' if len(faq['answer']) > 200 else faq['answer'],
                        'source_type': 'FAQ',
                        'source_url': url,
                        'similarity_score': similarity,
                        'answer_mode': faq.get('answer_mode', 'UNKNOWN')
                    }
        
        # Fallback to first source if no FAQ found
        if not best_source and faq_contents:
            faq = faq_contents[0]
            best_source = {
                'content': faq['answer'][:200] + '...' if len(faq['answer']) > 200 else faq['answer'],
                'source_type': 'FAQ' if faq.get('question') else faq.get('answer_mode', 'Page'),
                'source_url': faq.get('source_url', ''),
                'similarity_score': relevant_docs[0].get('similarity_score', 0.0),
                'answer_mode': faq.get('answer_mode', 'UNKNOWN')
            }
        
        sources = [best_source] if best_source else []
        
        return {
            'answer': answer,
            'sources': sources,
            'confidence': best_similarity if best_similarity > 0 else relevant_docs[0].get('similarity_score', 0.0),
            'query': question,
            'help_section': help_section
        }
    
    def _generate_llm_answer(self, question: str, context: str) -> str:
        """Generate a natural language answer using OpenAI LLM."""
        try:
            system_prompt = """You are a helpful customer service assistant for Toyota Financial Services. 
Your job is to answer customer questions based on the provided FAQ content.

Instructions:
- Provide a complete, natural language answer based on the source content provided.
- Include ALL relevant information from the sources - do not truncate or summarize excessively.
- If the answer involves steps or a list, present them clearly.
- If there are links or resources mentioned, include them.
- Be friendly and professional.
- If the sources don't fully answer the question, say so and suggest contacting customer service.
- Do NOT make up information that isn't in the sources."""

            user_prompt = f"""Customer Question: {question}

Relevant Information from Toyota Financial Services:
{context}

Please provide a complete, helpful answer to the customer's question based on the information above."""

            response = self.llm_client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            self.logger.error(f"LLM generation error: {e}")
            # Fallback to raw content
            return context.split('\n\n')[0].replace('Source 1 (FAQ):\nQ: ', '').replace('\nA: ', '\n\n')

    def _html_to_text_preserve_lists(self, html: str) -> str:
        soup = BeautifulSoup(html, 'html.parser')
        items = [li.get_text(' ', strip=True) for li in soup.find_all('li')]
        items = [it for it in items if it]
        if items:
            return "\n".join(items)
        return soup.get_text(' ', strip=True)
    
    def _remove_question_repetition(self, question: str, answer: str) -> str:
        """Remove ALL question text from the answer, not just repetitions."""
        if not question or not answer:
            return answer
        
        # Remove the entire question if it appears at the start
        question_words = question.lower().split()
        
        # Check if the question is repeated in the answer
        if len(question_words) > 3:
            # Look for the question in the answer (first 100 chars)
            question_pattern = re.escape(question[:100])  # First 100 chars
            if re.search(question_pattern, answer, re.IGNORECASE):
                # Remove the question from the answer
                answer = re.sub(question_pattern, '', answer, flags=re.IGNORECASE)
                answer = re.sub(r'^\s*[-:]\s*', '', answer.strip())  # Remove leading dashes/colons
        
        # Also remove any remaining question text that appears at the start
        # Common patterns to remove
        patterns_to_remove = [
            r'^.*?\?\s*[-:]?\s*',  # Question followed by dash or colon
            r'^.*?Toyota Financial\s*[-:]?\s*',  # Toyota Financial prefix
            r'^.*?What is\s*[-:]?\s*',  # "What is" prefix
            r'^.*?How do\s*[-:]?\s*',  # "How do" prefix
            r'^.*?Pay Online\s*[-:]?\s*',  # "Pay Online" prefix
            r'^.*?and how can I enroll\s*[-:]?\s*',  # "and how can I enroll" prefix
            r'^Pay Online\s*[-:]?\s*',  # Standalone "Pay Online" prefix
        ]
        
        for pattern in patterns_to_remove:
            answer = re.sub(pattern, '', answer, flags=re.IGNORECASE)
        
        # Remove any remaining question-like text at the beginning
        lines = answer.split('\n')
        if lines:
            first_line = lines[0].strip()
            # If first line looks like a question, remove it
            if '?' in first_line and len(first_line) < 100:
                lines = lines[1:]  # Remove first line
                answer = '\n'.join(lines)
        
        return answer.strip()
    
    def _format_answer_as_bullets(self, answer: str) -> str:
        """Format answer as bullet points with proper line breaks."""
        if not answer:
            return answer

        # If content already has multiple lines, treat each non-empty line as an item.
        raw_lines = [ln.strip() for ln in answer.splitlines() if ln.strip()]
        if len(raw_lines) > 1:
            items: List[str] = []
            for ln in raw_lines:
                ln = re.sub(r'^[\-\*\•]\s*', '', ln).strip()
                if len(ln) > 0:
                    items.append(ln)

            items = [it for it in items if len(it) > 0]
            if len(items) > 1:
                return "\n\n".join([f"• {it}" for it in items])
            if len(items) == 1:
                return items[0]

        # If content uses semicolons as list separators, split on them.
        if answer.count(';') >= 2:
            parts = [p.strip() for p in answer.split(';') if p.strip()]
            if len(parts) > 1:
                return "\n\n".join([f"• {p}" for p in parts])
        
        # Split into sentences using multiple punctuation marks
        sentences = re.split(r'[.!?]+', answer)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # Filter out very short or incomplete sentences
        valid_sentences = []
        for sentence in sentences:
            # Remove leading bullet characters if present
            sentence = re.sub(r'^[\-\*\•]\s*', '', sentence)
            sentence = sentence.strip()
            
            # Only include sentences that are substantial
            if len(sentence) > 10 and not sentence.lower().startswith(('still need', 'couldnt find', 'dont worry')):
                valid_sentences.append(sentence)
        
        # If there are multiple valid sentences, format as bullets with line breaks
        if len(valid_sentences) > 1:
            bullet_points = []
            for sentence in valid_sentences:
                # Add bullet point with proper spacing
                bullet_points.append(f"• {sentence}")
            
            # Join with line breaks for proper formatting
            return "\n\n".join(bullet_points)
        
        # For single sentence, just return as is
        return valid_sentences[0] if valid_sentences else answer.strip()
    
    def _extract_help_section(self, answer: str) -> Optional[str]:
        """Extract 'Still need help' section from answer."""
        help_patterns = [
            r'still\s+need\s+help.*?(?=\n\n|$)',
            r'contact\s+us.*?(?=\n\n|$)',
            r'need\s+more\s+help.*?(?=\n\n|$)',
            r'couldn\'t\s+find.*?contact.*?(?=\n\n|$)'
        ]
        
        for pattern in help_patterns:
            match = re.search(pattern, answer, re.IGNORECASE | re.DOTALL)
            if match:
                help_text = match.group(0).strip()
                # Format help section as bullets too
                return self._format_answer_as_bullets(help_text)
        
        return None
    
    def _remove_help_section_from_answer(self, answer: str) -> str:
        """Remove help section from the main answer."""
        help_patterns = [
            r'\n?still\s+need\s+help.*?(?=\n\n|$)',
            r'\n?contact\s+us.*?(?=\n\n|$)',
            r'\n?need\s+more\s+help.*?(?=\n\n|$)',
            r'\n?couldn\'t\s+find.*?contact.*?(?=\n\n|$)'
        ]
        
        for pattern in help_patterns:
            answer = re.sub(pattern, '', answer, flags=re.IGNORECASE | re.DOTALL)
        
        return answer.strip()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG system statistics."""
        vector_stats = self.vector_store.get_stats()
        
        # Add database stats
        with self.db._connect() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM content_blocks")
            content_blocks = cursor.fetchone()[0]
            
            cursor.execute("SELECT source_type, COUNT(*) FROM content_blocks GROUP BY source_type")
            source_distribution = dict(cursor.fetchall())
        
        return {
            'vector_store': vector_stats,
            'content_blocks': content_blocks,
            'source_distribution': source_distribution
        }
