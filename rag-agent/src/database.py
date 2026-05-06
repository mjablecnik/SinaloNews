import ssl as ssl_module
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

# asyncpg requires ssl context passed via connect_args for SSL connections
_connect_args: dict = {}
if settings.DATABASE_URL and ("neon.tech" in settings.DATABASE_URL or "supabase" in settings.DATABASE_URL):
    _ssl_context = ssl_module.create_default_context()
    _connect_args["ssl"] = _ssl_context

engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        yield session
