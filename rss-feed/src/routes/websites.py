import math
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.database import get_db
from src.data.models import Article, Feed, Website
from src.data.schemas import (
    ArticleResponse,
    DiscoveryResponse,
    FeedResponse,
    PaginatedResponse,
    WebsiteCreate,
    WebsiteResponse,
)
from src.services.discovery_service import FeedDiscoveryService

router = APIRouter(prefix="/api/websites", tags=["websites"])


def get_discovery() -> FeedDiscoveryService:
    from src.main import get_discovery_service
    return get_discovery_service()


@router.post(
    "",
    summary="Register website",
    response_model=WebsiteResponse,
    status_code=201,
    responses={200: {"model": WebsiteResponse, "description": "Website already exists"}},
)
async def register_website(
    body: WebsiteCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(select(Website).where(Website.url == body.url))
    ).scalar_one_or_none()
    if existing:
        response.status_code = 200
        return WebsiteResponse.model_validate(existing)

    domain = urlparse(body.url).netloc
    website = Website(name=body.name, url=body.url, domain=domain)
    db.add(website)
    try:
        await db.commit()
        await db.refresh(website)
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(select(Website).where(Website.url == body.url))
        ).scalar_one_or_none()
        if existing:
            response.status_code = 200
            return WebsiteResponse.model_validate(existing)
        raise

    return WebsiteResponse.model_validate(website)


@router.get("", summary="List websites", response_model=PaginatedResponse[WebsiteResponse])
async def list_websites(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Website.id)))).scalar_one()
    items = (
        await db.execute(select(Website).offset((page - 1) * size).limit(size))
    ).scalars().all()
    return PaginatedResponse(
        items=[WebsiteResponse.model_validate(w) for w in items],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size) if total else 0,
    )


@router.get("/{website_id}", summary="Get website", response_model=WebsiteResponse)
async def get_website(website_id: int, db: AsyncSession = Depends(get_db)):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    return WebsiteResponse.model_validate(website)


@router.delete("/{website_id}", summary="Delete website", status_code=204, response_class=Response)
async def delete_website(website_id: int, db: AsyncSession = Depends(get_db)):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    await db.delete(website)
    await db.commit()


@router.post(
    "/{website_id}/discover",
    summary="Trigger feed discovery",
    response_model=DiscoveryResponse,
)
async def discover_feeds(
    website_id: int,
    db: AsyncSession = Depends(get_db),
    discovery: FeedDiscoveryService = Depends(get_discovery),
):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    new_feeds = await discovery.discover_feeds(website, db)
    return DiscoveryResponse(
        website_id=website_id,
        feeds_found=len(new_feeds),
        feeds=[FeedResponse.model_validate(f) for f in new_feeds],
    )


@router.get("/{website_id}/feeds", summary="List feeds for website", response_model=list[FeedResponse])
async def list_website_feeds(website_id: int, db: AsyncSession = Depends(get_db)):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    result = await db.execute(select(Feed).where(Feed.website_id == website_id))
    feeds = result.scalars().all()
    return [FeedResponse.model_validate(f) for f in feeds]


@router.get(
    "/{website_id}/articles",
    summary="List articles across all feeds for website",
    response_model=PaginatedResponse[ArticleResponse],
)
async def list_website_articles(
    website_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    website = await db.get(Website, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    q = (
        select(Article)
        .join(Feed, Article.feed_id == Feed.id)
        .where(Feed.website_id == website_id)
    )
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
