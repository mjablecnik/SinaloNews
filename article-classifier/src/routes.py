import math
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.classifier_service import ClassifierService, is_processing, trigger_classification
from src.database import get_session
from src.models import Article, ArticleTag, ClassificationResult, Tag
from src.schemas import (
    ClassifiedArticleResponse,
    ClassifyStatusResponse,
    ClassifyTriggerResponse,
    HealthResponse,
    PaginatedResponse,
    TagResponse,
)

log = structlog.get_logger()
router = APIRouter()

_classifier_service: ClassifierService | None = None


def get_classifier_service() -> ClassifierService:
    global _classifier_service
    if _classifier_service is None:
        _classifier_service = ClassifierService()
    return _classifier_service


def _build_tag_responses(article_tags: list[ArticleTag]) -> list[TagResponse]:
    tags = []
    for at in article_tags:
        tag = at.tag
        if tag.parent_id is None:
            continue
        parent = tag.parent
        if parent:
            tags.append(TagResponse(category=parent.name, subcategory=tag.name))
    return tags


@router.get("/api/articles", response_model=PaginatedResponse)
async def get_articles(
    category: str | None = Query(None),
    subcategory: str | None = Query(None),
    content_type: str | None = Query(None),
    min_score: int | None = Query(None, ge=0, le=10),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    sort_by: str = Query("classified_at", pattern="^(importance_score|published_at|classified_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse:
    stmt = (
        select(ClassificationResult)
        .join(Article, ClassificationResult.article_id == Article.id)
        .options(
            selectinload(ClassificationResult.article),
            selectinload(ClassificationResult.article_tags).selectinload(ArticleTag.tag).selectinload(Tag.parent),
        )
    )

    filters = []

    if content_type is not None:
        filters.append(ClassificationResult.content_type == content_type)
    if min_score is not None:
        filters.append(ClassificationResult.importance_score >= min_score)
    if date_from is not None:
        filters.append(Article.published_at >= date_from)
    if date_to is not None:
        filters.append(Article.published_at <= date_to)

    if category is not None or subcategory is not None:
        tag_filter_stmt = select(ArticleTag.classification_result_id)
        if subcategory is not None:
            sub_tag = select(Tag.id).where(Tag.name.ilike(subcategory))
            tag_filter_stmt = tag_filter_stmt.where(ArticleTag.tag_id.in_(sub_tag))
        if category is not None:
            parent_tag = select(Tag.id).where(Tag.name.ilike(category), Tag.parent_id.is_(None))
            child_tags = select(Tag.id).where(Tag.parent_id.in_(parent_tag))
            if subcategory is not None:
                child_tags = child_tags.where(Tag.name.ilike(subcategory))
                tag_filter_stmt = (
                    select(ArticleTag.classification_result_id)
                    .where(ArticleTag.tag_id.in_(child_tags))
                )
            else:
                tag_filter_stmt = (
                    select(ArticleTag.classification_result_id)
                    .where(ArticleTag.tag_id.in_(child_tags))
                )
        filters.append(ClassificationResult.id.in_(tag_filter_stmt))

    if filters:
        stmt = stmt.where(and_(*filters))

    sort_col = {
        "importance_score": ClassificationResult.importance_score,
        "published_at": Article.published_at,
        "classified_at": ClassificationResult.classified_at,
    }[sort_by]

    stmt = stmt.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await session.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)

    rows = (await session.execute(stmt)).scalars().all()

    items: list[ClassifiedArticleResponse] = []
    for cr in rows:
        article = cr.article
        items.append(
            ClassifiedArticleResponse(
                id=article.id,
                title=article.title,
                url=article.url,
                author=article.author,
                published_at=article.published_at,
                tags=_build_tag_responses(cr.article_tags),
                content_type=cr.content_type,
                importance_score=cr.importance_score,
                summary=cr.summary,
                classified_at=cr.classified_at,
            )
        )

    pages = math.ceil(total / size) if total > 0 else 0

    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.post("/api/classify", response_model=ClassifyTriggerResponse, status_code=202)
async def classify(
    service: ClassifierService = Depends(get_classifier_service),
) -> ClassifyTriggerResponse:
    if is_processing():
        raise HTTPException(status_code=409, detail="Classification already in progress")
    try:
        queued = await trigger_classification(service)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ClassifyTriggerResponse(queued=queued, message=f"Classification triggered for {queued} articles")


@router.get("/api/classify/status", response_model=ClassifyStatusResponse)
async def classify_status(
    service: ClassifierService = Depends(get_classifier_service),
) -> ClassifyStatusResponse:
    status = "processing" if is_processing() else "idle"
    pending = await service.count_unprocessed()
    classified = await service.count_classified()
    return ClassifyStatusResponse(status=status, pending=pending, classified=classified)


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    try:
        await session.execute(select(func.now()))
        db_status = "ok"
    except Exception as exc:
        log.error("health_db_check_failed", error=str(exc)[:200])
        raise HTTPException(
            status_code=503,
            detail=HealthResponse(status="unavailable", database="unavailable").model_dump(),
        ) from exc
    return HealthResponse(status="ok", database=db_status)
