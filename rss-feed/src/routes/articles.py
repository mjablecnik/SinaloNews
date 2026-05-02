import math

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.database import get_db
from src.data.models import Article, Feed
from src.data.schemas import ArticleDetailResponse, ExtractBatchResponse, PaginatedResponse, ArticleResponse
from src.services.extractor_service import ArticleExtractorService

router = APIRouter(tags=["articles"])


def get_extractor() -> ArticleExtractorService:
    from src.main import get_extractor_service
    return get_extractor_service()


@router.get(
    "/api/articles/{article_id}",
    summary="Get article with all fields",
    response_model=ArticleDetailResponse,
)
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleDetailResponse.model_validate(article)


@router.delete(
    "/api/articles/{article_id}",
    summary="Delete article",
    status_code=204,
    response_class=Response,
)
async def delete_article(article_id: int, db: AsyncSession = Depends(get_db)):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(article)
    await db.commit()


@router.post(
    "/api/articles/{article_id}/extract",
    summary="Extract single article",
    response_model=ArticleDetailResponse,
)
async def extract_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
    extractor: ArticleExtractorService = Depends(get_extractor),
):
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    article = await extractor.extract_article(article, db)
    return ArticleDetailResponse.model_validate(article)


@router.get(
    "/api/feeds/{feed_id}/articles",
    summary="List articles for feed",
    response_model=PaginatedResponse[ArticleResponse],
)
async def list_feed_articles(
    feed_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    feed = await db.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found")

    q = select(Article).where(Article.feed_id == feed_id)
    if status:
        q = q.where(Article.status == status)

    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    items = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()

    return PaginatedResponse(
        items=[ArticleResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 0,
    )


@router.post(
    "/api/feeds/{feed_id}/extract",
    summary="Extract all unprocessed articles for feed",
    response_model=ExtractBatchResponse,
)
async def extract_feed_articles(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    extractor: ArticleExtractorService = Depends(get_extractor),
):
    feed = await db.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail="Feed not found")
    result = await extractor.extract_feed_articles(feed, db)
    return ExtractBatchResponse(feed_id=feed_id, **result)
