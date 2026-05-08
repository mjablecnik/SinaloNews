import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import Feed, Website
from src.services.extractor_service import ArticleExtractorService
from src.services.parser_service import FeedParserService

logger = structlog.get_logger()


class BatchProcessor:
    def __init__(
        self,
        parser_service: FeedParserService,
        extractor_service: ArticleExtractorService,
    ) -> None:
        self.parser_service = parser_service
        self.extractor_service = extractor_service

    async def process_website(self, website: Website, db: AsyncSession) -> dict:
        log = logger.bind(website_id=website.id)
        feeds_parsed = 0
        articles_discovered = 0
        articles_extracted = 0
        errors: list[str] = []

        result = await db.execute(select(Feed).where(Feed.website_id == website.id))
        feeds = result.scalars().all()
        # Cache feed IDs upfront — after rollback, ORM objects become expired
        # and accessing their attributes triggers lazy loads that fail in async context.
        feed_ids = [feed.id for feed in feeds]

        for feed_id in feed_ids:
            # Always fetch a fresh feed object to avoid expired-state issues
            feed = await db.get(Feed, feed_id)
            if feed is None:
                continue

            try:
                new_articles = await self.parser_service.parse_feed(feed, db)
                feeds_parsed += 1
                articles_discovered += len(new_articles)
                log.info("feed_parsed_in_batch", feed_id=feed_id, new_articles=len(new_articles))
            except Exception as exc:
                await db.rollback()
                errors.append(f"Feed {feed_id}: parse error: {exc}")
                log.warning("feed_parse_error", feed_id=feed_id, error=str(exc))
                continue

            try:
                # Re-fetch feed after parse_feed may have committed/changed session state
                feed = await db.get(Feed, feed_id)
                if feed is None:
                    continue
                extract_result = await self.extractor_service.extract_feed_articles(feed, db)
                articles_extracted += extract_result["extracted"]
                errors.extend(extract_result["errors"])
            except Exception as exc:
                await db.rollback()
                errors.append(f"Feed {feed_id}: extraction error: {exc}")
                log.warning("feed_extraction_error", feed_id=feed_id, error=str(exc))

        return {
            "feeds_parsed": feeds_parsed,
            "articles_discovered": articles_discovered,
            "articles_extracted": articles_extracted,
            "errors": errors,
        }

    async def process_all(self, db: AsyncSession) -> dict:
        result = await db.execute(select(Website))
        websites = result.scalars().all()
        website_ids = [w.id for w in websites]

        feeds_parsed = 0
        articles_discovered = 0
        articles_extracted = 0
        errors: list[str] = []

        for website_id in website_ids:
            website = await db.get(Website, website_id)
            if website is None:
                continue
            try:
                summary = await self.process_website(website, db)
            except Exception as exc:
                await db.rollback()
                errors.append(f"Website {website_id}: unexpected error: {exc}")
                logger.warning("website_process_error", website_id=website_id, error=str(exc))
                continue
            feeds_parsed += summary["feeds_parsed"]
            articles_discovered += summary["articles_discovered"]
            articles_extracted += summary["articles_extracted"]
            errors.extend(summary["errors"])

        logger.info(
            "batch_complete",
            feeds_parsed=feeds_parsed,
            articles_discovered=articles_discovered,
            articles_extracted=articles_extracted,
            error_count=len(errors),
        )
        return {
            "feeds_parsed": feeds_parsed,
            "articles_discovered": articles_discovered,
            "articles_extracted": articles_extracted,
            "errors": errors,
        }
