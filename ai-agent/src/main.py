import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from qdrant_client import AsyncQdrantClient
from sqlalchemy import func, select, text

from src.agent import NewsAgent, configure_langsmith
from src.config import settings
from src.database import AsyncSessionFactory
from src.embeddings import EmbeddingClient
from src.indexer import ArticleIndexer
from src.models import IndexedArticle
from src.rag import RAGPipeline
from src.schemas import (
    ErrorResponse,
    HealthResponse,
    IndexRequest,
    IndexingResult,
    QueryRequest,
    QueryResponse,
    StatsResponse,
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_langsmith(settings)

    embedding_client = EmbeddingClient(
        api_url=settings.EMBEDDING_API_URL,
        api_key=settings.effective_embedding_api_key(),
        model=settings.EMBEDDING_MODEL,
    )

    qdrant_client = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
    )

    rag_pipeline = RAGPipeline(
        embedding_client=embedding_client,
        qdrant_client=qdrant_client,
        settings=settings,
    )

    indexer = ArticleIndexer(
        db_session_factory=AsyncSessionFactory,
        embedding_client=embedding_client,
        qdrant_client=qdrant_client,
        settings=settings,
    )

    agent = NewsAgent(
        rag_pipeline=rag_pipeline,
        settings=settings,
    )

    app.state.qdrant_client = qdrant_client
    app.state.indexer = indexer
    app.state.agent = agent

    log.info("ai_agent_startup", port=settings.APP_PORT, model=settings.LLM_MODEL)
    yield

    await qdrant_client.close()
    log.info("ai_agent_shutdown")


app = FastAPI(title="AI News Agent", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=str(request.url.path), error=str(exc))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=type(exc).__name__,
            message=str(exc),
            timestamp=datetime.now(timezone.utc),
        ).model_dump(mode="json"),
    )


@app.post("/api/query", response_model=QueryResponse)
async def query_endpoint(body: QueryRequest, request: Request) -> QueryResponse:
    agent: NewsAgent = request.app.state.agent
    start = time.monotonic()

    try:
        result = await agent.query(body.query)
    except Exception as exc:
        err = str(exc)
        if "429" in err or "rate_limit" in err.lower() or "service_unavailable" in err.lower():
            return JSONResponse(
                status_code=503,
                content=ErrorResponse(
                    error="LLMUnavailable",
                    message="LLM service is temporarily unavailable. Please try again later.",
                    timestamp=datetime.now(timezone.utc),
                ).model_dump(mode="json"),
            )
        raise

    processing_time_ms = (time.monotonic() - start) * 1000
    log.info(
        "query_handled",
        query=body.query[:80],
        sources=len(result.sources),
        processing_time_ms=round(processing_time_ms, 2),
    )
    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        query=body.query,
        processing_time_ms=processing_time_ms,
    )


@app.post("/api/index", response_model=IndexingResult)
async def index_endpoint(body: IndexRequest, request: Request) -> IndexingResult:
    indexer: ArticleIndexer = request.app.state.indexer
    result = await indexer.index_articles(full_sync=body.full_sync)
    log.info(
        "indexing_complete",
        articles_processed=result.articles_processed,
        chunks_created=result.chunks_created,
        errors=len(result.errors),
    )
    return result


@app.get("/api/stats", response_model=StatsResponse)
async def stats_endpoint() -> StatsResponse:
    async with AsyncSessionFactory() as session:
        row = (
            await session.execute(
                select(
                    func.count(IndexedArticle.article_id),
                    func.sum(IndexedArticle.chunk_count),
                    func.max(IndexedArticle.indexed_at),
                )
            )
        ).one()

    return StatsResponse(
        total_articles_indexed=row[0] or 0,
        total_chunks=int(row[1] or 0),
        last_indexed_at=row[2],
    )


@app.get("/health", response_model=HealthResponse)
async def health_endpoint(request: Request) -> JSONResponse:
    qdrant_client: AsyncQdrantClient = request.app.state.qdrant_client

    db_status = "ok"
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        log.error("health_db_failed", error=str(exc))
        db_status = "unavailable"

    qdrant_status = "ok"
    try:
        await qdrant_client.get_collections()
    except Exception as exc:
        log.error("health_qdrant_failed", error=str(exc))
        qdrant_status = "unavailable"

    overall = "ok" if db_status == "ok" and qdrant_status == "ok" else "degraded"
    body = HealthResponse(status=overall, database=db_status, qdrant=qdrant_status)
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(status_code=status_code, content=body.model_dump())
