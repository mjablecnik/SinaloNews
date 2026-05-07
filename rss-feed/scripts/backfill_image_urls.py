#!/usr/bin/env python3
"""One-time script to backfill image_url from feedparser_raw_entry for existing articles."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings  # noqa: E402
from src.services.parser_service import FeedParserService  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: E402


async def backfill():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionFactory() as session:
        from src.data.models import Article

        stmt = select(Article).where(
            Article.image_url.is_(None),
            Article.feedparser_raw_entry.is_not(None),
        )
        result = await session.execute(stmt)
        articles = result.scalars().all()

        print(f"Found {len(articles)} articles to process")
        updated = 0

        for article in articles:
            raw_entry = article.feedparser_raw_entry
            if not raw_entry or not isinstance(raw_entry, dict):
                continue

            image_url = FeedParserService._extract_image_url(raw_entry)
            if image_url:
                article.image_url = image_url
                updated += 1

        await session.commit()
        print(f"Updated {updated} articles with image URLs")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(backfill())
