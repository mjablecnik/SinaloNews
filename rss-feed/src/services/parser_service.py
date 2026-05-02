import asyncio
import json
from datetime import datetime
from urllib.parse import urlparse

import feedparser
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import Article, Feed
from src.services.rate_limiter import RateLimiter

logger = structlog.get_logger()


def _make_json_serializable(obj: object) -> object:
    """Recursively convert a feedparser object to a JSON-serializable structure."""
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_serializable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


class FeedParserService:
    def __init__(self, rate_limiter: RateLimiter, user_agent: str = "") -> None:
        self.rate_limiter = rate_limiter
        self.user_agent = user_agent

    async def parse_feed(self, feed: Feed, db: AsyncSession) -> list[Article]:
        domain = urlparse(feed.feed_url).netloc
        log = logger.bind(feed_id=feed.id, feed_url=feed.feed_url)

        await self.rate_limiter.acquire(domain)

        loop = asyncio.get_event_loop()
        kwargs: dict = {}
        if self.user_agent:
            kwargs["agent"] = self.user_agent

        parsed = await loop.run_in_executor(
            None, lambda: feedparser.parse(feed.feed_url, **kwargs)
        )

        if parsed.bozo and not parsed.entries:
            exc = parsed.get("bozo_exception")
            raise ValueError(f"Failed to parse feed {feed.feed_url}: {exc}")

        log.info("feed_fetched", entry_count=len(parsed.entries))

        new_articles: list[Article] = []

        for entry in parsed.entries:
            url = entry.get("link") or entry.get("id") or ""
            if not url:
                continue

            existing = await db.execute(
                select(Article).where(Article.url == url)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            published_at: datetime | None = None
            if entry.get("published_parsed"):
                try:
                    published_at = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            raw_entry = _make_json_serializable(dict(entry))
            try:
                json.dumps(raw_entry)
            except (TypeError, ValueError):
                raw_entry = {"_raw": str(entry)}

            article = Article(
                feed_id=feed.id,
                url=url,
                title=entry.get("title"),
                author=entry.get("author"),
                published_at=published_at,
                summary=entry.get("summary"),
                status="pending",
                feedparser_raw_entry=raw_entry,
            )
            db.add(article)
            try:
                await db.flush()
                new_articles.append(article)
                log.debug("article_created", url=url)
            except IntegrityError:
                await db.rollback()
                log.debug("article_already_exists", url=url)

        feed.last_parsed_at = datetime.utcnow()
        await db.commit()

        for article in new_articles:
            await db.refresh(article)

        log.info("feed_parsed", new_articles=len(new_articles))
        return new_articles
