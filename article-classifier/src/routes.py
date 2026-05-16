import asyncio
import hashlib
import json
import math
import time
from datetime import date, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from langchain_openai import ChatOpenAI
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.classifier_service import ClassifierService, is_processing, trigger_classification
from src.config import settings
from src.database import get_session, AsyncSessionFactory
from src.grouping_schemas import (
    FeedItem,
    FeedResponse,
    GroupDetailResponse,
    GroupListResponse,
    GroupMemberResponse,
    GroupSummaryResponse,
    GroupingTriggerResponse,
    RegenerationResponse,
)
from src.grouping_service import GroupingService
from src.models import Article, ArticleGroup, ArticleGroupMember, ArticleTag, ClassificationResult, Tag
from src.schemas import (
    ArticleDetailResponse,
    CategoriesResponse,
    CategoryCountResponse,
    ClassifiedArticleResponse,
    ClassifyStatusResponse,
    ClassifyTriggerResponse,
    CleanupResponse,
    HealthResponse,
    PaginatedResponse,
    TagResponse,
)

log = structlog.get_logger()
router = APIRouter()

_classifier_service: ClassifierService | None = None
_formatting_llm: ChatOpenAI | None = None
_grouping_service: GroupingService | None = None

# --- In-memory cache (1 hour TTL) ---
_CACHE_TTL_SECONDS = 3600  # 1 hour
_cache: dict[str, tuple[float, object]] = {}


