#!/usr/bin/env python3
"""One-time script to clear original_html column for all existing articles."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings  # noqa: E402

from sqlalchemy import update  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: E402


async def clear_html():
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionFactory() as session:
        from src.data.models import Article

        stmt = update(Article).where(
            Article.original_html.is_not(None),
        ).values(original_html=None)

        result = await session.execute(stmt)
        await session.commit()

        print(f"Cleared original_html for {result.rowcount} articles")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(clear_html())
