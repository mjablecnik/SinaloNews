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
            html = self._safe_decode(response)
            if html is None:
                log.warning("article_not_text", content_type=response.headers.get("content-type"))
                article.status = "failed"
                article.updated_at = datetime.utcnow()
                await db.commit()
                return article
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

    @staticmethod
    def _safe_decode(response: httpx.Response) -> str | None:
        """Decode response content, returning None if it's not valid text.

        Rejects binary responses and strips null bytes that PostgreSQL
        cannot store in TEXT/VARCHAR columns.
        """
        content_type = response.headers.get("content-type", "")
        # Reject obviously binary content types
        if any(
            t in content_type
            for t in ("application/pdf", "application/octet-stream", "image/", "audio/", "video/")
        ):
            return None

        try:
            text = response.text
        except (UnicodeDecodeError, LookupError):
            return None

        # PostgreSQL cannot store null bytes in TEXT columns
        if "\x00" in text:
            text = text.replace("\x00", "")

        # If after cleanup the content has control characters (excluding common
        # whitespace), it's likely binary or corrupted data
        if len(text) > 0:
            sample = text[:2000]
            # Only count C0/C1 control chars (0x00-0x08, 0x0E-0x1F, 0x7F-0x9F)
            # excluding tab, newline, carriage return
            control_chars = sum(
                1 for c in sample
                if (ord(c) < 0x09)
                or (0x0E <= ord(c) <= 0x1F)
                or (0x7F <= ord(c) <= 0x9F)
            )
            if control_chars / len(sample) > 0.05:
                return None

        return text if text.strip() else None

    async def extract_feed_articles(self, feed: Feed, db: AsyncSession) -> dict:
        result = await db.execute(
            select(Article).where(Article.feed_id == feed.id, Article.status == "pending")
        )
        articles = result.scalars().all()
        # Cache identifiers upfront to avoid lazy-load after rollback
        article_ids = [(a.id, a.url) for a in articles]

        total = len(article_ids)
        extracted = 0
        failed = 0
        errors: list[str] = []

        for article_id, article_url in article_ids:
            try:
                article = await db.get(Article, article_id)
                if article is None:
                    continue
                await self.extract_article(article, db)
                if article.status == "extracted":
                    extracted += 1
                elif article.status == "failed":
                    failed += 1
                    errors.append(f"Article {article_id} ({article_url}): download failed")
            except Exception as exc:
                await db.rollback()
                failed += 1
                errors.append(f"Article {article_id} ({article_url}): {exc}")
                logger.warning("article_extraction_error", article_id=article_id, error=str(exc))

        return {
            "feed_id": feed.id,
            "total": total,
            "extracted": extracted,
            "failed": failed,
            "errors": errors,
        }