def _cache_key(prefix: str, params: dict) -> str:
    """Generate a cache key from prefix and query params."""
    raw = prefix + json.dumps(params, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> object | None:
    """Get value from cache if not expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    timestamp, value = entry
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        del _cache[key]
        return None
    return value


def _cache_set(key: str, value: object) -> None:
    """Store value in cache with current timestamp."""
    _cache[key] = (time.time(), value)


def _get_formatting_llm() -> ChatOpenAI:
    global _formatting_llm
    if _formatting_llm is None:
        _formatting_llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/sinalo/article-classifier",
                "X-Title": "Article Classifier",
            },
        )
    return _formatting_llm


_FORMAT_PROMPT = """You are a text formatter and translator for a news reader application.
Take the following raw article text and reformat it into clean, readable Markdown.

Rules:
- Split the text into logical paragraphs for easy reading
- Use **bold** for important names, organizations, numbers, and key terms
- Use bullet points where appropriate (e.g., lists of items)
- Remove any image URLs, base64 data, encoded strings, or garbage characters
- Remove any emoji sequences that don't add meaning
- If the text is NOT in Czech, translate it to Czech while preserving all facts and meaning
- If the text is already in Czech, keep it in Czech (do not translate)
- Do NOT add any information that is not in the original text
- Do NOT add a title or heading — just the formatted body text
- Output ONLY the formatted Markdown text, nothing else"""


async def _format_article_text(raw_text: str) -> str:
    """Format raw extracted article text into readable Markdown via LLM."""
    llm = _get_formatting_llm()
    # Truncate input to avoid token limits (keep first 8000 chars)
    text_input = raw_text[:8000] if len(raw_text) > 8000 else raw_text
    messages = [
        {"role": "system", "content": _FORMAT_PROMPT},
        {"role": "user", "content": text_input},
    ]
    response = await llm.ainvoke(messages)
    return str(response.content).strip()


async def _background_format_article(article_id: int, extracted_text: str) -> None:
    """Background task: format article text and save to DB."""
    try:
        formatted = await _format_article_text(extracted_text)
        async with AsyncSessionFactory() as session:
            article = await session.get(Article, article_id)
            if article and not article.formatted_text:
                article.formatted_text = formatted
                await session.commit()
                log.info("article_formatted_background", article_id=article_id)
    except Exception as exc:
        log.error("background_format_failed", article_id=article_id, error=str(exc)[:200])


def get_classifier_service() -> ClassifierService:
    global _classifier_service
    if _classifier_service is None:
        _classifier_service = ClassifierService()
    return _classifier_service


def get_grouping_service() -> GroupingService:
    global _grouping_service
    if _grouping_service is None:
        _grouping_service = GroupingService()
    return _grouping_service


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


def _build_group_tags(members: list[ArticleGroupMember]) -> list[TagResponse]:
    seen: set[tuple[str, str]] = set()
    tags: list[TagResponse] = []
    for member in members:
        article = member.article
        if not article or not article.classification_result:
            continue
        for at in article.classification_result.article_tags:
            tag = at.tag
            if tag.parent_id is None or not tag.parent:
                continue
            pair = (tag.parent.name, tag.name)
            if pair not in seen:
                seen.add(pair)
                tags.append(TagResponse(category=tag.parent.name, subcategory=tag.name))
    return tags


def _compute_group_importance(members: list[ArticleGroupMember]) -> int:
    scores = [
        m.article.classification_result.importance_score
        for m in members
        if m.article and m.article.classification_result
    ]
    return max(scores) if scores else 0


def _group_has_subcategory(members: list[ArticleGroupMember], subcategory: str) -> bool:
    sub_lower = subcategory.lower()
    for member in members:
        article = member.article
        if not article or not article.classification_result:
            continue
        for at in article.classification_result.article_tags:
            if at.tag and at.tag.name.lower() == sub_lower and at.tag.parent_id is not None:
                return True
    return False


def _get_article_category(article_tags: list[ArticleTag]) -> str:
    if not article_tags:
        return ""
    first_at = min(article_tags, key=lambda at: at.id)
    tag = first_at.tag
    if tag and tag.parent:
        return tag.parent.name
    if tag:
        return tag.name
    return ""


def _group_to_summary(group: ArticleGroup) -> GroupSummaryResponse:
    members = group.members
    return GroupSummaryResponse(
        id=group.id,
        title=group.title,
        summary=group.summary,
        category=group.category,
        grouped_date=group.grouped_date,
        member_count=len(members),
        importance_score=_compute_group_importance(members),
        tags=_build_group_tags(members),
        created_at=group.created_at,
    )


def _group_to_feed_item(group: ArticleGroup) -> FeedItem:
    members = group.members
    return FeedItem(
        type="group",
        id=group.id,
        title=group.title,
        summary=group.summary,
        category=group.category,
        importance_score=_compute_group_importance(members),
        tags=_build_group_tags(members),
        grouped_date=group.grouped_date,
        member_count=len(members),
    )


def _cr_to_feed_item(cr: ClassificationResult) -> FeedItem:
    article = cr.article
    return FeedItem(
        type="article",
        id=article.id,
        title=article.title,
        summary=cr.summary,
        category=_get_article_category(cr.article_tags),
        importance_score=cr.importance_score,
        tags=_build_tag_responses(cr.article_tags),
        url=article.url,
        author=article.author,
        published_at=article.published_at,
        content_type=cr.content_type,
        classified_at=cr.classified_at,
    )


def _feed_date_key(item: FeedItem) -> tuple[date, int]:
    """Sort key: (date descending, importance descending within same day).

    Returns (date, importance_score) — caller uses reverse=True.
    """
    if item.type == "article":
        d = item.published_at.date() if item.published_at else date.min
    elif item.grouped_date:
        d = item.grouped_date
    else:
        d = date.min
    return (d, item.importance_score)


@router.get("/api/articles", response_model=PaginatedResponse)
async def get_articles(
    category: str | None = Query(None),
    subcategory: str | None = Query(None),
    content_type: str | None = Query(None),
    min_score: int | None = Query(None, ge=0, le=10),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    sort_by: str = Query("classified_at", pattern="^(importance_score|published_at|classified_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse:
    # Check cache
    cache_params = {
        "category": category, "subcategory": subcategory, "content_type": content_type,
        "min_score": min_score, "date_from": date_from, "date_to": date_to,
        "sort_by": sort_by, "sort_order": sort_order, "page": page, "size": size,
    }
    key = _cache_key("articles", cache_params)
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

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
        filters.append(func.date(Article.published_at) >= date_from)
    if date_to is not None:
        filters.append(func.date(Article.published_at) <= date_to)

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

    result = PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)
    _cache_set(key, result)
    return result


@router.get("/api/categories", response_model=CategoriesResponse)
async def get_categories(
    min_score: int | None = Query(None, ge=0, le=10),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> CategoriesResponse:
    """Return category names with feed item counts and IDs (standalone articles + groups)."""
    cache_params = {"min_score": min_score, "date_from": date_from, "date_to": date_to}
    key = _cache_key("categories_v2", cache_params)
    cached = _cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    from sqlalchemy.orm import aliased

    ParentTag = aliased(Tag)

    # Standalone articles (not in any group) per category
    article_stmt = (
        select(
            ParentTag.name.label("category_name"),
            Article.id.label("article_id"),
        )
        .select_from(ArticleTag)
        .join(Tag, Tag.id == ArticleTag.tag_id)
        .join(ParentTag, ParentTag.id == Tag.parent_id)
        .join(ClassificationResult, ClassificationResult.id == ArticleTag.classification_result_id)
        .join(Article, Article.id == ClassificationResult.article_id)
        .outerjoin(ArticleGroupMember, ArticleGroupMember.article_id == Article.id)
        .where(ArticleGroupMember.id.is_(None))
    )

    filters = []
    if min_score is not None:
        filters.append(ClassificationResult.importance_score >= min_score)
    if date_from is not None:
        filters.append(func.date(Article.published_at) >= date_from)
    if date_to is not None:
        filters.append(func.date(Article.published_at) <= date_to)

    if filters:
        article_stmt = article_stmt.where(and_(*filters))

    article_rows = (await session.execute(article_stmt)).all()

    # Groups per category
    group_stmt = (
        select(ArticleGroup.id, ArticleGroup.category)
        .select_from(ArticleGroup)
    )

    group_filters = []
    if date_from is not None:
        group_filters.append(ArticleGroup.grouped_date >= date_from)
    if date_to is not None:
        group_filters.append(ArticleGroup.grouped_date <= date_to)

    if group_filters:
        group_stmt = group_stmt.where(and_(*group_filters))

    group_rows = (await session.execute(group_stmt)).all()

    # Filter groups by min_score if needed
    if min_score is not None:
        group_ids_to_check = [row.id for row in group_rows]
        if group_ids_to_check:
            members_stmt = (
                select(ArticleGroup)
                .where(ArticleGroup.id.in_(group_ids_to_check))
                .options(_GROUP_MEMBER_LOAD_OPTIONS)
            )
            groups_with_members = list((await session.execute(members_stmt)).scalars().all())
            valid_group_ids = {
                g.id for g in groups_with_members
                if _compute_group_importance(g.members) >= min_score
            }
            group_rows = [row for row in group_rows if row.id in valid_group_ids]

    # Build per-category data
    cat_data: dict[str, dict] = {}
    for row in article_rows:
        cat_name = row.category_name
        if cat_name not in cat_data:
            cat_data[cat_name] = {"article_ids": set(), "group_ids": set()}
        cat_data[cat_name]["article_ids"].add(row.article_id)

    for row in group_rows:
        cat_name = row.category
        if cat_name not in cat_data:
            cat_data[cat_name] = {"article_ids": set(), "group_ids": set()}
        cat_data[cat_name]["group_ids"].add(row.id)

    categories = []
    for cat_name, data in cat_data.items():
        article_ids = sorted(data["article_ids"])
        group_ids = sorted(data["group_ids"])
        count = len(article_ids) + len(group_ids)
        categories.append(CategoryCountResponse(
            category=cat_name,
            count=count,
            article_ids=article_ids,
            group_ids=group_ids,
        ))

    categories.sort(key=lambda c: c.count, reverse=True)
    total = sum(c.count for c in categories)

    result = CategoriesResponse(categories=categories, total=total)
    _cache_set(key, result)
    return result


@router.get("/api/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article_detail(
    article_id: int,
    session: AsyncSession = Depends(get_session),
) -> ArticleDetailResponse:
    stmt = (
        select(ClassificationResult)
        .join(Article, ClassificationResult.article_id == Article.id)
        .where(Article.id == article_id)
        .options(
            selectinload(ClassificationResult.article),
            selectinload(ClassificationResult.article_tags)
            .selectinload(ArticleTag.tag)
            .selectinload(Tag.parent),
        )
    )
    result = (await session.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found")

    article = result.article

    # Lazy format: if extracted_text exists but formatted_text doesn't, trigger background formatting
    formatted_text = article.formatted_text
    if article.extracted_text and not formatted_text:
        # Fire-and-forget: trigger formatting in background, return immediately with raw text
        asyncio.create_task(_background_format_article(article.id, article.extracted_text))

    return ArticleDetailResponse(
        id=article.id,
        title=article.title,
        url=article.url,
        author=article.author,
        published_at=article.published_at,
        tags=_build_tag_responses(result.article_tags),
        content_type=result.content_type,
        importance_score=result.importance_score,
        summary=result.summary,
        extracted_text=article.extracted_text,
        formatted_text=formatted_text,
        image_url=article.image_url,
        classified_at=result.classified_at,
    )


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


_GROUP_MEMBER_LOAD_OPTIONS = (
    selectinload(ArticleGroup.members)
    .selectinload(ArticleGroupMember.article)
    .selectinload(Article.classification_result)
    .selectinload(ClassificationResult.article_tags)
    .selectinload(ArticleTag.tag)
    .selectinload(Tag.parent)
)


@router.post("/api/groups/generate", response_model=GroupingTriggerResponse)
async def generate_groups(
    target_date: date | None = Query(None, alias="date"),
    service: GroupingService = Depends(get_grouping_service),
) -> GroupingTriggerResponse:
    return await service.run_grouping(target_date=target_date)


@router.post("/api/groups/regenerate", response_model=RegenerationResponse)
async def regenerate_groups(
    service: GroupingService = Depends(get_grouping_service),
) -> RegenerationResponse:
    return await service.run_regeneration()


@router.get("/api/groups", response_model=GroupListResponse)
async def get_groups(
    category: str | None = Query(None),
    date_filter: date | None = Query(None, alias="date"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    filters = []
    if category is not None:
        filters.append(ArticleGroup.category.ilike(category))
    if date_filter is not None:
        filters.append(ArticleGroup.grouped_date == date_filter)
    if date_from is not None:
        filters.append(ArticleGroup.grouped_date >= date_from)
    if date_to is not None:
        filters.append(ArticleGroup.grouped_date <= date_to)

    base_stmt = select(ArticleGroup)
    if filters:
        base_stmt = base_stmt.where(and_(*filters))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total: int = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        base_stmt
        .order_by(ArticleGroup.id.asc())
        .offset((page - 1) * size)
        .limit(size)
        .options(_GROUP_MEMBER_LOAD_OPTIONS)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [_group_to_summary(g) for g in rows]
    pages = math.ceil(total / size) if total > 0 else 0
    return GroupListResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.get("/api/groups/{group_id}", response_model=GroupDetailResponse)
async def get_group_detail(
    group_id: int,
    session: AsyncSession = Depends(get_session),
) -> GroupDetailResponse:
    stmt = (
        select(ArticleGroup)
        .where(ArticleGroup.id == group_id)
        .options(_GROUP_MEMBER_LOAD_OPTIONS)
    )
    group = (await session.execute(stmt)).scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")

    members = group.members
    member_responses = [
        GroupMemberResponse(
            id=m.article.id,
            title=m.article.title,
            url=m.article.url,
            author=m.article.author,
            published_at=m.article.published_at,
            summary=m.article.classification_result.summary if m.article.classification_result else None,
            importance_score=m.article.classification_result.importance_score if m.article.classification_result else 0,
        )
        for m in members
        if m.article
    ]

    return GroupDetailResponse(
        id=group.id,
        title=group.title,
        summary=group.summary,
        detail=group.detail,
        category=group.category,
        grouped_date=group.grouped_date,
        member_count=len(members),
        importance_score=_compute_group_importance(members),
        tags=_build_group_tags(members),
        created_at=group.created_at,
        members=member_responses,
    )


@router.get("/api/feed", response_model=FeedResponse)
async def get_feed(
    category: str | None = Query(None),
    subcategory: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    min_score: int | None = Query(None, ge=0, le=10),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> FeedResponse:
    # --- Standalone articles (not in any group) ---
    article_stmt = (
        select(ClassificationResult)
        .join(Article, ClassificationResult.article_id == Article.id)
        .outerjoin(ArticleGroupMember, ArticleGroupMember.article_id == Article.id)
        .where(ArticleGroupMember.id.is_(None))
        .options(
            selectinload(ClassificationResult.article),
            selectinload(ClassificationResult.article_tags)
            .selectinload(ArticleTag.tag)
            .selectinload(Tag.parent),
        )
    )

    article_filters = []
    if min_score is not None:
        article_filters.append(ClassificationResult.importance_score >= min_score)
    if date_from is not None:
        article_filters.append(func.date(Article.published_at) >= date_from)
    if date_to is not None:
        article_filters.append(func.date(Article.published_at) <= date_to)

    if category is not None or subcategory is not None:
        tag_filter_stmt = select(ArticleTag.classification_result_id)
        if category is not None:
            parent_tag = select(Tag.id).where(Tag.name.ilike(category), Tag.parent_id.is_(None))
            child_tags = select(Tag.id).where(Tag.parent_id.in_(parent_tag))
            if subcategory is not None:
                child_tags = child_tags.where(Tag.name.ilike(subcategory))
            tag_filter_stmt = tag_filter_stmt.where(ArticleTag.tag_id.in_(child_tags))
        else:
            sub_tag = select(Tag.id).where(Tag.name.ilike(subcategory))
            tag_filter_stmt = tag_filter_stmt.where(ArticleTag.tag_id.in_(sub_tag))
        article_filters.append(ClassificationResult.id.in_(tag_filter_stmt))

    if article_filters:
        article_stmt = article_stmt.where(and_(*article_filters))

    article_rows = (await session.execute(article_stmt)).scalars().all()

    # --- Groups ---
    group_stmt = select(ArticleGroup).options(_GROUP_MEMBER_LOAD_OPTIONS)

    group_filters = []
    if category is not None:
        group_filters.append(ArticleGroup.category.ilike(category))
    if date_from is not None:
        group_filters.append(ArticleGroup.grouped_date >= date_from)
    if date_to is not None:
        group_filters.append(ArticleGroup.grouped_date <= date_to)

    if group_filters:
        group_stmt = group_stmt.where(and_(*group_filters))

    group_rows = list((await session.execute(group_stmt)).scalars().all())

    if min_score is not None:
        group_rows = [g for g in group_rows if _compute_group_importance(g.members) >= min_score]
    if subcategory is not None:
        group_rows = [g for g in group_rows if _group_has_subcategory(g.members, subcategory)]

    # Merge and sort: newest day first, highest importance within same day
    all_items = [_cr_to_feed_item(cr) for cr in article_rows] + [_group_to_feed_item(g) for g in group_rows]
    all_items.sort(key=_feed_date_key, reverse=True)

    total = len(all_items)
    pages = math.ceil(total / size) if total > 0 else 0
    offset = (page - 1) * size
    return FeedResponse(items=all_items[offset:offset + size], total=total, page=page, size=size, pages=pages)


@router.delete("/api/articles/cleanup", response_model=CleanupResponse)
async def cleanup_old_articles(
    before: date = Query(..., description="Delete articles published before this date"),
    session: AsyncSession = Depends(get_session),
) -> CleanupResponse:
    """Delete articles (and their related data) published before the given date."""
    from datetime import timedelta
    from src.models import FullArticleIndexed

    # Safety check: refuse to delete articles from the last 30 days
    min_allowed_date = date.today() - timedelta(days=30)
    if before > min_allowed_date:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete articles newer than 30 days. Earliest allowed 'before' date is {min_allowed_date}.",
        )

    # Find articles to delete
    article_ids_stmt = (
        select(Article.id).where(func.date(Article.published_at) < before)
    )
    article_ids = list((await session.execute(article_ids_stmt)).scalars().all())

    if not article_ids:
        return CleanupResponse(deleted_articles=0, deleted_groups=0, before_date=str(before))

    # Delete full_article_indexed entries
    from sqlalchemy import delete as sa_delete

    await session.execute(
        sa_delete(FullArticleIndexed).where(FullArticleIndexed.article_id.in_(article_ids))
    )

    # Find classification_result IDs for these articles
    cr_ids_stmt = select(ClassificationResult.id).where(
        ClassificationResult.article_id.in_(article_ids)
    )
    cr_ids = list((await session.execute(cr_ids_stmt)).scalars().all())

    # Delete article_tags (cascade from classification_results)
    if cr_ids:
        await session.execute(
            sa_delete(ArticleTag).where(ArticleTag.classification_result_id.in_(cr_ids))
        )

    # Delete classification_results
    if cr_ids:
        await session.execute(
            sa_delete(ClassificationResult).where(ClassificationResult.id.in_(cr_ids))
        )

    # Delete article_group_members and track affected groups
    affected_group_ids_stmt = select(ArticleGroupMember.group_id).where(
        ArticleGroupMember.article_id.in_(article_ids)
    )
    affected_group_ids = list((await session.execute(affected_group_ids_stmt)).scalars().all())

    await session.execute(
        sa_delete(ArticleGroupMember).where(ArticleGroupMember.article_id.in_(article_ids))
    )

    # Delete groups that have no remaining members
    deleted_groups = 0
    if affected_group_ids:
        for group_id in set(affected_group_ids):
            remaining = (await session.execute(
                select(func.count()).where(ArticleGroupMember.group_id == group_id)
            )).scalar() or 0
            if remaining == 0:
                await session.execute(
                    sa_delete(ArticleGroup).where(ArticleGroup.id == group_id)
                )
                deleted_groups += 1

    # Delete articles
    await session.execute(
        sa_delete(Article).where(Article.id.in_(article_ids))
    )

    await session.commit()

    # Clear cache since data changed
    _cache.clear()

    log.info("cleanup_complete", deleted_articles=len(article_ids), deleted_groups=deleted_groups, before=str(before))

    return CleanupResponse(
        deleted_articles=len(article_ids),
        deleted_groups=deleted_groups,
        before_date=str(before),
    )


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
