"""Add formatted_text column to articles table.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("formatted_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "formatted_text")
