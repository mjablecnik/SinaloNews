from sqlalchemy import text, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Response

from src.data.database import get_db
from src.data.models import Article, Feed, Website
from src.data.schemas import StatusResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Health check",
    responses={200: {"description": "Service healthy"}, 503: {"description": "Service unavailable"}},
)
async def health_check(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        response.status_code = 503
        return {"status": "unavailable"}


@router.get("/status", summary="Pipeline statistics", response_model=StatusResponse)
async def get_status(db: AsyncSession = Depends(get_db)):
    total_websites = (await db.execute(select(func.count(Website.id)))).scalar_one()
    total_feeds = (await db.execute(select(func.count(Feed.id)))).scalar_one()
    total_articles = (await db.execute(select(func.count(Article.id)))).scalar_one()

    status_rows = (
        await db.execute(select(Article.status, func.count(Article.id)).group_by(Article.status))
    ).all()
    articles_by_status = {row[0]: row[1] for row in status_rows}

    return StatusResponse(
        total_websites=total_websites,
        total_feeds=total_feeds,
        total_articles=total_articles,
        articles_by_status=articles_by_status,
    )
