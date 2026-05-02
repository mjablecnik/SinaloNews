"""unique article url globally

Revision ID: 002
Revises: 001
Create Date: 2026-05-02
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove duplicate articles (keep lowest id per url)
    op.execute("""
        DELETE FROM articles
        WHERE id NOT IN (
            SELECT MIN(id) FROM articles GROUP BY url
        )
    """)
    op.drop_constraint("uq_article_feed_url", "articles", type_="unique")
    op.create_unique_constraint("uq_article_url", "articles", ["url"])


def downgrade() -> None:
    op.drop_constraint("uq_article_url", "articles", type_="unique")
    op.create_unique_constraint("uq_article_feed_url", "articles", ["feed_id", "url"])
