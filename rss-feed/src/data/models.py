from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.database import Base


class Website(Base):
    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discovery_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    feeds: Mapped[list["Feed"]] = relationship("Feed", back_populates="website", cascade="all, delete-orphan")


class Feed(Base):
    __tablename__ = "feeds"
    __table_args__ = (UniqueConstraint("website_id", "feed_url", name="uq_feed_website_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    website_id: Mapped[int] = mapped_column(Integer, ForeignKey("websites.id", ondelete="CASCADE"), nullable=False, index=True)
    feed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feed_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    last_parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    website: Mapped["Website"] = relationship("Website", back_populates="feeds")
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="feed", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("url", name="uq_article_url"),
        Index("ix_articles_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed_id: Mapped[int] = mapped_column(Integer, ForeignKey("feeds.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    formatted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    feedparser_raw_entry: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    feed: Mapped["Feed"] = relationship("Feed", back_populates="articles")
