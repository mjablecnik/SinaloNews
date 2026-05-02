import uuid
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.config import settings
from src.data.database import engine
from src.data.schemas import ErrorResponse
from src.services.batch_service import BatchProcessor
from src.services.discovery_service import FeedDiscoveryService
from src.services.extractor_service import ArticleExtractorService
from src.services.parser_service import FeedParserService
from src.services.rate_limiter import RateLimiter

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

logger = structlog.get_logger()

_http_client: httpx.AsyncClient | None = None
_rate_limiter: RateLimiter | None = None
_discovery_service: FeedDiscoveryService | None = None
_parser_service: FeedParserService | None = None
_extractor_service: ArticleExtractorService | None = None
_batch_processor: BatchProcessor | None = None


def get_discovery_service() -> FeedDiscoveryService:
    assert _discovery_service is not None
    return _discovery_service


def get_parser_service() -> FeedParserService:
    assert _parser_service is not None
    return _parser_service


def get_extractor_service() -> ArticleExtractorService:
    assert _extractor_service is not None
    return _extractor_service


def get_processor() -> BatchProcessor:
    assert _batch_processor is not None
    return _batch_processor


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client, _rate_limiter, _discovery_service, _parser_service
    global _extractor_service, _batch_processor

    _http_client = httpx.AsyncClient(
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": settings.USER_AGENT},
        follow_redirects=True,
    )
    _rate_limiter = RateLimiter(delay_seconds=settings.REQUEST_DELAY_SECONDS)
    _discovery_service = FeedDiscoveryService(_http_client, _rate_limiter)
    _parser_service = FeedParserService(_rate_limiter)
    _extractor_service = ArticleExtractorService(_http_client, _rate_limiter)
    _batch_processor = BatchProcessor(_parser_service, _extractor_service)

    logger.info("startup_complete")
    yield

    await _http_client.aclose()
    await engine.dispose()
    logger.info("shutdown_complete")


app = FastAPI(
    title="RSS Feed Pipeline",
    description="Discover RSS/Atom feeds, parse entries, and extract article text.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    logger.exception("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="internal_server_error",
            message=str(exc),
            request_id=request_id,
        ).model_dump(),
    )


from src.routes import articles, batch, feeds, health, websites  # noqa: E402

app.include_router(health.router)
app.include_router(websites.router)
app.include_router(feeds.router)
app.include_router(articles.router)
app.include_router(batch.router)
