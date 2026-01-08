"""
Configuration management for FAQ Scraper.
Loads and validates YAML configuration.
"""

import yaml
from pathlib import Path
from typing import List, Dict, Any
import logging


class Config:
    """Configuration class for the FAQ scraper."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self._config = self._load_config()
        self._validate_config()
        self._create_directories()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {self.config_path}")
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logging.info(f"Loaded configuration from {self.config_path}")
            return config
            
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            raise
    
    def _validate_config(self):
        """Validate required configuration fields."""
        required_fields = [
            'seed_urls',
            'allowed_domains',
            'crawl_depth',
            'max_pages',
            'request_rate_limit',
            'user_agent',
            'data_dir',
            'db_path'
        ]
        
        for field in required_fields:
            if field not in self._config:
                raise ValueError(f"Missing required config field: {field}")
        
        # Validate seed URLs
        if not isinstance(self._config['seed_urls'], list) or len(self._config['seed_urls']) == 0:
            raise ValueError("seed_urls must be a non-empty list")
        
        # Validate seed URLs are non-empty
        if not self._config['seed_urls'] or len(self._config['seed_urls']) == 0:
            raise ValueError("seed_urls must contain at least one URL")
        
        # Validate numeric values
        if self._config['crawl_depth'] < 1 or self._config['crawl_depth'] > 5:
            raise ValueError("crawl_depth must be between 1 and 5")
        
        if self._config['max_pages'] < 1:
            raise ValueError("max_pages must be positive")
        
        if self._config['request_rate_limit'] <= 0:
            raise ValueError("request_rate_limit must be positive")
    
    def _create_directories(self):
        """Create necessary directories."""
        directories = [
            self.data_dir,
            self.raw_dir,
            self.processed_dir,
            Path(self.db_path).parent,
            Path(self.log_file).parent
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
    
    @property
    def seed_urls(self) -> List[str]:
        return self._config['seed_urls']
    
    @property
    def allowed_domains(self) -> List[str]:
        return self._config['allowed_domains']
    
    @property
    def crawl_depth(self) -> int:
        return self._config['crawl_depth']
    
    @property
    def max_pages(self) -> int:
        return self._config['max_pages']
    
    @property
    def request_rate_limit(self) -> float:
        return self._config['request_rate_limit']
    
    @property
    def user_agent(self) -> str:
        return self._config['user_agent']
    
    @property
    def data_dir(self) -> str:
        return self._config['data_dir']
    
    @property
    def raw_dir(self) -> str:
        return self._config['raw_dir']
    
    @property
    def processed_dir(self) -> str:
        return self._config['processed_dir']
    
    @property
    def db_path(self) -> str:
        return self._config['db_path']
    
    @property
    def embedding_model(self) -> str:
        return self._config.get('embedding_model', 'sentence-transformers/all-MiniLM-L6-v2')
    
    @property
    def vector_store_type(self) -> str:
        return self._config.get('vector_store_type', 'faiss')
    
    @property
    def vector_dim(self) -> int:
        return self._config.get('vector_dim', 384)
    
    @property
    def pdf_enabled(self) -> bool:
        return self._config.get('pdf_enabled', True)
    
    @property
    def video_enabled(self) -> bool:
        return self._config.get('video_enabled', True)
    
    @property
    def whisper_model_size(self) -> str:
        return self._config.get('whisper_model_size', 'base')
    
    @property
    def ui_host(self) -> str:
        return self._config.get('ui_host', 'localhost')
    
    @property
    def ui_port(self) -> int:
        return self._config.get('ui_port', 8501)
    
    @property
    def log_level(self) -> str:
        return self._config.get('log_level', 'INFO')
    
    @property
    def log_file(self) -> str:
        return self._config.get('log_file', './logs/scraper.log')
    
    @property
    def llm_enabled(self) -> bool:
        return self._config.get('llm_enabled', False)
    
    @property
    def llm_provider(self) -> str:
        return self._config.get('llm_provider', 'openai')
    
    @property
    def llm_model(self) -> str:
        return self._config.get('llm_model', 'gpt-3.5-turbo')
