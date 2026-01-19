"""
Configuration settings loader for CodeGuardian.

Loads configuration from .env and config.toml files.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

import toml
from dotenv import load_dotenv


@dataclass
class DatabaseConfig:
    """Supabase database configuration."""
    url: str = ""
    key: str = ""


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "gemini"
    model: str = "gemini-2.0-flash"
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""
    model: str = "models/text-embedding-004"
    dimension: int = 768
    batch_size: int = 32


@dataclass
class IndexingConfig:
    """File indexing configuration."""
    exclude_dirs: List[str] = field(default_factory=lambda: [
        ".git", "__pycache__", "node_modules", "venv", ".venv",
        "env", ".env", "dist", "build", ".idea", ".vscode", "site-packages"
    ])
    supported_extensions: List[str] = field(default_factory=lambda: [
        ".py", ".js", ".jsx", ".ts", ".tsx"
    ])


@dataclass
class ChunkingConfig:
    """Code chunking configuration."""
    min_chunk_tokens: int = 100
    max_chunk_tokens: int = 500
    overlap_tokens: int = 50


@dataclass
class RetrievalConfig:
    """RAG retrieval configuration."""
    initial_count: int = 10
    final_count: int = 5
    similarity_threshold: float = 0.7


@dataclass
class AgentConfig:
    """Agent configuration."""
    blast_radius_threshold: int = 5
    require_approval_above: int = 5


@dataclass
class Settings:
    """Complete application settings."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    
    # Additional settings from environment
    google_api_key: str = ""
    project_path: Optional[str] = None


def load_settings(project_path: Optional[str] = None) -> Settings:
    """
    Load settings from environment and config.toml.
    
    Args:
        project_path: Optional path to project directory containing config.toml
        
    Returns:
        Settings object with all configuration loaded
    """
    # Load environment variables
    load_dotenv()
    
    settings = Settings()
    
    # Load from environment
    settings.google_api_key = os.getenv("GOOGLE_API_KEY", "")
    settings.database.url = os.getenv("SUPABASE_URL", "")
    settings.database.key = os.getenv("SUPABASE_KEY", "")
    settings.project_path = project_path
    
    # Try to load config.toml
    config_paths = [
        Path(project_path) / "config.toml" if project_path else None,
        Path.cwd() / "config.toml",
        Path.home() / ".codeguardian" / "config.toml",
    ]
    
    for config_path in config_paths:
        if config_path and config_path.exists():
            try:
                config = toml.load(config_path)
                _apply_config(settings, config)
                break
            except Exception:
                continue
    
    return settings


def _apply_config(settings: Settings, config: dict) -> None:
    """Apply config.toml values to settings object."""
    
    if "database" in config:
        db = config["database"]
        if db.get("url"):
            settings.database.url = db["url"]
        if db.get("key"):
            settings.database.key = db["key"]
    
    if "llm" in config:
        llm = config["llm"]
        settings.llm.provider = llm.get("provider", settings.llm.provider)
        settings.llm.model = llm.get("model", settings.llm.model)
        settings.llm.temperature = llm.get("temperature", settings.llm.temperature)
        settings.llm.max_tokens = llm.get("max_tokens", settings.llm.max_tokens)
        settings.llm.stream = llm.get("stream", settings.llm.stream)
    
    if "embedding" in config:
        emb = config["embedding"]
        settings.embedding.model = emb.get("model", settings.embedding.model)
        settings.embedding.dimension = emb.get("dimension", settings.embedding.dimension)
        settings.embedding.batch_size = emb.get("batch_size", settings.embedding.batch_size)
    
    if "indexing" in config:
        idx = config["indexing"]
        settings.indexing.exclude_dirs = idx.get("exclude_dirs", settings.indexing.exclude_dirs)
        settings.indexing.supported_extensions = idx.get("supported_extensions", settings.indexing.supported_extensions)
    
    if "chunking" in config:
        chunk = config["chunking"]
        settings.chunking.min_chunk_tokens = chunk.get("min_chunk_tokens", settings.chunking.min_chunk_tokens)
        settings.chunking.max_chunk_tokens = chunk.get("max_chunk_tokens", settings.chunking.max_chunk_tokens)
        settings.chunking.overlap_tokens = chunk.get("overlap_tokens", settings.chunking.overlap_tokens)
    
    if "retrieval" in config:
        ret = config["retrieval"]
        settings.retrieval.initial_count = ret.get("initial_count", settings.retrieval.initial_count)
        settings.retrieval.final_count = ret.get("final_count", settings.retrieval.final_count)
        settings.retrieval.similarity_threshold = ret.get("similarity_threshold", settings.retrieval.similarity_threshold)
    
    if "agent" in config:
        agent = config["agent"]
        settings.agent.blast_radius_threshold = agent.get("blast_radius_threshold", settings.agent.blast_radius_threshold)
        settings.agent.require_approval_above = agent.get("require_approval_above", settings.agent.require_approval_above)


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings(project_path: Optional[str] = None) -> Settings:
    """Get global settings instance, loading if necessary."""
    global _settings
    if _settings is None or project_path:
        _settings = load_settings(project_path)
    return _settings
