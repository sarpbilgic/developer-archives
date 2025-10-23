"""add_processing_status_to_projects

Revision ID: 95babcc757cb
Revises: faf9de66e450
Create Date: 2025-10-24 00:48:27.864337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # Bu satırı ekleyin
from pgvector.sqlalchemy import Vector  # Bu satırı ekleyin


# revision identifiers, used by Alembic.
revision: str = '95babcc757cb'
down_revision: Union[str, Sequence[str], None] = 'faf9de66e450'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add processing_status column with default value
    op.add_column('projects', 
        sa.Column('processing_status', 
                  sqlmodel.sql.sqltypes.AutoString(length=50), 
                  nullable=False, 
                  server_default='discovered')
    )
    
    # Update existing projects to 'completed' status (they already have embeddings)
    # New projects will use the default 'discovered'
    op.execute("""
        UPDATE projects 
        SET processing_status = 'completed' 
        WHERE project_embedding IS NOT NULL
    """)
    
    # Create index on processing_status for efficient queries
    op.create_index(op.f('ix_projects_processing_status'), 'projects', ['processing_status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove index first
    op.drop_index(op.f('ix_projects_processing_status'), table_name='projects')
    
    # Remove column
    op.drop_column('projects', 'processing_status')
