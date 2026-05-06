"""initial

Revision ID: 001
Revises:
Create Date: 2026-05-06
"""
import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["parent_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "name", name="uq_tag_parent_name"),
    )

    op.create_table(
        "classification_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("importance_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(200), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("classified_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("importance_score >= 0 AND importance_score <= 10", name="ck_score_range"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", name="uq_classification_article"),
    )
    op.create_index("ix_classification_results_article_id", "classification_results", ["article_id"])
    op.create_index("ix_classification_results_classified_at", "classification_results", ["classified_at"])

    op.create_table(
        "article_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("classification_result_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["classification_result_id"], ["classification_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("classification_result_id", "tag_id", name="uq_article_tag"),
    )


def downgrade() -> None:
    op.drop_table("article_tags")
    op.drop_table("classification_results")
    op.drop_table("tags")
