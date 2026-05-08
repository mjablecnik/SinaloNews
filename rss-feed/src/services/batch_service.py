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

        for feed in feeds:
            try:
                new_articles = await self.parser_service.parse_feed(feed, db)
                feeds_parsed += 1
                articles_discovered += len(new_articles)
                log.info("feed_parsed_in_batch", feed_id=feed.id, new_articles=len(new_articles))
            except Exception as exc:
                await db.rollback()
                errors.append(f"Feed {feed.id}: parse error: {exc}")
                log.warning("feed_parse_error", feed_id=feed.id, error=str(exc))
                continue

            try:
                extract_result = await self.extractor_service.extract_feed_articles(feed, db)
                articles_extracted += extract_result["extracted"]
                errors.extend(extract_result["errors"])
            except Exception as exc:
                await db.rollback()
                errors.append(f"Feed {feed.id}: extraction error: {exc}")
                log.warning("feed_extraction_error", feed_id=feed.id, error=str(exc))

        return {
            "feeds_parsed": feeds_parsed,
            "articles_discovered": articles_discovered,
            "articles_extracted": articles_extracted,
            "errors": errors,
        }

    async def process_all(self, db: AsyncSession) -> dict:
        result = await db.execute(select(Website))
        websites = result.scalars().all()

        feeds_parsed = 0
        articles_discovered = 0
        articles_extracted = 0
        errors: list[str] = []

        for website in websites:
            summary = await self.process_website(website, db)
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
