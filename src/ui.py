"""
Streamlit UI for Toyota FAQ Scraper with chatbot and metrics dashboard.
Provides interactive interface for RAG chatbot and CX metrics visualization.
"""

import sys
from pathlib import Path

# Add project root to Python path
try:
    project_root = Path(__file__).parent.parent
except NameError:
    # __file__ is not defined, use current working directory
    project_root = Path.cwd()
sys.path.insert(0, str(project_root))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any
import logging

from src.config import Config
from src.database import DatabaseManager
from src.metrics import MetricsAnalyzer
from src.vector_store import RAGSystem


class StreamlitUI:
    """Streamlit-based UI for the Toyota FAQ Scraper application."""
    
    def __init__(self):
        self.config = Config()
        self.db = DatabaseManager(self.config.db_path)
        self.metrics_analyzer = MetricsAnalyzer(self.config, self.db)
        self.rag_system = RAGSystem(self.config, self.db)
        
        # Configure page with Toyota-style favicon
        st.set_page_config(
            page_title="Toyota Financial Services FAQ Analysis",
            page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%23eb0a1e'/><ellipse cx='16' cy='16' rx='12' ry='8' stroke='white' stroke-width='2' fill='none'/><ellipse cx='16' cy='16' rx='5' ry='8' stroke='white' stroke-width='2' fill='none'/><line x1='4' y1='16' x2='28' y2='16' stroke='white' stroke-width='2'/></svg>",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Custom CSS - Clean modern design
        st.markdown("""
        <style>
            /* Hide default Streamlit elements */
            .stApp > header {display: none;}
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            
            /* Global font improvements */
            html, body, [class*="css"] {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            }

            /* Top navigation bar */
            .tfs-header {
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                padding: 0;
                margin: -1rem -1rem 1.5rem -1rem;
                border-radius: 0;
            }
            .tfs-header-inner {
                max-width: 1400px;
                margin: 0 auto;
                padding: 1rem 2rem;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            .tfs-logo-section {
                display: flex;
                align-items: center;
                gap: 14px;
            }
            .tfs-logo {
                width: 48px;
                height: 48px;
                background: #eb0a1e;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 12px rgba(235, 10, 30, 0.3);
            }
            .tfs-logo svg {
                width: 32px;
                height: 32px;
            }
            .tfs-brand-text {
                display: flex;
                flex-direction: column;
            }
            .tfs-brand-name {
                font-size: 1.25rem;
                font-weight: 700;
                color: #ffffff;
                letter-spacing: -0.02em;
            }
            .tfs-brand-tagline {
                font-size: 0.75rem;
                color: rgba(255, 255, 255, 0.7);
                font-weight: 500;
                letter-spacing: 0.02em;
            }

            /* Metric cards */
            .metric-card {
                background: #ffffff;
                padding: 1.25rem;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            }
            .metric-card:hover {
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
                border-color: #d1d5db;
            }
            
            /* Insight cards */
            .insight-critical {
                border-left: 4px solid #ef4444;
                background: linear-gradient(to right, #fef2f2, #ffffff);
            }
            .insight-warning {
                border-left: 4px solid #f59e0b;
                background: linear-gradient(to right, #fffbeb, #ffffff);
            }
            .insight-positive {
                border-left: 4px solid #10b981;
                background: linear-gradient(to right, #ecfdf5, #ffffff);
            }
            .insight-info {
                border-left: 4px solid #3b82f6;
                background: linear-gradient(to right, #eff6ff, #ffffff);
            }

            /* Chat styling */
            .stChatMessage {
                background: #f9fafb;
                border-radius: 12px;
                padding: 0.5rem;
            }
            
            /* Source card styling */
            .source-card {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px 16px;
                margin: 8px 0;
            }
            .source-link {
                color: #eb0a1e;
                text-decoration: none;
                font-weight: 600;
            }
            .source-link:hover {
                text-decoration: underline;
            }
            
            /* Sidebar styling */
            section[data-testid="stSidebar"] {
                background: #f8fafc;
            }
            section[data-testid="stSidebar"] .stSelectbox label {
                font-weight: 600;
                color: #374151;
            }
            
            /* Button styling */
            .stButton > button {
                border-radius: 8px;
                font-weight: 600;
                transition: all 0.2s;
            }
            .stButton > button:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            }
        </style>
        """, unsafe_allow_html=True)
    
    def render_header(self):
        """Render application header with Toyota-inspired branding."""
        st.markdown(
            """
            <div class="tfs-header">
                <div class="tfs-header-inner">
                    <div class="tfs-logo-section">
                        <div class="tfs-logo">
                            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <!-- Toyota-inspired ellipse logo -->
                                <ellipse cx="16" cy="16" rx="14" ry="10" stroke="white" stroke-width="2" fill="none"/>
                                <ellipse cx="16" cy="16" rx="6" ry="10" stroke="white" stroke-width="2" fill="none"/>
                                <line x1="2" y1="16" x2="30" y2="16" stroke="white" stroke-width="2"/>
                            </svg>
                        </div>
                        <div class="tfs-brand-text">
                            <span class="tfs-brand-name">Toyota Financial Services</span>
                            <span class="tfs-brand-tagline">FAQ Analysis Dashboard</span>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    
    def render_sidebar(self):
        """Render sidebar with navigation and info."""
        with st.sidebar:
            # Sidebar branding
            st.markdown("""
            <div style="text-align: center; padding: 1rem 0; margin-bottom: 1rem; border-bottom: 1px solid #e5e7eb;">
                <div style="font-size: 1.1rem; font-weight: 700; color: #1f2937;">Navigation</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Page selection with cleaner styling
            page = st.selectbox(
                "Select Page",
                ["📊 Metrics Dashboard", "💬 FAQ Chatbot", "📈 Detailed Analytics", "⚙️ System Info"],
                label_visibility="collapsed"
            )
            
            st.markdown("---")
            
            # System status with cleaner cards
            st.markdown("""
            <div style="font-size: 0.9rem; font-weight: 600; color: #6b7280; margin-bottom: 0.75rem;">
                SYSTEM STATUS
            </div>
            """, unsafe_allow_html=True)
            
            try:
                stats = self.metrics_analyzer.get_overall_statistics()
                rag_stats = self.rag_system.get_stats()
                
                # Compact metrics display
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Pages", stats['pages']['total'])
                    st.metric("PDFs", f"{stats['pdfs']['processed']}")
                    st.metric("Videos", f"{stats['videos']['processed']}")
                with col2:
                    st.metric("FAQs", stats['faqs']['total'])
                    st.metric("Indexed", rag_stats['vector_store']['total_documents'])
                
            except Exception as e:
                st.error(f"Error: {e}")
            
            st.markdown("---")
            
            # Quick actions with better styling
            st.markdown("""
            <div style="font-size: 0.9rem; font-weight: 600; color: #6b7280; margin-bottom: 0.75rem;">
                QUICK ACTIONS
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Refresh", use_container_width=True):
                    st.rerun()
            with col2:
                if st.button("📥 Export", use_container_width=True):
                    self.export_metrics()
            
            if st.button("🗑️ Clear Cache", use_container_width=True):
                self.clear_cache()
        
        return page
    
    def render_metrics_dashboard(self):
        """Render main metrics dashboard."""
        st.header("📊 Customer Experience Metrics Dashboard")
        
        try:
            # Get metrics
            cx_metrics = self.metrics_analyzer.get_customer_experience_metrics()
            stats = self.metrics_analyzer.get_overall_statistics()
            answer_modes = self.metrics_analyzer.get_answer_mode_distribution()
            
            # Key metrics row
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Direct Answers",
                    f"{cx_metrics['direct_answers']['percentage']:.1f}%",
                    delta=None,
                    help="Percentage of FAQs that provide direct answers without requiring additional actions"
                )
            
            with col2:
                st.metric(
                    "Customer Effort",
                    f"{cx_metrics['customer_effort']['score']:.2f}/3.0",
                    delta=None,
                    help="Average effort score (1=Low, 3=High)"
                )
            
            with col3:
                st.metric(
                    "Escalation Rate",
                    f"{cx_metrics['escalation_required']['percentage']:.1f}%",
                    delta=None,
                    help="Percentage of FAQs requiring phone calls or external resources"
                )
            
            with col4:
                st.metric(
                    "Media Dependency",
                    f"{cx_metrics['media_dependency']['total_media_dependency']:.1f}%",
                    delta=None,
                    help="Percentage of FAQs requiring PDFs or videos"
                )
            
            st.markdown("---")
            
            # Charts row
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Answer Mode Distribution")
                
                # Prepare data for pie chart
                distribution = answer_modes.get('distribution', {})
                if distribution:
                    df = pd.DataFrame([
                        {'Mode': mode, 'Count': data['count']}
                        for mode, data in distribution.items()
                    ])
                    
                    fig = px.pie(
                        df, 
                        values='Count', 
                        names='Mode',
                        title='FAQ Answer Types',
                        color_discrete_map={
                            'DIRECT_TEXT': '#28a745',
                            'PHONE_ESCALATION': '#dc3545',
                            'LINK_OUT': '#ffc107',
                            'PDF_ATTACHMENT': '#17a2b8',
                            'VIDEO': '#6f42c1',
                            'PORTAL_REDIRECT': '#fd7e14'
                        }
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info("No FAQ data available")
            
            with col2:
                st.subheader("Customer Experience Assessment")
                
                # Create assessment gauge chart
                assessments = [
                    ('Content Quality', cx_metrics['direct_answers']['assessment']),
                    ('Customer Effort', cx_metrics['customer_effort']['assessment']),
                    ('Escalation Level', cx_metrics['escalation_required']['assessment']),
                    ('Navigation', cx_metrics['navigation_complexity']['assessment'])
                ]
                
                assessment_data = []
                for name, assessment in assessments:
                    score = 3 if assessment == 'Poor' else 2 if assessment == 'Moderate' else 1
                    color = '#dc3545' if assessment == 'Poor' else '#ffc107' if assessment == 'Moderate' else '#28a745'
                    assessment_data.append({'Aspect': name, 'Score': score, 'Assessment': assessment, 'Color': color})
                
                df_assessments = pd.DataFrame(assessment_data)

                fig = make_subplots(
                    rows=2,
                    cols=2,
                    specs=[[{"type": "indicator"}, {"type": "indicator"}], [{"type": "indicator"}, {"type": "indicator"}]],
                    vertical_spacing=0.2,
                    horizontal_spacing=0.1,
                )

                for idx, row in enumerate(df_assessments.itertuples(index=False), start=1):
                    r = 1 if idx <= 2 else 2
                    c = idx if idx <= 2 else idx - 2
                    fig.add_trace(
                        go.Indicator(
                            mode="gauge+number",
                            value=row.Score,
                            title={"text": row.Aspect, "font": {"size": 14}},
                            number={"font": {"size": 44}},
                            gauge={
                                "axis": {"range": [0, 3], "tickwidth": 1, "tickcolor": "rgba(107,114,128,0.9)"},
                                "bar": {"color": row.Color},
                                "steps": [
                                    {"range": [0, 1], "color": "#e5e7eb"},
                                    {"range": [1, 2], "color": "#9ca3af"},
                                    {"range": [2, 3], "color": "#6b7280"},
                                ],
                                "threshold": {"line": {"color": "#ef4444", "width": 3}, "thickness": 0.75, "value": 2.5},
                            },
                        ),
                        row=r,
                        col=c,
                    )

                fig.update_layout(
                    height=420,
                    margin={"t": 30, "r": 10, "b": 10, "l": 10},
                    showlegend=False,
                )
                st.plotly_chart(fig, width='stretch')
            
            st.markdown("---")
            
            # Business Insights
            st.subheader("🎯 Business Insights & Recommendations")
            
            insights = self.metrics_analyzer.generate_business_insights()
            
            if insights:
                for insight in insights:
                    insight_class = f"insight-{insight['type']}"
                    
                    with st.container():
                        st.markdown(f"""
                        <div class="metric-card {insight_class}">
                            <h4>{insight['title']}</h4>
                            <p><strong>Impact:</strong> {insight['impact']}</p>
                            <p><strong>Description:</strong> {insight['description']}</p>
                            <p><strong>Recommendation:</strong> {insight['recommendation']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown("---")
            else:
                st.info("No insights available")
        
        except Exception as e:
            st.error(f"Error loading metrics dashboard: {e}")
    
    def render_chatbot(self):
        """Render FAQ chatbot interface."""
        # Clean header section
        st.markdown("""
        <div style="margin-bottom: 1.5rem;">
            <h2 style="margin: 0; color: #1f2937;">💬 FAQ Assistant</h2>
            <p style="color: #6b7280; margin-top: 0.5rem; font-size: 0.95rem;">
                Ask questions about Toyota Financial Services. Get instant answers with source citations.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        # Initialize chat history
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        
        def _toggle_state(state_key: str):
            st.session_state[state_key] = not st.session_state.get(state_key, False)

        # Display chat messages
        for idx, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                if message["role"] == "assistant":
                    # Show help section if present
                    if message.get("help_section"):
                        st.markdown("---")
                        st.info(f"🆘 **Still need help?**\n\n{message['help_section']}")
                    
                    # Show sources if present
                    if "sources" in message and message["sources"]:
                        state_key = f"msg_sources_open_{idx}"
                        button_key = f"{state_key}_btn"
                        if state_key not in st.session_state:
                            st.session_state[state_key] = False

                        col1, col2 = st.columns([20, 1])
                        with col1:
                            st.markdown("**Sources**")
                        with col2:
                            st.button(
                                "▸" if not st.session_state[state_key] else "▾",
                                key=button_key,
                                on_click=_toggle_state,
                                args=(state_key,),
                            )

                        # Show sources only if expanded
                        if st.session_state[state_key]:
                            # Remove duplicate sources
                            unique_sources = []
                            seen_urls = set()
                            
                            for source in message["sources"]:
                                if source['source_url'] not in seen_urls:
                                    unique_sources.append(source)
                                    seen_urls.add(source['source_url'])
                            
                            for i, source in enumerate(unique_sources, 1):
                                st.markdown(f"**Source {i}:** {source['source_type']}")
                                st.markdown(f"**Content:** {source['content']}")
                                st.markdown(f"**🔗 [View Source]({source['source_url']})**")
                                st.markdown(f"**Similarity:** {source['similarity_score']:.3f}")
                                st.markdown("---")
        
        # Chat input
        if prompt := st.chat_input("Ask about Toyota Financial Services..."):
            # Add user message
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Generate response
            with st.chat_message("assistant"):
                with st.spinner("Searching for relevant information..."):
                    try:
                        response = self.rag_system.generate_answer(prompt, k=3)
                        
                        # Display answer
                        if response['answer'] and len(response['answer'].strip()) > 0:
                            st.markdown(response['answer'])
                        else:
                            st.error("⚠️ Answer appears to be empty or blank")
                            st.info(f"Debug info: Answer length = {len(response['answer'])}")
                            if response['answer']:
                                st.code(response['answer'])
                        
                        # Display help section if present
                        if response.get('help_section'):
                            st.markdown("---")
                            st.info(f"🆘 **Still need help?**\n\n{response['help_section']}")
                        
                        # Display confidence
                        confidence = response['confidence']
                        if confidence > 0.7:
                            st.success(f"Confidence: {confidence:.2f}")
                        elif confidence > 0.4:
                            st.warning(f"Confidence: {confidence:.2f}")
                        else:
                            st.error(f"Confidence: {confidence:.2f}")
                        
                        # Display sources with better toggle
                        if response['sources']:
                            st.markdown("---")

                            state_key = f"resp_sources_open_{len(st.session_state.messages)}"
                            button_key = f"{state_key}_btn"
                            if state_key not in st.session_state:
                                st.session_state[state_key] = False

                            col1, col2 = st.columns([20, 1])
                            with col1:
                                st.markdown("**Sources**")
                            with col2:
                                st.button(
                                    "▸" if not st.session_state[state_key] else "▾",
                                    key=button_key,
                                    on_click=_toggle_state,
                                    args=(state_key,),
                                )

                            # Show sources only if expanded
                            if st.session_state[state_key]:
                                # Remove duplicate sources
                                unique_sources = []
                                seen_urls = set()
                                
                                for source in response['sources']:
                                    if source['source_url'] not in seen_urls:
                                        unique_sources.append(source)
                                        seen_urls.add(source['source_url'])
                                
                                for i, source in enumerate(unique_sources, 1):
                                    with st.container():
                                        st.markdown(f"**Source {i}:** {source['source_type']}")
                                        st.markdown(f"**Content:** {source['content']}")
                                        st.markdown(f"**🔗 [View Source]({source['source_url']})**")
                                        st.markdown(f"**Similarity:** {source['similarity_score']:.3f}")
                                        st.markdown("---")
                        
                        # Add sources to message
                        message_with_sources = {
                            "role": "assistant", 
                            "content": response['answer'],
                            "sources": response['sources'],
                            "help_section": response.get('help_section')
                        }
                        
                    except Exception as e:
                        error_message = f"I apologize, but I encountered an error while processing your question: {str(e)}"
                        st.error(error_message)
                        message_with_sources = {
                            "role": "assistant", 
                            "content": error_message
                        }
            
            # Add assistant message to session state
            st.session_state.messages.append(message_with_sources)
        
        # Clear chat button
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.rerun()
    
    def render_detailed_analytics(self):
        """Render detailed analytics page."""
        st.header("📈 Detailed Analytics")
        
        try:
            # Get comprehensive metrics
            report = self.metrics_analyzer.generate_metrics_report()
            
            # Content Overview
            st.subheader("Content Overview")
            
            col1, col2 = st.columns(2)
            
            with col1:
                stats = report['overall_statistics']
                
                st.markdown("**Pages & Content**")
                st.write(f"• Total pages crawled: {stats['pages']['total']}")
                st.write(f"• Successful extractions: {stats['pages']['successful']}")
                st.write(f"• FAQs extracted: {stats['faqs']['total']}")
                st.write(f"• Average FAQs per page: {stats['faqs']['avg_per_page']:.1f}")
                
                st.markdown("**Media Content**")
                st.write(f"• PDFs found: {stats['pdfs']['total']}")
                st.write(f"• PDFs processed: {stats['pdfs']['processed']}")
                st.write(f"• Videos found: {stats['videos']['total']}")
                st.write(f"• Videos processed: {stats['videos']['processed']}")
            
            with col2:
                depth_analysis = report['content_depth_analysis']
                
                st.markdown("**Navigation Analysis**")
                st.write(f"• Average depth to answer: {depth_analysis['avg_depth_to_answer']:.2f}")
                st.write(f"• Maximum depth to answer: {depth_analysis['max_depth_to_answer']}")
                st.write(f"• Pages with phone numbers: {depth_analysis['pages_with_phone_numbers']}")
                
                # Depth distribution chart
                if depth_analysis['page_depth_distribution']:
                    df_depth = pd.DataFrame([
                        {'Depth': str(k), 'Count': v}
                        for k, v in depth_analysis['page_depth_distribution'].items()
                    ])
                    
                    fig = px.bar(
                        df_depth, 
                        x='Depth', 
                        y='Count',
                        title='Page Depth Distribution'
                    )
                    st.plotly_chart(fig, width='stretch')
            
            st.markdown("---")
            
            # Answer Mode Analysis
            st.subheader("Answer Mode Analysis")
            
            answer_modes = report['answer_mode_distribution']
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Distribution table
                distribution = answer_modes.get('distribution', {})
                if distribution:
                    df_modes = pd.DataFrame([
                        {
                            'Answer Mode': mode,
                            'Count': data['count'],
                            'Percentage': f"{data['percentage']:.1f}%"
                        }
                        for mode, data in distribution.items()
                    ])
                    
                    st.dataframe(df_modes, width='stretch')
            
            with col2:
                # Key metrics
                st.metric("Direct Answer Rate", f"{answer_modes.get('direct_answer_rate', 0):.1f}%")
                st.metric("Escalation Required", f"{answer_modes.get('escalation_required_rate', 0):.1f}%")
                st.metric("Total FAQs", answer_modes.get('total_faqs', 0))
            
            st.markdown("---")
            
            # Content Type Analysis
            st.subheader("Content Type Analysis")
            
            content_types = report['content_type_analysis']
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Page Content Types**")
                page_types = content_types.get('page_content_types', {})
                if page_types:
                    df_types = pd.DataFrame([
                        {'Content Type': k, 'Count': v}
                        for k, v in page_types.items()
                    ])
                    
                    fig = px.pie(
                        df_types,
                        values='Count',
                        names='Content Type',
                        title='Page Content Types'
                    )
                    st.plotly_chart(fig, width='stretch')
            
            with col2:
                st.markdown("**Media Statistics**")
                pdfs = content_types.get('pdfs', {})
                videos = content_types.get('videos', {})
                
                st.write(f"• Average PDF pages: {pdfs.get('avg_pages', 0):.1f}")
                st.write(f"• Total PDF pages: {pdfs.get('total_pages', 0)}")
                st.write(f"• Average video duration: {videos.get('avg_duration_minutes', 0):.1f} minutes")
                st.write(f"• Total video duration: {videos.get('total_duration_seconds', 0) / 3600:.1f} hours")
        
        except Exception as e:
            st.error(f"Error loading detailed analytics: {e}")
    
    def render_system_info(self):
        """Render system information page."""
        st.header("⚙️ System Information")
        
        try:
            # Configuration
            st.subheader("Configuration")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Crawl Settings**")
                st.write(f"• Seed URLs: {len(self.config.seed_urls)}")
                st.write(f"• Crawl depth: {self.config.crawl_depth}")
                st.write(f"• Max pages: {self.config.max_pages}")
                st.write(f"• Rate limit: {self.config.request_rate_limit} req/s")
                
                st.markdown("**Allowed Domains**")
                for domain in self.config.allowed_domains:
                    st.write(f"• {domain}")
            
            with col2:
                st.markdown("**Processing Settings**")
                st.write(f"• PDF processing: {'Enabled' if self.config.pdf_enabled else 'Disabled'}")
                st.write(f"• Video processing: {'Enabled' if self.config.video_enabled else 'Disabled'}")
                st.write(f"• Whisper model: {self.config.whisper_model_size}")
                
                st.markdown("**Vector Store**")
                st.write(f"• Embedding model: {self.config.embedding_model}")
                st.write(f"• Vector dimension: {self.config.vector_dim}")
                st.write(f"• Store type: {self.config.vector_store_type}")
            
            st.markdown("---")
            
            # Database statistics
            st.subheader("Database Statistics")
            
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Table sizes
                tables = ['pages', 'faqs', 'pdfs', 'videos', 'links', 'content_blocks', 'metrics']
                
                table_stats = []
                for table in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        table_stats.append({'Table': table, 'Records': count})
                    except sqlite3.OperationalError:
                        table_stats.append({'Table': table, 'Records': 'N/A'})
                
                df_tables = pd.DataFrame(table_stats)
                st.dataframe(df_tables, width='stretch')
            
            st.markdown("---")
            
            # RAG System Stats
            st.subheader("RAG System Statistics")
            
            rag_stats = self.rag_system.get_stats()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Vector Store**")
                vector_stats = rag_stats['vector_store']
                st.write(f"• Total documents: {vector_stats['total_documents']}")
                st.write(f"• Index type: {vector_stats['index_type']}")
                st.write(f"• Dimension: {vector_stats['dimension']}")
                st.write(f"• Embedding model: {vector_stats['embedding_model']}")
            
            with col2:
                st.markdown("**Content Blocks**")
                st.write(f"• Total blocks: {rag_stats['content_blocks']}")
                
                source_dist = rag_stats['source_distribution']
                if source_dist:
                    st.write("• By source type:")
                    for source_type, count in source_dist.items():
                        st.write(f"  - {source_type}: {count}")
            
            st.markdown("---")
            
            # File system info
            st.subheader("File System")
            
            data_dir = Path(self.config.data_dir)
            raw_dir = Path(self.config.raw_dir)
            processed_dir = Path(self.config.processed_dir)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Data Directory Size", self._get_dir_size(data_dir))
            
            with col2:
                st.metric("Raw Files", len(list(raw_dir.glob("*"))))
            
            with col3:
                st.metric("Processed Files", len(list(processed_dir.glob("*"))))
        
        except Exception as e:
            st.error(f"Error loading system info: {e}")
    
    def _get_dir_size(self, path: Path) -> str:
        """Get human-readable directory size."""
        try:
            total_size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
            
            for unit in ['B', 'KB', 'MB', 'GB']:
                if total_size < 1024.0:
                    return f"{total_size:.1f} {unit}"
                total_size /= 1024.0
            return f"{total_size:.1f} TB"
        except:
            return "Unknown"
    
    def export_metrics(self):
        """Export metrics to JSON file."""
        try:
            export_path = self.metrics_analyzer.export_metrics_to_json()
            st.success(f"Metrics exported to: {export_path}")
        except Exception as e:
            st.error(f"Error exporting metrics: {e}")
    
    def clear_cache(self):
        """Clear application cache."""
        try:
            # Clear vector store cache
            if hasattr(self.rag_system, 'vector_store'):
                self.rag_system.vector_store.documents = []
                self.rag_system.vector_store.index = None
            
            st.success("Cache cleared successfully")
            st.rerun()
        except Exception as e:
            st.error(f"Error clearing cache: {e}")
    
    def run(self):
        """Run the Streamlit application."""
        self.render_header()
        page = self.render_sidebar()
        
        if page == "📊 Metrics Dashboard":
            self.render_metrics_dashboard()
        elif page == "💬 FAQ Chatbot":
            self.render_chatbot()
        elif page == "📈 Detailed Analytics":
            self.render_detailed_analytics()
        elif page == "⚙️ System Info":
            self.render_system_info()


def main():
    """Main entry point for Streamlit UI."""
    try:
        app = StreamlitUI()
        app.run()
    except Exception as e:
        st.error(f"Application error: {e}")
        st.exception(e)


if __name__ == "__main__":
    main()
