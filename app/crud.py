# app/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # For SQLAlchemy 2.0 style select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func # For now() in update
from typing import Optional, List, Dict, Any # Import Dict, Any for update_card if needed, though not directly used in this snippet
from . import models, schemas
from .security import get_password_hash

# --- User CRUD ---
async def get_user(db: AsyncSession, user_id: int) -> Optional[models.User]:
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    return result.scalars().first()

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[models.User]:
    result = await db.execute(select(models.User).filter(models.User.username == username))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: schemas.UserCreate) -> models.User:
    hashed_password = get_password_hash(user.password)
    db_user = models.User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(db_user)
    await db.flush()
    await db.refresh(db_user)
    return db_user

# --- CardDefinition CRUD ---
async def get_card_definition_by_scryfall_id(db: AsyncSession, scryfall_id: str) -> Optional[models.CardDefinition]:
    """
    Retrieve a card definition from the database by its Scryfall ID.
    """
    result = await db.execute(
        select(models.CardDefinition).filter(models.CardDefinition.scryfall_id == scryfall_id)
    )
    return result.scalars().first() # .scalars().first() gets a single object or None

async def get_card_definition(db: AsyncSession, card_definition_id: int) -> Optional[models.CardDefinition]:
    """
    Retrieve a card definition from the database by its primary key ID.
    """
    result = await db.execute(select(models.CardDefinition).filter(models.CardDefinition.id == card_definition_id))
    return result.scalars().first()

async def get_card_definitions(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.CardDefinition]:
    """
    Retrieve a list of card definitions with pagination.
    """
    result = await db.execute(select(models.CardDefinition).order_by(models.CardDefinition.id).offset(skip).limit(limit))
    return result.scalars().all()

async def create_card_definition(db: AsyncSession, card_def: schemas.CardDefinitionCreate) -> models.CardDefinition:
    """
    Create a new card definition in the database.
    This might be used if you fetch from Scryfall and want to cache it.
    """
    db_card_def = models.CardDefinition(**card_def.model_dump())
    db.add(db_card_def)
    await db.flush()
    await db.refresh(db_card_def)
    return db_card_def

# (update_card_definition and delete_card_definition can be added if needed for admin purposes)

# --- UserCollectionEntry CRUD ---
async def get_collection_entry(db: AsyncSession, user_id: int, collection_entry_id: int) -> Optional[models.UserCollectionEntry]:
    result = await db.execute(
        select(models.UserCollectionEntry)
        .filter(models.UserCollectionEntry.id == collection_entry_id, models.UserCollectionEntry.user_id == user_id)
        .options(selectinload(models.UserCollectionEntry.card_definition)) # Eager load card_definition
    )
    return result.scalars().first()

async def get_user_collection(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> List[models.UserCollectionEntry]:
    result = await db.execute(
        select(models.UserCollectionEntry)
        .filter(models.UserCollectionEntry.user_id == user_id)
        .order_by(models.UserCollectionEntry.id) # Or by card name, date added etc.
        .offset(skip)
        .limit(limit)
        .options(selectinload(models.UserCollectionEntry.card_definition)) # Eager load card_definition
    )
    return result.scalars().all()

async def add_card_to_collection(db: AsyncSession, user_id: int, entry_create: schemas.UserCollectionEntryCreate) -> models.UserCollectionEntry:
    # 1. Find or create the CardDefinition
    card_def = await get_card_definition_by_scryfall_id(db, entry_create.card_definition_scryfall_id)
    if not card_def:
        # Here you would typically fetch from Scryfall API and create the CardDefinition
        # For now, let's assume it must exist or raise an error / handle as per your design
        # For example, if you have a Scryfall proxy endpoint, you'd call it here.
        # This is a placeholder:
        raise ValueError(f"CardDefinition with Scryfall ID {entry_create.card_definition_scryfall_id} not found. Implement Scryfall fetch.")
        # card_def_data = schemas.CardDefinitionCreate(scryfall_id=entry_create.card_definition_scryfall_id, name="Fetched Name") # Populate with fetched data
        # card_def = await create_card_definition(db, card_def_data)

    # 2. Check if user already has this card (by card_definition_id) to update quantity, or create new entry
    # This example creates a new entry each time, or you can implement logic to update existing.
    # For simplicity, we'll create a new entry. You might want to find an existing entry for the same card_definition_id
    # and update quantities if it exists.

    db_collection_entry = models.UserCollectionEntry(
        user_id=user_id,
        card_definition_id=card_def.id,
        **entry_create.model_dump(exclude={"card_definition_scryfall_id"}) # Exclude the scryfall_id used for lookup
    )
    db.add(db_collection_entry)
    await db.flush()
    await db.refresh(db_collection_entry)
    # To include card_definition in the response, load it after refresh if not already loaded by relationship
    await db.refresh(db_collection_entry, attribute_names=['card_definition'])
    return db_collection_entry

async def update_collection_entry(db: AsyncSession, db_collection_entry: models.UserCollectionEntry, entry_update: schemas.UserCollectionEntryUpdate) -> models.UserCollectionEntry:
    """
    Update an existing UserCollectionEntry.
    """
    update_data = entry_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_collection_entry, key, value)
    
    if update_data:
        db_collection_entry.date_updated_in_collection = func.now()

    db.add(db_collection_entry)
    await db.flush()
    await db.refresh(db_collection_entry)
    await db.refresh(db_collection_entry, attribute_names=['card_definition'])
    return db_collection_entry

async def delete_collection_entry(db: AsyncSession, db_collection_entry: models.UserCollectionEntry) -> None:
    await db.delete(db_collection_entry)
    return None
