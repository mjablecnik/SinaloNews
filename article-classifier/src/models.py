from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Article(Base):
    """Read-only mapping to the rss-feed articles table."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(String(1000))
    url: Mapped[str | None] = mapped_column(String(2048))
    author: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    formatted_text: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str | None] = mapped_column(String(20))

    classification_result: Mapped["ClassificationResult | None"] = relationship(
        back_populates="article", uselist=False
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tags.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    parent: Mapped["Tag | None"] = relationship("Tag", remote_side="Tag.id")
    article_tags: Mapped[list["ArticleTag"]] = relationship(back_populates="tag")

    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_tag_parent_name"),)


class ClassificationResult(Base):
    __tablename__ = "classification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id"), unique=True, nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String(200))
    token_usage: Mapped[int | None] = mapped_column(Integer)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    classified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    article: Mapped["Article"] = relationship(back_populates="classification_result")
    article_tags: Mapped[list["ArticleTag"]] = relationship(
        back_populates="classification_result", cascade="all, delete-orphan"
    )

    __table_args__ = (CheckConstraint("importance_score >= 0 AND importance_score <= 10", name="ck_score_range"),)


class ArticleTag(Base):
    __tablename__ = "article_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    classification_result_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("classification_results.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    classification_result: Mapped["ClassificationResult"] = relationship(back_populates="article_tags")
    tag: Mapped["Tag"] = relationship(back_populates="article_tags")

    __table_args__ = (
        UniqueConstraint("classification_result_id", "tag_id", name="uq_article_tag"),
    )
