from datetime import date, datetime, timezone

import structlog
from qdrant_client import AsyncQdrantClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.database import AsyncSessionFactory
from src.embedding_client import EmbeddingClient, EmbeddingError
from src.grouping_pipeline import GroupingPipeline
from src.grouping_schemas import ArticleForDetail, GroupingTriggerResponse, RegenerationResponse
from src.models import Article, ArticleGroup, ArticleGroupMember, ArticleTag, ClassificationResult, FullArticleIndexed, Tag
from src.similarity_service import SimilarityService

log = structlog.get_logger()


class GroupingService:
    def __init__(self) -> None:
        self._embedding_client = EmbeddingClient(
            api_url=settings.EMBEDDING_API_URL,
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )
        qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        self._similarity_service = SimilarityService(qdrant_client, settings)
        self._pipeline = GroupingPipeline(settings)
        self._model = settings.GROUPING_LLM_MODEL or settings.LLM_MODEL

    async def _get_candidates(self, session: AsyncSession, target_date: date) -> list[Article]:
        """Fetch classified articles for target_date not yet in full_article_indexed."""
        stmt = (
            select(Article)
            .join(ClassificationResult, ClassificationResult.article_id == Article.id)
            .outerjoin(FullArticleIndexed, FullArticleIndexed.article_id == Article.id)
            .where(
                Article.published_at.isnot(None),
                ClassificationResult.summary.isnot(None),
                ClassificationResult.summary != "",
                FullArticleIndexed.article_id.is_(None),
            )
            .where(
                Article.published_at.between(
                    datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0),
                    datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59),
                )
            )
            .order_by(Article.published_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _get_group_for_article(
        self, session: AsyncSession, article_id: int
    ) -> ArticleGroup | None:
        """Return the ArticleGroup containing the given article_id, or None."""
        stmt = (
            select(ArticleGroup)
            .join(ArticleGroupMember, ArticleGroupMember.group_id == ArticleGroup.id)
            .where(ArticleGroupMember.article_id == article_id)
            .options(selectinload(ArticleGroup.members).selectinload(ArticleGroupMember.article))
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def _is_article_in_any_group(self, session: AsyncSession, article_id: int) -> bool:
        """Return True if the article is already a member of any group."""
        stmt = select(ArticleGroupMember).where(ArticleGroupMember.article_id == article_id)
        result = await session.execute(stmt)
        return result.scalars().first() is not None

    async def _get_article_category(self, session: AsyncSession, article_id: int) -> str:
        """Get the main category of an article from its first tag."""
        stmt = (
            select(ArticleTag)
            .where(ArticleTag.classification_result_id == (
                select(ClassificationResult.id)
                .where(ClassificationResult.article_id == article_id)
                .scalar_subquery()
            ))
            .options(selectinload(ArticleTag.tag).selectinload(Tag.parent))
            .order_by(ArticleTag.id.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        first_at = result.scalars().first()
        if first_at and first_at.tag:
            if first_at.tag.parent:
                return first_at.tag.parent.name
            return first_at.tag.name
        return ""

    async def run_grouping(self, target_date: date | None = None) -> GroupingTriggerResponse:
        """Embed unindexed articles, perform similarity matching, create/update groups."""
        if target_date is None:
            target_date = date.today()

        log.info("grouping_started", date=str(target_date))

        groups_created = 0
        groups_updated = 0
        articles_grouped = 0

        async with AsyncSessionFactory() as session:
            candidates = await self._get_candidates(session, target_date)

        log.info("grouping_candidates_loaded", total_articles=len(candidates))

        if not candidates:
            log.info("grouping_no_candidates", date=str(target_date))
            return GroupingTriggerResponse(
                groups_created=0,
                groups_updated=0,
                articles_grouped=0,
                date=target_date,
            )

        await self._similarity_service.ensure_collection()

        # Phase 1: embed and upsert all candidates into Qdrant
        indexed_article_ids: list[int] = []
        for article in candidates:
            if not article.extracted_text or not article.extracted_text.strip():
                log.warning("grouping_skipping_empty_text", article_id=article.id)
                continue

            try:
                vector = await self._embedding_client.embed_text(article.extracted_text)
            except EmbeddingError as exc:
                log.error("grouping_embedding_failed", article_id=article.id, error=str(exc)[:300])
                continue

            try:
                metadata = {
                    "article_id": article.id,
                    "article_title": article.title or "",
                    "published_at": article.published_at.isoformat() if article.published_at else "",
                    "indexed_at": datetime.now(timezone.utc).isoformat(),
                }
                await self._similarity_service.upsert_article(article.id, vector, metadata)
            except Exception as exc:
                log.error("grouping_upsert_failed", article_id=article.id, error=str(exc)[:300])
                continue

            async with AsyncSessionFactory() as session:
                try:
                    session.add(FullArticleIndexed(article_id=article.id))
                    await session.commit()
                    indexed_article_ids.append(article.id)
                except Exception as exc:
                    await session.rollback()
                    log.error(
                        "grouping_index_tracking_failed",
                        article_id=article.id,
                        error=str(exc)[:300],
                    )

        log.info("grouping_indexing_complete", indexed=len(indexed_article_ids))

        # Phase 2: sequential similarity matching for newly indexed articles
        article_map = {a.id: a for a in candidates}

        for article_id in indexed_article_ids:
            article = article_map.get(article_id)
            if article is None or not article.extracted_text:
                continue

            try:
                vector = await self._embedding_client.embed_text(article.extracted_text)
                match = await self._similarity_service.find_most_similar(article_id, vector)
            except EmbeddingError as exc:
                log.error(
                    "grouping_similarity_embedding_failed",
                    article_id=article_id,
                    error=str(exc)[:300],
                )
                continue
            except Exception as exc:
                log.error(
                    "grouping_similarity_search_failed",
                    article_id=article_id,
                    error=str(exc)[:300],
                )
                continue

            if match is None:
                log.info("grouping_no_match", article_id=article_id)
                continue

            matched_article_id, score = match

            if score < settings.GROUPING_SIMILARITY_THRESHOLD:
                log.info("grouping_below_threshold", article_id=article_id, score=score)
                continue

            log.info(
                "grouping_match_found",
                article_id=article_id,
                matched_article_id=matched_article_id,
                score=score,
            )

            async with AsyncSessionFactory() as session:
                try:
                    existing_group = await self._get_group_for_article(session, matched_article_id)

                    if existing_group is not None:
                        existing_member_ids = {m.article_id for m in existing_group.members}
                        if article_id in existing_member_ids:
                            log.warning(
                                "grouping_already_member",
                                article_id=article_id,
                                group_id=existing_group.id,
                            )
                            continue

                        session.add(ArticleGroupMember(group_id=existing_group.id, article_id=article_id))
                        all_member_articles = [m.article for m in existing_group.members] + [article]
                        most_recent_date = max(
                            (a.published_at.date() for a in all_member_articles if a.published_at),
                            default=target_date,
                        )
                        existing_group.grouped_date = most_recent_date
                        existing_group.needs_regeneration = True
                        await session.commit()
                        groups_updated += 1
                        articles_grouped += 1
                        log.info(
                            "grouping_article_added_to_group",
                            article_id=article_id,
                            group_id=existing_group.id,
                        )
                    else:
                        matched_article = article_map.get(matched_article_id)
                        placeholder_title = article.title or f"Article group {article_id}"

                        dates = [
                            a.published_at.date()
                            for a in [article, matched_article]
                            if a is not None and a.published_at
                        ]
                        grouped_date = max(dates) if dates else target_date

                        category = await self._get_article_category(session, article_id)

                        group = ArticleGroup(
                            title=placeholder_title,
                            summary="",
                            detail="",
                            category=category,
                            grouped_date=grouped_date,
                            llm_model=None,
                            token_usage=None,
                            needs_regeneration=True,
                        )
                        session.add(group)
                        await session.flush()

                        session.add(ArticleGroupMember(group_id=group.id, article_id=article_id))

                        matched_already_grouped = await self._is_article_in_any_group(
                            session, matched_article_id
                        )
                        if not matched_already_grouped:
                            session.add(
                                ArticleGroupMember(group_id=group.id, article_id=matched_article_id)
                            )

                        await session.commit()
                        groups_created += 1
                        articles_grouped += 1
                        log.info(
                            "grouping_new_group_created",
                            group_id=group.id,
                            article_id=article_id,
                            matched_article_id=matched_article_id,
                        )
                except Exception as exc:
                    await session.rollback()
                    log.error(
                        "grouping_persist_failed",
                        article_id=article_id,
                        error=str(exc)[:500],
                    )

        log.info(
            "grouping_finished",
            date=str(target_date),
            groups_created=groups_created,
            groups_updated=groups_updated,
            articles_grouped=articles_grouped,
        )

        return GroupingTriggerResponse(
            groups_created=groups_created,
            groups_updated=groups_updated,
            articles_grouped=articles_grouped,
            date=target_date,
        )

    async def run_regeneration(self) -> RegenerationResponse:
        """Regenerate detail text for all groups with needs_regeneration=True."""
        log.info("regeneration_started")
        groups_regenerated = 0

        async with AsyncSessionFactory() as session:
            stmt = (
                select(ArticleGroup)
                .where(ArticleGroup.needs_regeneration.is_(True))
                .options(selectinload(ArticleGroup.members).selectinload(ArticleGroupMember.article))
            )
            result = await session.execute(stmt)
            flagged_groups = list(result.scalars().all())

        log.info("regeneration_groups_found", count=len(flagged_groups))

        for group in flagged_groups:
            member_articles = [m.article for m in group.members if m.article is not None]
            articles_with_text = [a for a in member_articles if a.extracted_text]

            if not articles_with_text:
                log.warning("regeneration_no_text", group_id=group.id)
                continue

            try:
                articles_for_detail = [
                    ArticleForDetail(id=a.id, title=a.title, extracted_text=a.extracted_text)
                    for a in articles_with_text
                ]
                detail_output = await self._pipeline.generate_detail(articles_for_detail)
            except Exception as exc:
                log.error(
                    "regeneration_detail_failed", group_id=group.id, error=str(exc)[:500]
                )
                continue

            async with AsyncSessionFactory() as session:
                try:
                    db_group = await session.get(ArticleGroup, group.id)
                    if db_group is None:
                        log.warning("regeneration_group_not_found", group_id=group.id)
                        continue
                    db_group.title = detail_output.title
                    db_group.summary = detail_output.summary
                    db_group.detail = detail_output.detail
                    db_group.llm_model = self._model
                    db_group.needs_regeneration = False
                    await session.commit()
                    groups_regenerated += 1
                    log.info("regeneration_group_done", group_id=group.id)
                except Exception as exc:
                    await session.rollback()
                    log.error(
                        "regeneration_persist_failed", group_id=group.id, error=str(exc)[:500]
                    )

        log.info("regeneration_finished", groups_regenerated=groups_regenerated)
        return RegenerationResponse(groups_regenerated=groups_regenerated)
