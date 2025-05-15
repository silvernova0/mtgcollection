# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from .core.config import settings # Import the settings

DATABASE_URL = settings.DATABASE_URL

# Create an asynchronous engine
# future=True enables 2.0 style usage which is recommended
engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# Create a sessionmaker for creating AsyncSession instances
# expire_on_commit=False prevents attributes from being expired after commit,
# which is useful in async contexts.
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, future=True
)

# Base class for declarative models
Base = declarative_base()

# Dependency to get a DB session
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit() # Commit transactions if all operations succeed
        except Exception:
            await session.rollback() # Rollback in case of an error
            raise
        finally:
            await session.close()
