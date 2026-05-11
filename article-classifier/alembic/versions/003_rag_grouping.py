"""rag-based grouping: needs_regeneration flag and full_article_indexed table

Revision ID: 003
Revises: 002
Create Date: 2026-05-11
"""
import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add needs_regeneration flag to article_groups
    op.add_column(
        "article_groups",
        sa.Column("needs_regeneration", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Create full_article_indexed tracking table
    op.create_table(
        "full_article_indexed",
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("article_id"),
    )


def downgrade() -> None:
    op.drop_table("full_article_indexed")
    op.drop_column("article_groups", "needs_regeneration")
