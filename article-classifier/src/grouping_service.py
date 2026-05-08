from collections import defaultdict
from datetime import date

import structlog
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.database import AsyncSessionFactory
from src.grouping_pipeline import GroupingPipeline
from src.grouping_schemas import (
    ArticleForClustering,
    ArticleForDetail,
    ClusterItem,
    ClusteringOutput,
    ExistingGroupAddition,
    ExistingGroupForClustering,
    GroupingTriggerResponse,
)
from src.models import Article, ArticleGroup, ArticleGroupMember, ArticleTag, ClassificationResult, Tag

log = structlog.get_logger()


class GroupingService:
    def __init__(self) -> None:
        self._pipeline = GroupingPipeline(settings)
        self._model = settings.GROUPING_LLM_MODEL or settings.LLM_MODEL

    async def get_candidates(
        self, session: AsyncSession, target_date: date
    ) -> dict[str, list[Article]]:
        """Fetch ungrouped classified articles for target_date, grouped by first tag category."""
        stmt = (
            select(Article)
            .join(ClassificationResult, ClassificationResult.article_id == Article.id)
            .outerjoin(ArticleGroupMember, ArticleGroupMember.article_id == Article.id)
            .where(
                func.date(Article.published_at) == target_date,
                ClassificationResult.summary.is_not(None),
                ClassificationResult.summary != "",
                ClassificationResult.importance_score >= settings.GROUPING_MIN_SCORE,
                ArticleGroupMember.id.is_(None),
            )
            .options(
                selectinload(Article.classification_result)
                .selectinload(ClassificationResult.article_tags)
                .selectinload(ArticleTag.tag)
                .selectinload(Tag.parent)
            )
            .order_by(Article.published_at.desc())
        )
        result = await session.execute(stmt)
        articles = list(result.scalars().all())

        by_category: dict[str, list[Article]] = defaultdict(list)
        for article in articles:
            cr = article.classification_result
            if not cr or not cr.article_tags:
                continue
            first_at = min(cr.article_tags, key=lambda at: at.id)
            tag = first_at.tag
            if tag and tag.parent:
                category = tag.parent.name
            elif tag:
                category = tag.name
            else:
                continue
            by_category[category].append(article)

        return dict(by_category)

    async def get_existing_groups(
        self, session: AsyncSession, target_date: date
    ) -> dict[str, list[ArticleGroup]]:
        """Fetch existing groups for the date, grouped by category."""
        stmt = (
            select(ArticleGroup)
            .where(ArticleGroup.grouped_date == target_date)
            .options(
                selectinload(ArticleGroup.members).selectinload(ArticleGroupMember.article)
            )
        )
        result = await session.execute(stmt)
        groups = list(result.scalars().all())

        by_category: dict[str, list[ArticleGroup]] = defaultdict(list)
        for group in groups:
            by_category[group.category].append(group)
        return dict(by_category)

    def _validate_clustering_output(
        self,
        output: ClusteringOutput,
        valid_article_ids: set[int],
    ) -> ClusteringOutput:
        """Discard single-article groups and deduplicate article assignments across groups."""
        seen: set[int] = set()
        valid_groups: list[ClusterItem] = []

        for cluster in output.groups:
            local_seen: set[int] = set()
            filtered_ids = []
            for aid in cluster.article_ids:
                if aid in valid_article_ids and aid not in seen and aid not in local_seen:
                    filtered_ids.append(aid)
                    local_seen.add(aid)
            if len(filtered_ids) < 2:
                log.warning(
                    "grouping_cluster_discarded",
                    original_count=len(cluster.article_ids),
                    filtered_count=len(filtered_ids),
                    topic=cluster.topic[:60] if cluster.topic else "",
                )
                continue
            seen.update(filtered_ids)
            valid_groups.append(ClusterItem(
                article_ids=filtered_ids,
                topic=cluster.topic,
                justification=cluster.justification,
            ))

        valid_additions: list[ExistingGroupAddition] = []
        for addition in output.existing_group_additions:
            local_seen = set()
            filtered_ids = []
            for aid in addition.article_ids:
                if aid in valid_article_ids and aid not in seen and aid not in local_seen:
                    filtered_ids.append(aid)
                    local_seen.add(aid)
            if not filtered_ids:
                continue
            seen.update(filtered_ids)
            valid_additions.append(ExistingGroupAddition(
                group_id=addition.group_id,
                article_ids=filtered_ids,
            ))

        return ClusteringOutput(
            groups=valid_groups,
            existing_group_additions=valid_additions,
            standalone_ids=output.standalone_ids,
        )

    async def run_grouping(self, target_date: date | None = None) -> GroupingTriggerResponse:
        """Run full grouping pipeline for a date. Returns stats."""
        if target_date is None:
            target_date = date.today()

        log.info("grouping_started", date=str(target_date))

        groups_created = 0
        groups_updated = 0
        articles_grouped = 0

        async with AsyncSessionFactory() as session:
            candidates_by_category = await self.get_candidates(session, target_date)
            existing_by_category = await self.get_existing_groups(session, target_date)

        log.info(
            "grouping_candidates_loaded",
            categories=len(candidates_by_category),
            total_articles=sum(len(v) for v in candidates_by_category.values()),
            existing_groups=sum(len(v) for v in existing_by_category.values()),
        )

        for category, articles in candidates_by_category.items():
            # Enforce max articles limit — keep most recent (already sorted desc by published_at)
            if len(articles) > settings.GROUPING_MAX_ARTICLES_PER_CATEGORY:
                articles = articles[:settings.GROUPING_MAX_ARTICLES_PER_CATEGORY]

            if len(articles) < settings.GROUPING_MIN_ARTICLES:
                log.info(
                    "grouping_category_skipped",
                    category=category,
                    article_count=len(articles),
                    min_articles=settings.GROUPING_MIN_ARTICLES,
                )
                continue

            existing_groups = existing_by_category.get(category, [])
            article_map = {a.id: a for a in articles}
            valid_article_ids = set(article_map.keys())

            articles_for_clustering = [
                ArticleForClustering(
                    id=a.id,
                    title=a.title,
                    summary=a.classification_result.summary,
                    source_url=a.url,
                )
                for a in articles
            ]
            existing_for_clustering = [
                ExistingGroupForClustering(
                    group_id=g.id,
                    title=g.title,
                    summary=g.summary,
                )
                for g in existing_groups
            ]

            try:
                clustering_output = await self._pipeline.cluster(
                    articles_for_clustering, existing_for_clustering
                )
            except Exception as exc:
                log.error(
                    "grouping_clustering_failed",
                    category=category,
                    error=str(exc)[:500],
                )
                continue

            validated = self._validate_clustering_output(clustering_output, valid_article_ids)

            log.info(
                "grouping_clustering_validated",
                category=category,
                new_groups=len(validated.groups),
                existing_additions=len(validated.existing_group_additions),
            )

            # Generate details for new groups (LLM calls outside the DB transaction)
            new_group_data: list[tuple[list[int], object]] = []
            for cluster in validated.groups:
                member_articles = [article_map[aid] for aid in cluster.article_ids if aid in article_map]
                if len(member_articles) < 2:
                    continue
                try:
                    articles_for_detail = [
                        ArticleForDetail(id=a.id, title=a.title, extracted_text=a.extracted_text)
                        for a in member_articles
                    ]
                    detail_output = await self._pipeline.generate_detail(articles_for_detail)
                    new_group_data.append((cluster.article_ids, detail_output))
                except Exception as exc:
                    log.error(
                        "grouping_detail_generation_failed",
                        category=category,
                        topic=cluster.topic[:60] if cluster.topic else "",
                        error=str(exc)[:500],
                    )

            # Persist all new groups in a single per-category transaction
            if new_group_data:
                async with AsyncSessionFactory() as session:
                    try:
                        for article_ids, detail_output in new_group_data:
                            group = ArticleGroup(
                                title=detail_output.title,
                                summary=detail_output.summary,
                                detail=detail_output.detail,
                                category=category,
                                grouped_date=target_date,
                                llm_model=self._model,
                                token_usage=None,
                            )
                            session.add(group)
                            await session.flush()
                            for aid in article_ids:
                                if aid in article_map:
                                    session.add(ArticleGroupMember(group_id=group.id, article_id=aid))
                        await session.commit()
                        groups_created += len(new_group_data)
                        articles_grouped += sum(len(ids) for ids, _ in new_group_data)
                        log.info(
                            "grouping_new_groups_persisted",
                            category=category,
                            count=len(new_group_data),
                        )
                    except Exception as exc:
                        await session.rollback()
                        log.error(
                            "grouping_category_persist_failed",
                            category=category,
                            error=str(exc)[:500],
                        )

            # Handle existing group additions
            existing_group_map = {g.id: g for g in existing_groups}
            for addition in validated.existing_group_additions:
                existing_group = existing_group_map.get(addition.group_id)
                if not existing_group:
                    log.warning("grouping_addition_unknown_group", group_id=addition.group_id)
                    continue

                new_member_articles = [
                    article_map[aid] for aid in addition.article_ids if aid in article_map
                ]
                if not new_member_articles:
                    continue

                # Combine existing + new members for detail regeneration
                existing_member_articles = [m.article for m in existing_group.members]
                all_articles_for_detail = existing_member_articles + new_member_articles

                try:
                    articles_for_detail = [
                        ArticleForDetail(id=a.id, title=a.title, extracted_text=a.extracted_text)
                        for a in all_articles_for_detail
                    ]
                    detail_output = await self._pipeline.generate_detail(articles_for_detail)
                except Exception as exc:
                    log.error(
                        "grouping_detail_regen_failed",
                        group_id=addition.group_id,
                        error=str(exc)[:500],
                    )
                    continue

                async with AsyncSessionFactory() as session:
                    try:
                        db_group = await session.get(ArticleGroup, addition.group_id)
                        if db_group is None:
                            log.warning("grouping_group_not_found", group_id=addition.group_id)
                            continue

                        for a in new_member_articles:
                            session.add(ArticleGroupMember(group_id=db_group.id, article_id=a.id))

                        db_group.title = detail_output.title
                        db_group.summary = detail_output.summary
                        db_group.detail = detail_output.detail
                        db_group.llm_model = self._model

                        await session.commit()
                        groups_updated += 1
                        articles_grouped += len(new_member_articles)
                        log.info(
                            "grouping_group_updated",
                            group_id=addition.group_id,
                            new_members=len(new_member_articles),
                        )
                    except Exception as exc:
                        await session.rollback()
                        log.error(
                            "grouping_group_update_failed",
                            group_id=addition.group_id,
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
