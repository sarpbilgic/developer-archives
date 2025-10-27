"""add_ivfflat_index_for_embeddings

Revision ID: e1020321b4e3
Revises: 3c3824bea299
Create Date: 2025-10-18 15:03:24.371766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # Bu satırı ekleyin
from pgvector.sqlalchemy import Vector  # Bu satırı ekleyin


# revision identifiers, used by Alembic.
revision: str = 'e1020321b4e3'
down_revision: Union[str, Sequence[str], None] = '3c3824bea299'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create IVFFlat index for vector similarity search.
    
    # Create IVFFlat index with 'lists' parameter
    # lists = sqrt(row_count) is a good heuristic
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_embedding_ivfflat 
        ON projects 
        USING ivfflat (project_embedding vector_cosine_ops) 
        WITH (lists = 200);
    """)


def downgrade() -> None:
    """Remove IVFFlat index."""
    op.execute("DROP INDEX IF EXISTS idx_project_embedding_ivfflat;")

