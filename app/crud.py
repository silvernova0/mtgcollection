# app/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # For SQLAlchemy 2.0 style select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func # For now() in update
from typing import Optional, List, Dict, Any # Import Dict, Any for update_card if needed, though not directly used in this snippet
import asyncio # For potential concurrent image downloads
from . import models, schemas
from .security import get_password_hash
import httpx # Moved import to top level

async def _fetch_and_store_card_definition_from_scryfall(db: AsyncSession, scryfall_id: str) -> Optional[models.CardDefinition]:
    """
    Fetches card data from Scryfall API by Scryfall ID, stores it as a CardDefinition,
    and returns the SQLAlchemy model instance. Includes on-the-fly image downloading.
    Returns None if the card is not found on Scryfall or an error occurs.
    """
    # Helper for on-the-fly image download
    # Renamed to avoid potential conflict if this helper is moved out or reused.

    async def download_image_data_internal(client: httpx.AsyncClient, url: Optional[str]) -> Optional[bytes]:
        if not url:
            return None
        try:
            # Simplified download, no complex retries like in populate_cards.py for this on-the-fly fetch
            img_response = await client.get(url, timeout=10) # Shorter timeout for on-the-fly
            img_response.raise_for_status()
            return img_response.content
        except Exception as img_e:
            print(f"Failed to download image on-the-fly from {url}: {img_e}")
            return None

    scryfall_api_url = f"https://api.scryfall.com/cards/{scryfall_id}"
    # print(f"Attempting to fetch from Scryfall: {scryfall_api_url}") # For debugging

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(scryfall_api_url)
            response.raise_for_status() # Raises an exception for 4XX/5XX responses
            scryfall_data = response.json()
            image_uris = scryfall_data.get("image_uris", {})

            # Directly prepare data for the model, including image_data fields
            card_def_model_data = {
                "scryfall_id": scryfall_data.get("id"),
                "name": scryfall_data.get("name"),
                "set_code": scryfall_data.get("set"),
                "collector_number": scryfall_data.get("collector_number"),
                "legalities": scryfall_data.get("legalities"),
                "image_uri_small": image_uris.get("small"),
                "image_uri_normal": image_uris.get("normal"),
                "image_uri_large": image_uris.get("large"),
                "image_uri_art_crop": image_uris.get("art_crop"),
                "image_uri_border_crop": image_uris.get("border_crop"),
                "type_line": scryfall_data.get("type_line"),
                "image_data_small": None, # Initialize
                "image_data_normal": None,
                "image_data_large": None,
            }
            
            if not card_def_model_data["scryfall_id"] or not card_def_model_data["name"]:
                print(f"Scryfall data for {scryfall_id} missing essential fields (id or name). Will not store.")
                return None

            # Attempt to download images on-the-fly
            if card_def_model_data["image_uri_small"]:
                card_def_model_data["image_data_small"] = await download_image_data_internal(client, card_def_model_data["image_uri_small"])
            if card_def_model_data["image_uri_normal"]:
                card_def_model_data["image_data_normal"] = await download_image_data_internal(client, card_def_model_data["image_uri_normal"]) # Corrected typo
            if card_def_model_data["image_uri_large"]: # Ensure large image download is attempted
                card_def_model_data["image_data_large"] = await download_image_data_internal(client, card_def_model_data["image_uri_large"])

            db_card_def = models.CardDefinition(**card_def_model_data)
            db.add(db_card_def)
            await db.flush()
            await db.refresh(db_card_def)
            print(f"Successfully fetched and stored CardDefinition for {scryfall_id} ('{card_def_model_data['name']}') from Scryfall.")
            return db_card_def

    except httpx.HTTPStatusError as e:
        # Log more details from the HTTPStatusError
        error_detail = f"status_code={e.response.status_code}"
        if e.request:
            error_detail += f", url={e.request.url}"
        print(f"Scryfall API error for {scryfall_id}: {error_detail}. Response: {e.response.text[:200] if e.response else 'N/A'}")
        return None
    except httpx.RequestError as e:
        print(f"Request error for Scryfall API {scryfall_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching/storing Scryfall card {scryfall_id}: {e}")
        return None

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

