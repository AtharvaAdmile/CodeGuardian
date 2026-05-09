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
    nvidia_llm_model: str = "openai/gpt-oss-120b"
    nvidia_embed_model: str = "nvidia/nv-embedqa-e5-v5"

    # ── CG-pilot ────────────────────────────────────────────────────────
    # Uses the OpenAI SDK against the OpenAI-compatible NVIDIA NIM endpoint.
    cgpilot_max_tool_rounds: int = 6

    # ── Supabase ────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_key: str = ""

    # ── ChromaDB ───────────────────────────────────────────────────────
    chromadb_persist_dir: str = "./chroma_data"

    # ── Context-YAML (NEW) ──────────────────────────────────────────────
    context_yaml_enabled: bool = True
    context_yaml_filename: str = ".context.yaml"
    context_max_recent_changes: int = 20
    context_auto_commit: bool = True
    context_llm_temperature: float = 0.3
    context_llm_max_tokens: int = 2048
    retrieval_max_contexts: int = 5
    retrieval_max_snippets: int = 10

    # ── Feature Flags ──────────────────────────────────────────────────
    use_context_yaml: bool = False
    use_vector_search: bool = True

    # ── Logging ─────────────────────────────────────────────────────────
    log_level: str = "INFO"


def get_settings() -> Settings:
    """Create and return a Settings instance (cached via lru_cache if needed)."""
    return Settings()
