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
    warmup_task: asyncio.Task | None = None

    if settings.nvidia_nim_api_key:
        llm_client = NIMClient(
            base_url=settings.nvidia_nim_base_url,
            api_key=settings.nvidia_nim_api_key,
            model=settings.nvidia_llm_model,
        )
        # Non-blocking warm-up — don't delay server startup
        # Store task reference to ensure proper cleanup on shutdown
        warmup_task = asyncio.create_task(_warmup_llm(llm_client))
        logger.info("✅ NIM LLM client initialised (model: %s)", settings.nvidia_llm_model)
    else:
        logger.warning("⚠️  NVIDIA_NIM_API_KEY not set — LLM client disabled")

    app.state.warmup_task = warmup_task

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

    # ── Vector Service (ChromaDB only) ──────────────────────────────
    from server.services.vector_service import VectorService

    vector_service = VectorService(
        chromadb_dir=settings.chromadb_persist_dir,
    )
    app.state.vector_service = vector_service

    # ── Decision Service ────────────────────────────────────────────
    from server.services.decision_service import DecisionService

    decision_service = DecisionService(supabase_client=None)
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

    # ── Knowledge Graph ─────────────────────────────────────────────────
    from server.services.knowledge_graph import KnowledgeGraph

    knowledge_graph = KnowledgeGraph()

    # Try to restore a previously-built graph from disk
    kg_persist_path = ".codeguardian/knowledge_graph.json"
    loaded = knowledge_graph.load_from_json(kg_persist_path)
    if loaded:
        logger.info("✅ Knowledge graph loaded from disk (%s)", kg_persist_path)
    else:
        logger.info("ℹ️  Knowledge graph empty — will be populated on first index")

    app.state.knowledge_graph = knowledge_graph

    # ── Context Service (NEW) ─────────────────────────────────────────────
    from server.services.context_service import ContextService

    context_service: ContextService | None = None
    if settings.context_yaml_enabled and llm_client is not None:
        context_service = ContextService(
            llm_client=llm_client,
            git_service=None,
            context_filename=settings.context_yaml_filename,
        )
        logger.info(
            "✅ ContextService initialised (filename: %s)",
            settings.context_yaml_filename,
        )
    else:
        logger.info("ℹ️  ContextService disabled (context_yaml_enabled=False)")

    app.state.context_service = context_service

    # ── Retrieval Service (NEW) ──────────────────────────────────────────
    from server.services.retrieval_service import RetrievalService

    retrieval_service: RetrievalService | None = None
    if context_service is not None:
        retrieval_service = RetrievalService(
            context_service=context_service,
            max_contexts=settings.retrieval_max_contexts,
            max_snippets=settings.retrieval_max_snippets,
        )
        logger.info("✅ RetrievalService initialised")

    app.state.retrieval_service = retrieval_service

    # ── Chat History Service (CG-pilot session persistence) ─────────────
    from server.services.chat_history_service import ChatHistoryService

    chat_history_service = ChatHistoryService()
    app.state.chat_history_service = chat_history_service
    logger.info("✅ ChatHistoryService initialised")

    # ── CG-pilot (OpenAI SDK over NVIDIA NIM-compatible endpoint) ───────
    from server.services.cg_pilot_service import CGPilotService

    cg_pilot_service: CGPilotService | None = None
    if settings.nvidia_nim_api_key and embedding_service is not None:
        cg_pilot_service = CGPilotService(
            api_key=settings.nvidia_nim_api_key,
            base_url=settings.nvidia_nim_base_url,
            model=settings.nvidia_llm_model,
            embedding_service=embedding_service,
            vector_service=vector_service,
            max_tool_rounds=settings.cgpilot_max_tool_rounds,
        )
        logger.info(
            "✅ CG-pilot initialised via OpenAI SDK (NIM model: %s)",
            settings.nvidia_llm_model,
        )
    elif not settings.nvidia_nim_api_key:
        logger.info("ℹ️  CG-pilot disabled (NVIDIA_NIM_API_KEY not set)")
    else:
        logger.info("ℹ️  CG-pilot disabled (embedding service unavailable)")

    app.state.cg_pilot_service = cg_pilot_service

    # ── Indexing Job Tracker ────────────────────────────────────────────
    app.state.index_jobs = {}

    logger.info("✅ Startup complete")

    yield  # ── Application runs here ────────────────────────────────

    # ── Shutdown ────────────────────────────────────────────────────
    logger.info("🛑 CodeGuardian server shutting down …")

    # Cancel warmup task if still running
    warmup_task = getattr(app.state, "warmup_task", None)
    if warmup_task is not None and not warmup_task.done():
        warmup_task.cancel()
        try:
            await asyncio.wait_for(warmup_task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        logger.info("   Warmup task cancelled")

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

    # Close CG-pilot service
    if getattr(app.state, "cg_pilot_service", None) is not None:
        await app.state.cg_pilot_service.close()
        logger.info("   CG-pilot service closed")

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
            "http://localhost:5174",
            "http://localhost:3000",
        ],
        allow_origin_regex=r"http://localhost:\d+",  # Any localhost port
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # ── Register Routers ────────────────────────────────────────────
    from server.routes.health import router as health_router
    from server.routes.query import router as query_router
    from server.routes.analysis import router as analysis_router
    from server.routes.indexing import router as indexing_router
    from server.routes.analysis_extended import router as analysis_ext_router
    from server.routes.impact import router as impact_router
    from server.routes.onboarding import router as onboarding_router
    from server.routes.review import router as review_router
    from server.routes.context import router as context_router
    from server.routes.cg_pilot import router as cg_pilot_router
    from server.routes.dashboard import router as dashboard_router
    from server.routes.compliance import router as compliance_router

    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(analysis_router)
    app.include_router(indexing_router)
    app.include_router(analysis_ext_router)
    app.include_router(impact_router)
    app.include_router(onboarding_router)
    app.include_router(review_router)
    app.include_router(context_router)
    app.include_router(cg_pilot_router)
    app.include_router(dashboard_router)
    app.include_router(compliance_router)

    return app


app = create_app()
