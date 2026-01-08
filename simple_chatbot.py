#!/usr/bin/env python3
"""
Simple FAQ Chatbot for Toyota Financial Services
Tests the RAG system with extracted FAQs
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import Config
from src.database import DatabaseManager
from src.vector_store import RAGSystem

def main():
    print("🚗 Toyota Financial Services FAQ Chatbot")
    print("=" * 50)
    print("Type 'quit' to exit")
    print("=" * 50)
    
    # Initialize system
    config = Config()
    db = DatabaseManager(config.db_path)
    rag_system = RAGSystem(config, db)
    
    # Get system stats
    stats = rag_system.get_stats()
    print(f"📊 System Stats:")
    print(f"   • Total documents: {stats['vector_store']['total_documents']}")
    print(f"   • Content blocks: {stats['content_blocks']}")
    print(f"   • Source types: {list(stats['source_distribution'].keys())}")
    print()
    
    # Chat loop
    while True:
        try:
            question = input("🤔 Ask a question: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not question:
                continue
            
            print(f"\n🔍 Searching for: {question}")
            print("-" * 40)
            
            # Get answer
            response = rag_system.generate_answer(question, k=3)
            
            print(f"💬 Answer: {response['answer']}")
            print(f"\n🎯 Confidence: {response['confidence']:.2f}")
            
            if response['sources']:
                print(f"\n📚 Sources:")
                for i, source in enumerate(response['sources'], 1):
                    print(f"   {i}. {source['source_type']}")
                    print(f"      URL: {source['source_url']}")
                    print(f"      Similarity: {source['similarity_score']:.3f}")
                    if source.get('answer_mode'):
                        print(f"      Answer Mode: {source['answer_mode']}")
            
            print("\n" + "=" * 50 + "\n")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Please try again.\n")

if __name__ == "__main__":
    main()
