# app/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # For SQLAlchemy 2.0 style select
from typing import Optional, List # Import Optional and List
from . import models, schemas

async def get_card_by_scryfall_id(db: AsyncSession, scryfall_id: str) -> Optional[models.Card]:
    """
    Retrieve a card from the database by its Scryfall ID.
    """
    result = await db.execute(
        select(models.Card).filter(models.Card.scryfall_id == scryfall_id)
    )
    return result.scalars().first() # .scalars().first() gets a single object or None

async def get_card(db: AsyncSession, card_id: int) -> Optional[models.Card]:
    """
    Retrieve a card from the database by its primary key ID.
    """
    result = await db.execute(select(models.Card).filter(models.Card.id == card_id))
    return result.scalars().first()

async def get_cards(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.Card]: # Use List here
    """
    Retrieve a list of cards with pagination.
    """
    result = await db.execute(select(models.Card).offset(skip).limit(limit))
    return result.scalars().all()

async def create_card(db: AsyncSession, card: schemas.CardCreate) -> models.Card:
    """
    Create a new card in the database.
    """
    # Create a new SQLAlchemy model instance from the Pydantic schema data
    db_card = models.Card(**card.model_dump()) # Use model_dump() for Pydantic v2
    db.add(db_card)
    # The session commit is handled by the get_db dependency
    # We need to await refresh to get DB-generated values like id and date_added
    # However, since commit is handled by get_db, we might not need to refresh here
    # if the session is flushed before commit. For safety, let's assume we might need it
    # or rely on the session being committed by get_db.
    # For now, we'll add it and then rely on the commit in get_db.
    # The primary key and defaults will be populated after the flush/commit.
    await db.flush() # Ensure db_card gets its ID if it's a new object
    await db.refresh(db_card) # Refresh to get DB-generated values
    return db_card

# You will add more CRUD functions here:
# async def update_card(...)
# async def delete_card(...)
