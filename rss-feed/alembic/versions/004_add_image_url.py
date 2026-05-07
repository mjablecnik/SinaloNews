"""Add image_url column to articles table.

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("image_url", sa.String(2048), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "image_url")
