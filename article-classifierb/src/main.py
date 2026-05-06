import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.constants import TAG_TAXONOMY
from src.database import Base, engine, AsyncSessionFactory
from src.models import Tag
from src.routes import router

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


def _configure_langsmith() -> None:
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
        os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGSMITH_TRACING
        log.info("langsmith_configured", project=settings.LANGSMITH_PROJECT)
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"


async def _seed_tag_taxonomy() -> None:
    async with AsyncSessionFactory() as session:
        for category, subcategories in TAG_TAXONOMY.items():
            existing = (
                await session.execute(
                    select(Tag).where(Tag.name == category, Tag.parent_id.is_(None))
                )
            ).scalar_one_or_none()

            if existing is None:
                parent = Tag(name=category, parent_id=None)
                session.add(parent)
                try:
                    await session.flush()
                except IntegrityError:
                    await session.rollback()
                    existing = (
                        await session.execute(
                            select(Tag).where(Tag.name == category, Tag.parent_id.is_(None))
                        )
                    ).scalar_one_or_none()
                    parent = existing
            else:
                parent = existing

            for subcategory in subcategories:
                sub_exists = (
                    await session.execute(
                        select(Tag).where(Tag.name == subcategory, Tag.parent_id == parent.id)
                    )
                ).scalar_one_or_none()
                if sub_exists is None:
                    session.add(Tag(name=subcategory, parent_id=parent.id))

        try:
            await session.commit()
            log.info("tag_taxonomy_seeded")
        except IntegrityError:
            await session.rollback()
            log.info("tag_taxonomy_already_seeded")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_langsmith()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _seed_tag_taxonomy()

    log.info("article_classifier_startup", port=settings.APP_PORT, model=settings.LLM_MODEL)
    yield

    await engine.dispose()
    log.info("article_classifier_shutdown")


app = FastAPI(title="Article Classifier", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=str(request.url.path), error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": type(exc).__name__,
            "message": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


app.include_router(router)
