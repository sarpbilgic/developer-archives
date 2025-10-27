"""add_gin_index_for_topics

Revision ID: e0bc7beba9b8
Revises: 95babcc757cb
Create Date: 2025-10-27 22:25:32.550193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  
from pgvector.sqlalchemy import Vector  

revision: str = 'e0bc7beba9b8'
down_revision: Union[str, Sequence[str], None] = '95babcc757cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add GIN index for array operations on topics column.
    """
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_projects_topics_gin 
        ON projects 
        USING GIN (topics);
    """)


def downgrade() -> None:
    """Remove GIN index from topics column."""
    op.execute("DROP INDEX IF EXISTS idx_projects_topics_gin;")
