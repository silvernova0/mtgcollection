# app/main.py
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional  # <-- Make sure this is present
from datetime import timedelta

from . import models, schemas, crud, security # Import security
from .database import engine, get_db
from .core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

async def create_db_and_tables():
    async with engine.begin() as conn:
        # await conn.run_sync(models.Base.metadata.drop_all) # Optional: drop tables for clean slate
        # Be careful with drop_all in production!
        await conn.run_sync(models.Base.metadata.create_all)

app = FastAPI(
    title="MTG Collection Tracker API",
    description="API for managing a Magic: The Gathering card collection.",
    version="0.1.0",
    on_startup=[create_db_and_tables]
)

# --- Helper Dependency for Current User ---
async def get_current_active_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> models.User:
    try:
        token_data = await security.get_current_user_token_data(token)
    except JWTError: # Re-raise as HTTPException
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await crud.get_user_by_username(db, username=token_data.username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate user or user inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# --- Authentication Endpoints ---
@app.post("/auth/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
async def register_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    # Add email check if email is mandatory and unique
    # db_user_email = await crud.get_user_by_email(db, email=user.email)
    # if db_user_email:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return await crud.create_user(db=db, user=user)

@app.post("/auth/token", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_username(db, username=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password) or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password or user inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    return current_user

# --- Root Endpoint ---
@app.get("/")
async def read_root():
    return {"message": "Welcome to the MTG Collection Tracker API!"}

# --- Card Definition Endpoints (Example: for admin or internal caching) ---
# These might be admin-only or used internally when fetching from Scryfall.
# For simplicity, keeping them open for now.
@app.post("/card-definitions/", response_model=schemas.CardDefinition, status_code=status.HTTP_201_CREATED)
async def create_new_card_definition(
    card_def: schemas.CardDefinitionCreate, db: AsyncSession = Depends(get_db)
):
    db_card_def = await crud.get_card_definition_by_scryfall_id(db=db, scryfall_id=card_def.scryfall_id)
    if db_card_def:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Card Definition with this Scryfall ID already exists")
    return await crud.create_card_definition(db=db, card_def=card_def)

@app.get("/card-definitions/", response_model=List[schemas.CardDefinition])
async def read_card_definitions_list(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    type_line: Optional[str] = None,
    set_code: Optional[str] = None,
    # Add other searchable fields as query parameters here
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a list of card definitions.
    Supports pagination and filtering by name, type_line, set_code, etc.
    Providing a 'name' will list all printings of cards matching that name.
    """
    card_defs = await crud.get_card_definitions(
        db=db, skip=skip, limit=limit, name=name, type_line=type_line, set_code=set_code
    )
    return card_defs

@app.get("/card-definitions/{card_def_id}", response_model=schemas.CardDefinition)
async def read_card_definition(card_def_id: int, db: AsyncSession = Depends(get_db)):
    db_card_def = await crud.get_card_definition(db=db, card_definition_id=card_def_id)
    if db_card_def is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card Definition not found")
    return db_card_def

# --- User Collection Endpoints ---
@app.post("/collection/cards/", response_model=schemas.UserCollectionEntry, status_code=status.HTTP_201_CREATED)
async def add_card_to_my_collection(
    entry_create: schemas.UserCollectionEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Add a card to the authenticated user's collection.
    The backend will try to find an existing CardDefinition by scryfall_id,
    or you'd extend this to fetch from Scryfall and create the CardDefinition if new.
    """
    try:
        return await crud.add_card_to_collection(db=db, user_id=current_user.id, entry_create=entry_create)
    except ValueError as e: # Catch specific error from CRUD if CardDefinition not found
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/collection/cards/", response_model=List[schemas.UserCollectionEntry])
async def read_my_collection(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    collection = await crud.get_user_collection(db=db, user_id=current_user.id, skip=skip, limit=limit)
    return collection

@app.get("/collection/cards/{collection_entry_id}", response_model=schemas.UserCollectionEntry)
async def read_my_collection_entry(
    collection_entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    db_entry = await crud.get_collection_entry(db=db, user_id=current_user.id, collection_entry_id=collection_entry_id)
    if db_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection entry not found")
    return db_entry

@app.put("/collection/cards/{collection_entry_id}", response_model=schemas.UserCollectionEntry)
async def update_my_collection_entry(
    collection_entry_id: int,
    entry_update: schemas.UserCollectionEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    db_entry = await crud.get_collection_entry(db=db, user_id=current_user.id, collection_entry_id=collection_entry_id)
    if db_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection entry not found")
    return await crud.update_collection_entry(db=db, db_collection_entry=db_entry, entry_update=entry_update)

@app.delete("/collection/cards/{collection_entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_collection_entry(
    collection_entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    db_entry = await crud.get_collection_entry(db=db, user_id=current_user.id, collection_entry_id=collection_entry_id)
    if db_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection entry not found")
    await crud.delete_collection_entry(db=db, db_collection_entry=db_entry)
    return None

# --- Scryfall Proxy Endpoint (Example) ---
@app.get("/scryfall/search")
async def search_scryfall_cards(q: str, db: AsyncSession = Depends(get_db)): # Add db if you want to cache results
    """
    Proxy for Scryfall card search.
    Example: /scryfall/search?q=name:"Sol Ring"
    """
    # You'll need an HTTP client like httpx for this
    # import httpx
    # async with httpx.AsyncClient() as client:
    #     try:
    #         response = await client.get(f"https://api.scryfall.com/cards/search?q={q}")
    #         response.raise_for_status() # Raise an exception for bad status codes
    #         # Optionally, cache CardDefinition data here from the response
    #         return response.json()
    #     except httpx.HTTPStatusError as e:
    #         raise HTTPException(status_code=e.response.status_code, detail=f"Error from Scryfall: {e.response.text}")
    #     except httpx.RequestError as e:
    #         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not connect to Scryfall: {str(e)}")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Scryfall proxy not fully implemented yet. Add httpx.")

# --- Deck Management Endpoints ---
@app.post("/decks/", response_model=schemas.Deck, status_code=status.HTTP_201_CREATED)
async def create_new_deck_for_user(
    deck_create: schemas.DeckCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new deck for the authenticated user."""
    deck = await crud.create_deck(db=db, user_id=current_user.id, deck_create=deck_create)
    # The created deck will be empty initially, cards are added via another endpoint.
    # To return deck_entries, ensure your Deck schema and CRUD operation populate it.
    # For now, it will return the deck without entries as per current Deck schema.
    # If you want to return entries, you might need to adjust the Deck schema or how crud.create_deck works.
    # The current Deck schema expects deck_entries: List[DeckEntry] = []
    return deck

@app.get("/decks/", response_model=List[schemas.Deck])
async def read_user_decks(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Retrieve decks for the authenticated user."""
    decks = await crud.get_user_decks(db=db, user_id=current_user.id, skip=skip, limit=limit)
    return decks

@app.get("/decks/{deck_id}", response_model=schemas.Deck)
async def read_single_deck(
    deck_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Retrieve a specific deck owned by the authenticated user."""
    deck = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id)
    if deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")
    return deck

@app.put("/decks/{deck_id}", response_model=schemas.Deck)
async def update_existing_deck(
    deck_id: int,
    deck_update: schemas.DeckUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a deck's details (name, description, format)."""
    db_deck = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id) # Ensure user owns the deck
    if db_deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")
    return await crud.update_deck(db=db, db_deck=db_deck, deck_update=deck_update)

@app.delete("/decks/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_deck(
    deck_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Delete a deck owned by the authenticated user."""
    db_deck = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id)
    if db_deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")
    await crud.delete_deck(db=db, db_deck=db_deck)
    return None

# --- Deck Card Management Endpoints ---
@app.post("/decks/{deck_id}/cards/", response_model=schemas.DeckEntry, status_code=status.HTTP_201_CREATED)
async def add_card_to_specific_deck(
    deck_id: int,
    deck_entry_create: schemas.DeckEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Add a card to a specific deck owned by the user."""
    # First, verify the deck exists and belongs to the user
    deck_model = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id) # Fetch the full deck model
    if deck_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")
    try:
        return await crud.add_card_to_deck(db=db, deck_model=deck_model, deck_entry_create=deck_entry_create)
    except ValueError as e: # From crud if CardDefinition not found
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# You would also add endpoints for:
# - PUT /decks/{deck_id}/cards/{deck_entry_id} (Update card quantity/role in deck)
# - DELETE /decks/{deck_id}/cards/{deck_entry_id} (Remove a card from a deck)
