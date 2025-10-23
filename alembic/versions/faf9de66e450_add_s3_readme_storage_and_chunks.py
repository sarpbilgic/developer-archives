"""add_s3_readme_storage_and_chunks

Revision ID: faf9de66e450
Revises: e1020321b4e3
Create Date: 2025-10-21 00:27:38.404784

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # Bu satırı ekleyin
from pgvector.sqlalchemy import Vector  # Bu satırı ekleyin


# revision identifiers, used by Alembic.
revision: str = 'faf9de66e450'
down_revision: Union[str, Sequence[str], None] = 'e1020321b4e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema to use S3-based README storage (SINGLE VECTOR).
    
    Changes:
    1. Add readme_s3_key and readme_word_count to projects table
    2. Keep readme_content for backward compatibility (can drop manually later)
    
    NO readme_chunks table - using single-vector approach for simplicity!
    """
    # Add new columns to projects table for S3 storage
    op.add_column('projects', sa.Column('readme_s3_key', sa.String(length=500), nullable=True))
    op.add_column('projects', sa.Column('readme_word_count', sa.Integer(), nullable=True))
    
    # Create index on readme_s3_key for efficient lookups
    op.create_index('ix_projects_readme_s3_key', 'projects', ['readme_s3_key'])
    
    # NOTE: readme_content column is kept for backward compatibility
    # You can drop it manually later after verifying all READMEs are in S3:
    # ALTER TABLE projects DROP COLUMN readme_content;


def downgrade() -> None:
    """
    Downgrade schema back to DB-only README storage.
    
    Removes S3 fields.
    """
    # Remove S3-related columns
    op.drop_index('ix_projects_readme_s3_key', table_name='projects')
    op.drop_column('projects', 'readme_word_count')
    op.drop_column('projects', 'readme_s3_key')
