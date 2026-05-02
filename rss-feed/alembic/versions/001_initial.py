"""initial

Revision ID: 001
Revises:
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "websites",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_discovery_at", sa.DateTime(), nullable=True),
        sa.Column("discovery_status", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_websites_domain", "websites", ["domain"])

    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("website_id", sa.Integer(), nullable=False),
        sa.Column("feed_url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("feed_type", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_parsed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["website_id"], ["websites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("website_id", "feed_url", name="uq_feed_website_url"),
    )
    op.create_index("ix_feeds_website_id", "feeds", ["website_id"])

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(1000), nullable=True),
        sa.Column("author", sa.String(500), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("original_html", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("feedparser_raw_entry", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["feed_id"], ["feeds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feed_id", "url", name="uq_article_feed_url"),
    )
    op.create_index("ix_articles_feed_id", "articles", ["feed_id"])
    op.create_index("ix_articles_status", "articles", ["status"])


def downgrade() -> None:
    op.drop_table("articles")
    op.drop_table("feeds")
    op.drop_table("websites")
