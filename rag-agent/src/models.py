from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Article(Base):
    """Read-only mapping to the existing rss-feed articles table."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(1000))
    url: Mapped[str | None] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20))


class IndexedArticle(Base):
    """Tracks which articles have been indexed to prevent duplicate processing."""

    __tablename__ = "indexed_articles"

    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    indexed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
