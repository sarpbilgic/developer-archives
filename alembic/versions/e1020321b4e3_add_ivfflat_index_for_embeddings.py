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
    
    IVFFlat is memory-efficient (critical for 1GB RAM!) compared to HNSW:
    - HNSW: Fast but high memory (9KB per vector)
    - IVFFlat: Moderate speed, low memory (1-2KB per vector)
    
    For 75k repos:
    - HNSW: ~675 MB RAM (TOO MUCH for 1GB!)
    - IVFFlat: ~150 MB RAM (PERFECT!)
    """
    # Create IVFFlat index with 'lists' parameter
    # lists = sqrt(row_count) is a good heuristic
    # For 75k repos: sqrt(75000) ≈ 274
    # We use 100-300 lists for optimal performance
    
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_embedding_ivfflat 
        ON projects 
        USING ivfflat (project_embedding vector_cosine_ops) 
        WITH (lists = 200);
    """)
    
    # Note: After inserting data, you should run:
    # ANALYZE projects;
    # This helps PostgreSQL optimize the index usage


def downgrade() -> None:
    """Remove IVFFlat index."""
    op.execute("DROP INDEX IF EXISTS idx_project_embedding_ivfflat;")

# USAGE INSTRUCTIONS:
# 1. Run this migration: alembic upgrade head
# 2. After loading repos: psql -c "ANALYZE projects;"
# 3. In search queries, use: ORDER BY project_embedding <=> query_vector
