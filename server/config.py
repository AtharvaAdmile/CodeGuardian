"""
CodeGuardian Server Configuration.

Uses pydantic-settings to read configuration from environment variables
and .env file. All LLM/embedding calls go through NVIDIA NIM API.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ──────────────────────────────────────────────────────────
    server_host: str = "0.0.0.0"
    server_port: int = 8742

    # ── NVIDIA NIM API ──────────────────────────────────────────────────
    nvidia_nim_api_key: str = ""
    nvidia_nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_llm_model: str = "qwen/qwen3-coder-480b-a35b-instruct"
    nvidia_embed_model: str = "nvidia/nv-embedqa-e5-v5"

    # ── Supabase ────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""

    # ── ChromaDB ────────────────────────────────────────────────────────
    chromadb_persist_dir: str = "./chroma_data"

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Create and return a Settings instance (cached via lru_cache if needed)."""
    return Settings()
