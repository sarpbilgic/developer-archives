# app/data_access/repositories/project_repository.py
# This layer is responsible for all write/update/delete operations to the database.
# It is the only part of the application that directly writes SQL or uses the ORM for mutations.

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from app.models.project import Project

class ProjectRepository:
    """
    Handles data persistence logic for the Project model.
    It abstracts away the direct database interaction from the service layer.
    """
    def __init__(self, session: AsyncSession):
        """
        Initializes the repository with an active database session.
        
        Args:
            session: An active AsyncSession for database communication.
        """
        self.session = session

    async def upsert(self, project: Project) -> Project:
        """
        Performs an "update or insert" operation for a Project.
        
        If a project with the same 'full_name' already exists, it updates the
        existing record. Otherwise, it inserts a new record. This is crucial for
        both the initial data backfill and for periodic updates.

        Args:
            project: The Project SQLModel object to be saved.

        Returns:
            The saved Project object, retrieved from the database to ensure it
            includes any database-generated values (like the ID).
        """
        # 1. Convert the SQLModel object into a dictionary.
        #    exclude_none=True removes None values (like id for new inserts)
        #    This ensures last_indexed_at (with default_factory) is included
        project_data = project.dict(exclude_none=True)

        # 2. Build the core 'INSERT' statement using SQLAlchemy's PostgreSQL dialect.
        insert_stmt = pg_insert(Project).values(**project_data)

        # 3. Define the 'ON CONFLICT' behavior.
        #    When a project with the same 'full_name' is found, we update its fields.
        #    We get the values to update from the 'excluded' property of the insert statement,
        #    which refers to the values we tried to insert.
        update_columns = {
            col.name: getattr(insert_stmt.excluded, col.name)
            for col in Project.__table__.columns
            if col.name not in ["id", "full_name"] # Never update the primary key or the unique constraint key
        }
        
        on_conflict_stmt = insert_stmt.on_conflict_do_update(
            index_elements=['full_name'], # The unique constraint to check for conflict
            set_=update_columns,
        )

        # 4. Execute the statement.
        await self.session.execute(on_conflict_stmt)
        await self.session.commit()

        # 5. After committing, we need to get the fresh object from the database
        #    to ensure all fields (like 'id' for new inserts) are correctly populated.
        #    This is a reliable pattern to get the final state of the record.
        statement = select(Project).where(Project.full_name == project.full_name)
        result = await self.session.execute(statement)
        saved_project = result.scalar_one()
        
        return saved_project