import asyncio
from datetime import datetime
from urllib.parse import urlparse

import httpx
import structlog
import trafilatura
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import Article, Feed
from src.services.rate_limiter import RateLimiter

logger = structlog.get_logger()


class ArticleExtractorService:
    def __init__(self, http_client: httpx.AsyncClient, rate_limiter: RateLimiter) -> None:
        self.http_client = http_client
        self.rate_limiter = rate_limiter

    async def extract_article(self, article: Article, db: AsyncSession) -> Article:
        domain = urlparse(article.url).netloc
        log = logger.bind(article_id=article.id, url=article.url)

        await self.rate_limiter.acquire(domain)

        try:
            response = await self.http_client.get(article.url, follow_redirects=True)
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "60"))
                await self.rate_limiter.notify_retry_after(domain, retry_after)
                article.status = "failed"
                article.updated_at = datetime.utcnow()
                await db.commit()
                return article
            response.raise_for_status()
            html = response.text
        except httpx.HTTPError as exc:
            log.warning("article_download_failed", error=str(exc))
            article.status = "failed"
            article.updated_at = datetime.utcnow()
            await db.commit()
            return article

        loop = asyncio.get_event_loop()
        extracted_text = await loop.run_in_executor(None, trafilatura.extract, html)

        if extracted_text:
            article.extracted_text = extracted_text
            article.status = "extracted"
            log.info("article_extracted")
        else:
            article.status = "downloaded"
            log.info("article_downloaded_no_text")

        article.updated_at = datetime.utcnow()
        await db.commit()
        return article

    async def extract_feed_articles(self, feed: Feed, db: AsyncSession) -> dict:
        result = await db.execute(
            select(Article).where(Article.feed_id == feed.id, Article.status == "pending")
        )
        articles = result.scalars().all()

        total = len(articles)
        extracted = 0
        failed = 0
        errors: list[str] = []

        for article in articles:
            try:
                await self.extract_article(article, db)
                if article.status == "extracted":
                    extracted += 1
                elif article.status == "failed":
                    failed += 1
                    errors.append(f"Article {article.id} ({article.url}): download failed")
            except Exception as exc:
                failed += 1
                errors.append(f"Article {article.id} ({article.url}): {exc}")
                logger.warning("article_extraction_error", article_id=article.id, error=str(exc))

        return {
            "feed_id": feed.id,
            "total": total,
            "extracted": extracted,
            "failed": failed,
            "errors": errors,
        }