async def get_card_definitions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    type_line: Optional[str] = None,
    set_code: Optional[str] = None
    # Add other searchable fields as parameters here
) -> List[models.CardDefinition]:
    """
    Retrieve a list of card definitions with pagination and optional filters.
    - If 'name' is provided, it will list all printings of that card.
    - Other fields can be used for more specific filtering.
    """
    query = select(models.CardDefinition)
    if name:
        query = query.filter(models.CardDefinition.name.ilike(f"%{name}%"))
    if type_line:
        query = query.filter(models.CardDefinition.type_line.ilike(f"%{type_line}%"))
    if set_code:
        query = query.filter(models.CardDefinition.set_code.ilike(f"%{set_code}%"))
    # Add more filters for other fields as needed

    query = query.order_by(models.CardDefinition.name, models.CardDefinition.set_code, models.CardDefinition.collector_number).offset(skip).limit(limit)
    result = await db.execute(query)
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
        card_def = await _fetch_and_store_card_definition_from_scryfall(db, entry_create.card_definition_scryfall_id)
        if not card_def:
            raise ValueError(f"Could not find or fetch CardDefinition with Scryfall ID {entry_create.card_definition_scryfall_id} from Scryfall.")

    # 2. Check if an entry for this card already exists for the user
    stmt = select(models.UserCollectionEntry).filter_by(
        user_id=user_id, 
        card_definition_id=card_def.id,
        # You might also want to filter by condition, language if you treat these as distinct entries
        # For this example, we assume same card_definition_id means it's the same conceptual entry.
    )
    result = await db.execute(stmt)
    db_collection_entry = result.scalars().first()

    if db_collection_entry:
        # Update existing entry
        update_data = entry_create.model_dump(exclude={"card_definition_scryfall_id"}, exclude_unset=True)
        if 'quantity_normal' in update_data:
            db_collection_entry.quantity_normal += update_data['quantity_normal'] # Increment
        if 'quantity_foil' in update_data:
            db_collection_entry.quantity_foil += update_data['quantity_foil'] # Increment
        
        # For other fields, you might want to overwrite or have specific logic
        if 'condition' in update_data: db_collection_entry.condition = update_data['condition']
        if 'language' in update_data: db_collection_entry.language = update_data['language']
        if 'notes' in update_data: db_collection_entry.notes = update_data['notes']
        
        db_collection_entry.date_updated_in_collection = func.now() # Explicitly set update timestamp
    else:
        # Create new entry
        db_collection_entry = models.UserCollectionEntry(
            user_id=user_id,
            card_definition_id=card_def.id,
            **entry_create.model_dump(exclude={"card_definition_scryfall_id"})
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

# --- Deck CRUD ---
async def create_deck(db: AsyncSession, user_id: int, deck_create: schemas.DeckCreate) -> models.Deck:
    db_deck = models.Deck(**deck_create.model_dump(), user_id=user_id)
    db.add(db_deck)
    await db.flush()
    await db.refresh(db_deck)
    return db_deck

async def get_deck(db: AsyncSession, user_id: int, deck_id: int) -> Optional[models.Deck]:
    result = await db.execute(
        select(models.Deck)
        .filter(models.Deck.id == deck_id, models.Deck.user_id == user_id)
        .options(selectinload(models.Deck.deck_entries).selectinload(models.DeckEntry.card_definition))
    )
    return result.scalars().first()

async def get_user_decks(db: AsyncSession, user_id: int, skip: int = 0, limit: int = 100) -> List[models.Deck]:
    result = await db.execute(
        select(models.Deck)
        .filter(models.Deck.user_id == user_id)
        .order_by(models.Deck.name)
        .offset(skip)
        .limit(limit)
        .options(selectinload(models.Deck.deck_entries).selectinload(models.DeckEntry.card_definition)) # Optionally load entries here or make it separate
    )
    return result.scalars().all()

async def update_deck(db: AsyncSession, db_deck: models.Deck, deck_update: schemas.DeckUpdate) -> models.Deck:
    update_data = deck_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_deck, key, value)
    if update_data:
        db_deck.date_updated = func.now()
    db.add(db_deck)
    await db.flush()
    await db.refresh(db_deck)
    # Refresh relationships if they might have changed or if needed for the response
    await db.refresh(db_deck, attribute_names=['deck_entries'])
    for entry in db_deck.deck_entries: # Ensure card_definitions within entries are loaded
        await db.refresh(entry, attribute_names=['card_definition'])
    return db_deck

