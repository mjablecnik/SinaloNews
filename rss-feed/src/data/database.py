import ssl as ssl_module

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


class Base(DeclarativeBase):
    pass


# SSL context for cloud PostgreSQL providers
_connect_args: dict = {}
if settings.DATABASE_URL and ("neon.tech" in settings.DATABASE_URL or "supabase" in settings.DATABASE_URL):
    _ssl_context = ssl_module.create_default_context()
    _connect_args["ssl"] = _ssl_context

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=_connect_args)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
