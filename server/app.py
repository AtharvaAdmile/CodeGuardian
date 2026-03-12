"""
CodeGuardian FastAPI Application Factory.

Uses the lifespan context manager pattern (NOT deprecated @app.on_event)
to initialize and tear down shared resources stored on app.state.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import get_settings

logger = logging.getLogger("codeguardian.server")


async def _warmup_llm(client) -> None:
    """Fire-and-forget warm-up for the NIM LLM client."""
    try:
        elapsed = await client.warm_up()
        logger.info("NIM warm-up completed in %.1fs", elapsed)
    except Exception as exc:
        logger.error("NIM warm-up failed (non-fatal): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown logic.

    On startup:
      - Records the boot timestamp for uptime tracking.
      - Initialises the NIM LLM client and fires a non-blocking warm-up.
      - Sets placeholder references for services not yet wired.

    On shutdown:
      - Closes the NIM LLM client.
      - Cleans up any other resources that need explicit teardown.
    """
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("🚀 CodeGuardian server starting up …")
    logger.info("   Host: %s  Port: %s", settings.server_host, settings.server_port)

    # ── Startup: store shared state ─────────────────────────────────
    app.state.boot_time = time.time()
    app.state.settings = settings

    # ── NIM LLM Client ──────────────────────────────────────────────
    from server.services.llm_client import NIMClient

    llm_client: NIMClient | None = None

    if settings.nvidia_nim_api_key:
        llm_client = NIMClient(
            base_url=settings.nvidia_nim_base_url,
            api_key=settings.nvidia_nim_api_key,
            model=settings.nvidia_llm_model,
        )
        # Non-blocking warm-up — don't delay server startup
        asyncio.create_task(_warmup_llm(llm_client))
        logger.info("✅ NIM LLM client initialised (model: %s)", settings.nvidia_llm_model)
    else:
        logger.warning("⚠️  NVIDIA_NIM_API_KEY not set — LLM client disabled")

    app.state.llm_client = llm_client

    # ── NIM Embedding Service ───────────────────────────────────────
    from server.services.embedding_service import NIMEmbeddingService

    embedding_service: NIMEmbeddingService | None = None

    if settings.nvidia_nim_api_key:
        embedding_service = NIMEmbeddingService(
            base_url=settings.nvidia_nim_base_url,
            api_key=settings.nvidia_nim_api_key,
            model=settings.nvidia_embed_model,
        )
        logger.info(
            "✅ NIM Embedding service initialised (model: %s)",
            settings.nvidia_embed_model,
        )
    else:
        logger.warning(
            "⚠️  NVIDIA_NIM_API_KEY not set — Embedding service disabled"
        )

    app.state.embedding_service = embedding_service

    # ── Vector Service (ChromaDB + optional Supabase) ───────────────
    from server.services.vector_service import VectorService

    supabase_client = None
    if settings.supabase_url and settings.supabase_key:
        try:
            from supabase import create_client

            supabase_client = create_client(
                settings.supabase_url, settings.supabase_key
            )
            logger.info("✅ Supabase client connected")
        except Exception as exc:
            logger.warning(
                "⚠️  Supabase init failed (non-fatal): %s", exc
            )

    vector_service = VectorService(
        chromadb_dir=settings.chromadb_persist_dir,
        supabase_client=supabase_client,
    )
    app.state.vector_service = vector_service
    app.state.supabase_client = supabase_client

    # ── Decision Service ────────────────────────────────────────────
    from server.services.decision_service import DecisionService

    decision_service = DecisionService(supabase_client=supabase_client)
    app.state.decision_service = decision_service

    # ── Git Service ─────────────────────────────────────────────────────
    # Initialised per-project when an indexing job runs; None at startup.
    app.state.git_service = None
    logger.info("ℹ️  GitService placeholder set (initialised per-project)")

    # ── Decision Extractor ──────────────────────────────────────────────
    from server.services.decision_extractor import DecisionExtractor

    if llm_client is not None:
        decision_extractor = DecisionExtractor(llm_client)
        logger.info("✅ DecisionExtractor initialised")
    else:
        decision_extractor = None
        logger.warning("⚠️  DecisionExtractor disabled (no LLM client)")

    app.state.decision_extractor = decision_extractor

    # ── Indexing Job Tracker ────────────────────────────────────────────
    app.state.index_jobs = {}

    logger.info("✅ Startup complete")

    yield  # ── Application runs here ────────────────────────────────

    # ── Shutdown ────────────────────────────────────────────────────
    logger.info("🛑 CodeGuardian server shutting down …")

    # Close LLM client
    if app.state.llm_client is not None:
        await app.state.llm_client.close()
        logger.info("   NIM LLM client closed")

    # Close Embedding service
    if getattr(app.state, "embedding_service", None) is not None:
        await app.state.embedding_service.close()
        logger.info("   NIM Embedding service closed")

    # Close Vector service
    if getattr(app.state, "vector_service", None) is not None:
        await app.state.vector_service.close()
        logger.info("   Vector service closed")

    logger.info("👋 Shutdown complete")


def create_app() -> FastAPI:
    """
    Application factory.

    Returns a fully configured FastAPI instance with CORS middleware
    and all route modules included.
    """
    app = FastAPI(
        title="CodeGuardian API",
        description=(
            "AI-powered institutional memory for codebases. "
            "Central hub for Electron desktop app, CLI, MCP server, and CI pipelines."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS Middleware ─────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://127.0.0.1:5173",
        ],
        allow_origin_regex=r"http://localhost:\d+",  # Any localhost port
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Register Routers ────────────────────────────────────────────
    from server.routes.health import router as health_router
    from server.routes.query import router as query_router
    from server.routes.analysis import router as analysis_router
    from server.routes.indexing import router as indexing_router
    from server.routes.analysis_extended import router as analysis_ext_router

    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(analysis_router)
    app.include_router(indexing_router)
    app.include_router(analysis_ext_router)

    return app