async def delete_deck(db: AsyncSession, db_deck: models.Deck) -> None:
    await db.delete(db_deck)
    return None

# --- DeckEntry CRUD ---
async def add_card_to_deck(db: AsyncSession, deck_model: models.Deck, deck_entry_create: schemas.DeckEntryCreate) -> models.DeckEntry:
    """
    Adds a card to a given deck, performing legality checks if the deck has a format.
    - deck_model: The SQLAlchemy model instance of the deck.
    - deck_entry_create: Pydantic schema with card and quantity details.
    """
    card_def = await get_card_definition_by_scryfall_id(db, deck_entry_create.card_definition_scryfall_id)
    if not card_def:
        card_def = await _fetch_and_store_card_definition_from_scryfall(db, deck_entry_create.card_definition_scryfall_id)
        if not card_def:
            raise ValueError(f"Could not find or fetch CardDefinition with Scryfall ID {deck_entry_create.card_definition_scryfall_id} from Scryfall.")

    # Perform legality check if the deck has a format specified
    if deck_model.format:
        if not card_def.legalities:
            # This case implies legalities were not fetched/cached for this card.
            # For a robust system, you might attempt a Scryfall fetch here for legalities.
            raise ValueError(f"Legality information not available for card '{card_def.name}'. Please ensure card data is up to date.")
        
        card_legality_in_format = card_def.legalities.get(deck_model.format.lower()) # Ensure format comparison is case-insensitive
        if card_legality_in_format != "legal":
            raise ValueError(f"Card '{card_def.name}' is not legal in the '{deck_model.format}' format (Status: {card_legality_in_format or 'unknown'}).")

    # Check if this card (with the same sideboard status) already exists in the deck.
    stmt = select(models.DeckEntry).filter_by(
        deck_id=deck_model.id,
        card_definition_id=card_def.id,
        is_sideboard=deck_entry_create.is_sideboard 
        # is_commander might also be part of the uniqueness if a card can be both commander and in the 99 (though unusual)
    )
    result = await db.execute(stmt)
    db_deck_entry = result.scalars().first()

    if db_deck_entry:
        # Update quantity of existing entry
        db_deck_entry.quantity += deck_entry_create.quantity
        # Potentially update is_commander if that's being changed for an existing entry
        if deck_entry_create.is_commander is not None: # Check if it's explicitly passed
             db_deck_entry.is_commander = deck_entry_create.is_commander
    else:
        # Create new entry
        db_deck_entry = models.DeckEntry(
            deck_id=deck_model.id,
            card_definition_id=card_def.id,
            **deck_entry_create.model_dump(exclude={"card_definition_scryfall_id"})
        )
        db.add(db_deck_entry)
    await db.flush()
    await db.refresh(db_deck_entry)
    await db.refresh(db_deck_entry, attribute_names=['card_definition']) # Ensure card_definition is loaded
    return db_deck_entry

async def get_deck_entry(db: AsyncSession, deck_entry_id: int) -> Optional[models.DeckEntry]:
    # Note: You might want to ensure this deck_entry_id belongs to a deck owned by the current user.
    # This would require joining with Deck and checking user_id, or passing deck_id and user_id.
    result = await db.execute(
        select(models.DeckEntry).filter(models.DeckEntry.id == deck_entry_id)
        .options(selectinload(models.DeckEntry.card_definition))
    )
    return result.scalars().first()

async def update_deck_entry(db: AsyncSession, db_deck_entry: models.DeckEntry, entry_update: schemas.DeckEntryUpdate) -> models.DeckEntry:
    update_data = entry_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_deck_entry, key, value)
    db.add(db_deck_entry) # Add to session to track changes
    await db.flush()
    await db.refresh(db_deck_entry)
    await db.refresh(db_deck_entry, attribute_names=['card_definition'])
    return db_deck_entry

async def remove_card_from_deck(db: AsyncSession, db_deck_entry: models.DeckEntry) -> None:
    await db.delete(db_deck_entry)
    return None
