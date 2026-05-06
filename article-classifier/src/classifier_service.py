import asyncio
import json

import structlog
from langchain_openai import ChatOpenAI
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import AsyncSessionFactory
from src.models import Article, ArticleTag, ClassificationResult, Tag
from src.pipeline import ClassificationOutput, ClassificationPipeline
from src.schemas import TagOutput

log = structlog.get_logger()

_is_processing = False


class ClassifierService:
    def __init__(self) -> None:
        self._pipeline = ClassificationPipeline(settings)
        self._dedup_llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/sinalo/article-classifier",
                "X-Title": "Article Classifier",
            },
        )

    async def get_unprocessed_articles(self, session: AsyncSession, batch_size: int) -> list[Article]:
        """Fetch articles with extracted_text but no classification result."""
        stmt = (
            select(Article)
            .where(
                Article.extracted_text.is_not(None),
                Article.extracted_text != "",
                ~exists().where(ClassificationResult.article_id == Article.id),
            )
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_existing_tags(self, session: AsyncSession) -> list[Tag]:
        """Fetch all tags."""
        result = await session.execute(select(Tag))
        return list(result.scalars().all())

    def _tags_to_prompt_dicts(self, tags: list[Tag]) -> list[dict]:
        """Convert Tag objects to {category, subcategory} dicts for the LLM prompt."""
        parent_map: dict[int, str] = {t.id: t.name for t in tags if t.parent_id is None}
        return [
            {"category": parent_map[t.parent_id], "subcategory": t.name}
            for t in tags
            if t.parent_id is not None and t.parent_id in parent_map
        ]

    async def _dedup_check(
        self, proposed: str, existing_subs: list[str], category: str
    ) -> tuple[bool, str | None]:
        """Ask LLM whether proposed subcategory is a duplicate of an existing one."""
        if not existing_subs:
            return False, None
        prompt = (
            f"You are a tag deduplication assistant for a news classifier.\n"
            f"Category: '{category}'\n"
            f"Proposed new subcategory: '{proposed}'\n"
            f"Existing subcategories: {', '.join(existing_subs)}\n\n"
            f"Is '{proposed}' a synonym or near-duplicate of any existing subcategory? "
            f"Reply with ONLY valid JSON, no markdown:\n"
            f'{{\"is_duplicate\": true or false, \"existing_name\": \"matching name or null\"}}'
        )
        try:
            response = await self._dedup_llm.ainvoke([{"role": "user", "content": prompt}])
            content = str(response.content).strip()
            # Strip markdown code fences if present
            if "```" in content:
                parts = content.split("```")
                content = parts[1] if len(parts) > 1 else parts[0]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)
            is_dup: bool = bool(data.get("is_duplicate", False))
            existing_name: str | None = data.get("existing_name") or None
            if existing_name == "null":
                existing_name = None
            return is_dup, existing_name
        except Exception as exc:
            log.warning("tag_dedup_check_failed", proposed=proposed, error=str(exc)[:200])
            return False, None

    async def _validate_tags(
        self,
        session: AsyncSession,
        llm_tags: list[TagOutput],
        existing_tags: list[Tag],
    ) -> list[Tag]:
        """
        Validate LLM tags against DB:
        - Map known category+subcategory directly.
        - For unknown subcategories, run LLM dedup; map to existing or create new.
        - Enforce 1–5 tags.
        """
        parent_map: dict[str, Tag] = {t.name.lower(): t for t in existing_tags if t.parent_id is None}
        subcategory_map: dict[tuple[str, str], Tag] = {}
        for t in existing_tags:
            if t.parent_id is not None:
                parent = parent_map.get(next(
                    (p.name.lower() for p in existing_tags if p.id == t.parent_id), ""
                ))
                if parent:
                    subcategory_map[(parent.name.lower(), t.name.lower())] = t

        validated: list[Tag] = []

        for tag_out in llm_tags:
            cat_key = tag_out.category.lower()
            sub_key = tag_out.subcategory.lower()

            if cat_key not in parent_map:
                log.warning("invalid_main_category", category=tag_out.category)
                continue

            parent_tag = parent_map[cat_key]
            direct_key = (cat_key, sub_key)

            if direct_key in subcategory_map:
                validated.append(subcategory_map[direct_key])
                continue

            # Unknown subcategory — run dedup check
            existing_subs = [t.name for t in existing_tags if t.parent_id == parent_tag.id]
            is_dup, match_name = await self._dedup_check(tag_out.subcategory, existing_subs, tag_out.category)

            if is_dup and match_name:
                match_key = (cat_key, match_name.lower())
                if match_key in subcategory_map:
                    validated.append(subcategory_map[match_key])
                    log.info("tag_dedup_mapped", proposed=tag_out.subcategory, mapped_to=match_name)
                else:
                    log.warning("tag_dedup_match_not_found", proposed=tag_out.subcategory, matched=match_name)
            else:
                new_tag = Tag(name=tag_out.subcategory, parent_id=parent_tag.id)
                session.add(new_tag)
                await session.flush()
                existing_tags = existing_tags + [new_tag]
                subcategory_map[(cat_key, tag_out.subcategory.lower())] = new_tag
                validated.append(new_tag)
                log.info("tag_created", category=tag_out.category, subcategory=tag_out.subcategory)

        return validated[:5]

    async def _persist_result(
        self,
        session: AsyncSession,
        article: Article,
        output: ClassificationOutput,
        resolved_tags: list[Tag],
    ) -> None:
        """Save classification result and article_tags, then commit."""
        cr = ClassificationResult(
            article_id=article.id,
            content_type=output.content_type,
            importance_score=output.importance_score,
            summary=output.summary,
            reason=output.reason,
            llm_model=output.llm_model,
            token_usage=output.token_usage,
            processing_time_ms=int(output.processing_time_ms),
        )
        session.add(cr)
        await session.flush()

        for tag in resolved_tags:
            session.add(ArticleTag(classification_result_id=cr.id, tag_id=tag.id))

        await session.commit()

    async def classify_batch(self) -> dict:
        """Process one batch of unprocessed articles. Returns {processed, failed}."""
        async with AsyncSessionFactory() as session:
            articles = await self.get_unprocessed_articles(session, settings.BATCH_SIZE)
            if not articles:
                return {"processed": 0, "failed": 0}

            existing_tags = await self.get_existing_tags(session)
            tags_for_prompt = self._tags_to_prompt_dicts(existing_tags)

            processed = 0
            failed = 0

            for article in articles:
                try:
                    output = await self._pipeline.classify(
                        article_title=article.title or "",
                        article_text=article.extracted_text or "",
                        article_summary=None,
                        existing_tags=tags_for_prompt,
                    )

                    is_short = len(article.extracted_text or "") < 100
                    resolved_tags = await self._validate_tags(session, output.tags, existing_tags)

                    if not resolved_tags and not is_short:
                        log.error("all_tags_failed_validation", article_id=article.id)
                        failed += 1
                        continue

                    await self._persist_result(session, article, output, resolved_tags)

                    # Refresh tag list for subsequent articles in the same batch
                    existing_tags = await self.get_existing_tags(session)
                    tags_for_prompt = self._tags_to_prompt_dicts(existing_tags)

                    processed += 1
                    log.info(
                        "article_persisted",
                        article_id=article.id,
                        tags_count=len(resolved_tags),
                        content_type=output.content_type,
                        importance_score=output.importance_score,
                    )

                except Exception as exc:
                    log.error(
                        "article_classification_failed",
                        article_id=article.id,
                        error=str(exc)[:500],
                    )
                    failed += 1
                    await session.rollback()
                    # Refresh tags from DB to discard any flushed-but-rolled-back new tags
                    existing_tags = await self.get_existing_tags(session)
                    tags_for_prompt = self._tags_to_prompt_dicts(existing_tags)

        return {"processed": processed, "failed": failed}

    async def run_classification(self) -> None:
        """Process all unprocessed articles in batches until none remain."""
        global _is_processing
        try:
            while True:
                result = await self.classify_batch()
                log.info("batch_complete", **result)
                if result["processed"] == 0 and result["failed"] == 0:
                    break
        finally:
            _is_processing = False
            log.info("classification_finished")

    async def count_unprocessed(self) -> int:
        """Count articles pending classification."""
        async with AsyncSessionFactory() as session:
            stmt = select(func.count()).select_from(Article).where(
                Article.extracted_text.is_not(None),
                Article.extracted_text != "",
                ~exists().where(ClassificationResult.article_id == Article.id),
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    async def count_classified(self) -> int:
        """Count articles that have been classified."""
        async with AsyncSessionFactory() as session:
            result = await session.execute(select(func.count()).select_from(ClassificationResult))
            return result.scalar() or 0


def is_processing() -> bool:
    return _is_processing


async def trigger_classification(service: ClassifierService) -> int:
    """Trigger async classification. Returns queued count. Raises if already running."""
    global _is_processing
    if _is_processing:
        raise RuntimeError("Classification already in progress")
    queued = await service.count_unprocessed()
    _is_processing = True
    asyncio.create_task(service.run_classification())
    return queued
