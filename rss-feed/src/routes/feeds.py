from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.database import get_db
from src.data.models import Feed, Website
from src.data.schemas import ParseResponse
from src.services.parser_service import FeedParserService

router = APIRouter(tags=["feeds"])


def get_parser() -> FeedParserService:
    from src.main import get_parser_service
    return get_parser_service()


@router.post(
    "/api/feeds/{feed_id}/parse",
    summary="Parse single feed",
    response_model=ParseResponse,
)
async def parse_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    parser: FeedParserService = Depends(get_parser),
):
    feed = await db.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found")
    new_articles = await parser.parse_feed(feed, db)
    result = await db.execute(select(Feed).where(Feed.id == feed_id))
    total = result.scalar_one_or_none()
    return ParseResponse(feed_id=feed_id, articles_found=len(new_articles), new_articles=len(new_articles))


@router.post(
    "/api/websites/{website_id}/parse",
    summary="Parse all feeds for website",
    response_model=ParseResponse,
)
async def parse_website_feeds(
    website_id: int,
    db: AsyncSession = Depends(get_db),
    parser: FeedParserService = Depends(get_parser),
):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    result = await db.execute(select(Feed).where(Feed.website_id == website_id))
    feeds = result.scalars().all()

    total_new = 0
    for feed in feeds:
        new_articles = await parser.parse_feed(feed, db)
        total_new += len(new_articles)

    return ParseResponse(feed_id=None, articles_found=total_new, new_articles=total_new)
