# app/main.py
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Path # Import Query, Request, and Path
from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware
from fastapi.responses import Response # Added for serving image data
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import timedelta

from . import models, schemas, crud, security # Import security
from .database import engine, get_db
from .core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
from enum import Enum # Added for StoredImageSize

async def create_db_and_tables():
    async with engine.begin() as conn:
        # await conn.run_sync(models.Base.metadata.drop_all) # Optional: drop tables for clean slate
        # Be careful with drop_all in production!
        await conn.run_sync(models.Base.metadata.create_all)

app = FastAPI(
    title="MTG Collection Tracker API",
    description="API for managing a Magic: The Gathering card collection.",
    version="0.1.0",
    on_startup=[create_db_and_tables],
)

# --- CORS Middleware ---
# Origins that are allowed to make requests to this API.
# You should update this list with the actual origin of your frontend application.
# For example, if your frontend runs on http://localhost:3000, add that.
# Using ["*"] allows all origins, which is okay for development but might be too permissive for production.
origins = [
    "http://localhost",         # If frontend is served from root localhost
    "http://localhost:3000",    # Common port for React dev servers
    "http://localhost:5173",    # Common port for Vite dev servers
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # List of origins that are allowed to make requests
    allow_credentials=True,      # Allow cookies to be included in requests
    allow_methods=["*"],         # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],         # Allow all headers
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
    request: Request, # Inject Request
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
    
    response_cards: List[schemas.CardDefinition] = []
    for db_card in card_defs: # Iterate over the correct variable 'card_defs'
        pydantic_card = schemas.CardDefinition.from_orm(db_card)
        if db_card.image_data_small:
            pydantic_card.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card.scryfall_id, size='small'))
        if db_card.image_data_normal:
            pydantic_card.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card.scryfall_id, size='normal'))
        if db_card.image_data_large:
            pydantic_card.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card.scryfall_id, size='large'))
        response_cards.append(pydantic_card)
    return response_cards

@app.get("/card-definitions/{card_def_id}", response_model=schemas.CardDefinition)
async def read_card_definition(
    card_def_id: int,
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db)
):
    db_card_def = await crud.get_card_definition(db=db, card_definition_id=card_def_id)
    if db_card_def is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card Definition not found")
    
    pydantic_card = schemas.CardDefinition.from_orm(db_card_def)
    if db_card_def.image_data_small:
        pydantic_card.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
    if db_card_def.image_data_normal:
        pydantic_card.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
    if db_card_def.image_data_large:
        pydantic_card.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
    return pydantic_card

# --- Card Search Endpoint (as requested by frontend) ---
@app.get("/cards/search", response_model=List[schemas.CardDefinition])
async def search_card_definitions_by_name(
    request: Request, # Inject Request
    name: str = Query(..., min_length=1, description="Card name to search for"),
    skip: int = 0,
    limit: int = 20, # Default limit for search results
    db: AsyncSession = Depends(get_db)
):
    """
    Search for Magic: The Gathering card definitions by name.
    This endpoint is specifically for the frontend's /cards/search path.
    """
    # Uses the existing crud.get_card_definitions function
    card_defs_models = await crud.get_card_definitions(
        db=db, skip=skip, limit=limit, name=name
        # You can add other parameters like type_line, set_code if the frontend sends them
    )
    # Standard practice is to return an empty list if no results are found,
    # rather than a 404, as the endpoint itself was found and processed the query.
    response_cards: List[schemas.CardDefinition] = []
    for db_card in card_defs_models:
        pydantic_card = schemas.CardDefinition.from_orm(db_card)
        if db_card.image_data_small: # Check if image data exists before creating URL
            pydantic_card.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card.scryfall_id, size='small'))
        if db_card.image_data_normal:
            pydantic_card.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card.scryfall_id, size='normal'))
        if db_card.image_data_large:
            pydantic_card.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card.scryfall_id, size='large'))
        response_cards.append(pydantic_card)
    return response_cards

# --- Card Image Endpoint ---
class StoredImageSize(str, Enum):
    """
    Represents the image sizes for which binary data is stored in the database
    by the populate_cards.py script.
    """
    small = "small"
    normal = "normal"
    large = "large"

@app.get(
    "/cards/{scryfall_id}/image/{size}", # MODIFIED: size is now a path parameter
    responses={
        200: {
            "content": {"image/jpeg": {}}, # Assuming images are JPEGs
            "description": "The card image.",
        },
        404: {"description": "Card or image data not found"},
        400: {"description": "Invalid image size requested"},
    },
    summary="Get Card Image Data",
    description="Serves the stored binary image data for a card. "
                "Currently supports 'small', 'normal', and 'large' sizes "
                "and assumes JPEG format.",
    tags=["Cards"], # Added a tag for better organization in API docs
    name="get_card_image_data"  # <--- ADD THIS NAME
)
async def get_card_image_data(
    scryfall_id: str = Path(..., description="The Scryfall ID of the card."), # ADDED: Path for scryfall_id
    size: StoredImageSize = Path( # MODIFIED: size is now a Path parameter
        ..., # Make size a required path parameter
        description="The desired image size (small, normal, or large)."
    ),
    db: AsyncSession = Depends(get_db),
):

    card = await crud.get_card_definition_by_scryfall_id(db, scryfall_id=scryfall_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    image_data_column_name = f"image_data_{size.value}"
    image_data: bytes | None = getattr(card, image_data_column_name, None)

    if not image_data:
        raise HTTPException(status_code=404, detail=f"Image data for size '{size.value}' not found for card {scryfall_id}.")

    return Response(content=image_data, media_type="image/jpeg")

# --- User Collection Endpoints ---
@app.post("/collection/cards/", response_model=schemas.UserCollectionEntry, status_code=status.HTTP_201_CREATED)
async def add_card_to_my_collection(
    entry_create: schemas.UserCollectionEntryCreate,
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Add a card to the authenticated user's collection.
    """
    try:
        db_entry = await crud.add_card_to_collection(db=db, user_id=current_user.id, entry_create=entry_create)
        pydantic_entry = schemas.UserCollectionEntry.from_orm(db_entry)
        if db_entry.card_definition:
            db_card_def = db_entry.card_definition
            if db_card_def.image_data_small:
                pydantic_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
            if db_card_def.image_data_normal:
                pydantic_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
            if db_card_def.image_data_large:
                pydantic_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
        return pydantic_entry
    except ValueError as e: # Catch specific error from CRUD if CardDefinition not found
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/collection/cards/", response_model=List[schemas.UserCollectionEntry])
async def read_my_collection(
    request: Request, # Inject Request
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    db_collection_entries = await crud.get_user_collection(db=db, user_id=current_user.id, skip=skip, limit=limit)
    
    response_entries: List[schemas.UserCollectionEntry] = []
    for db_entry in db_collection_entries:
        pydantic_entry = schemas.UserCollectionEntry.from_orm(db_entry)
        if db_entry.card_definition: # Ensure card_definition exists
            db_card_def = db_entry.card_definition 
            if db_card_def.image_data_small:
                pydantic_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
            if db_card_def.image_data_normal:
                pydantic_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
            if db_card_def.image_data_large:
                pydantic_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
        response_entries.append(pydantic_entry)
    return response_entries

@app.get("/collection/cards/{collection_entry_id}", response_model=schemas.UserCollectionEntry)
async def read_my_collection_entry(
    collection_entry_id: int,
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    db_entry = await crud.get_collection_entry(db=db, user_id=current_user.id, collection_entry_id=collection_entry_id)
    if db_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection entry not found")
    
    pydantic_entry = schemas.UserCollectionEntry.from_orm(db_entry)
    if db_entry.card_definition:
        db_card_def = db_entry.card_definition
        if db_card_def.image_data_small:
            pydantic_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
        if db_card_def.image_data_normal:
            pydantic_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
        if db_card_def.image_data_large:
            pydantic_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
    return pydantic_entry

@app.put("/collection/cards/{collection_entry_id}", response_model=schemas.UserCollectionEntry)
async def update_my_collection_entry(
    collection_entry_id: int,
    entry_update: schemas.UserCollectionEntryUpdate,
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    db_entry = await crud.get_collection_entry(db=db, user_id=current_user.id, collection_entry_id=collection_entry_id)
    if db_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection entry not found")
    updated_db_entry = await crud.update_collection_entry(db=db, db_collection_entry=db_entry, entry_update=entry_update)
    
    pydantic_entry = schemas.UserCollectionEntry.from_orm(updated_db_entry)
    if updated_db_entry.card_definition:
        db_card_def = updated_db_entry.card_definition
        if db_card_def.image_data_small:
            pydantic_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
        if db_card_def.image_data_normal:
            pydantic_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
        if db_card_def.image_data_large:
            pydantic_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
    return pydantic_entry

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
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new deck for the authenticated user."""
    db_deck = await crud.create_deck(db=db, user_id=current_user.id, deck_create=deck_create)
    # Even if deck_entries is empty, we convert to Pydantic schema
    pydantic_deck = schemas.Deck.from_orm(db_deck)
    # No need to iterate pydantic_deck.deck_entries here as it will be empty upon creation
    return pydantic_deck

@app.get("/decks/", response_model=List[schemas.Deck])
async def read_user_decks(
    request: Request, # Inject Request
    skip: int = 0, 
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Retrieve decks for the authenticated user."""
    db_decks = await crud.get_user_decks(db=db, user_id=current_user.id, skip=skip, limit=limit)
    
    response_decks: List[schemas.Deck] = []
    for db_deck in db_decks:
        pydantic_deck = schemas.Deck.from_orm(db_deck)
        for pydantic_deck_entry in pydantic_deck.deck_entries:
            # Find the corresponding SQLAlchemy model for the card_definition
            # This assumes db_deck.deck_entries were loaded with their card_definitions by CRUD
            original_db_deck_entry = next((de for de in db_deck.deck_entries if de.id == pydantic_deck_entry.id), None)
            if original_db_deck_entry and original_db_deck_entry.card_definition:
                db_card_def = original_db_deck_entry.card_definition
                if db_card_def.image_data_small:
                    pydantic_deck_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
                if db_card_def.image_data_normal:
                    pydantic_deck_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
                if db_card_def.image_data_large:
                    pydantic_deck_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
        response_decks.append(pydantic_deck)
    return response_decks

@app.get("/decks/{deck_id}", response_model=schemas.Deck)
async def read_single_deck(
    deck_id: int,
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Retrieve a specific deck owned by the authenticated user."""
    db_deck = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id)
    if db_deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")

    pydantic_deck = schemas.Deck.from_orm(db_deck)
    for pydantic_deck_entry in pydantic_deck.deck_entries:
        # Find the corresponding SQLAlchemy model for the card_definition
        original_db_deck_entry = next((de for de in db_deck.deck_entries if de.id == pydantic_deck_entry.id), None)
        if original_db_deck_entry and original_db_deck_entry.card_definition:
            db_card_def = original_db_deck_entry.card_definition
            if db_card_def.image_data_small:
                pydantic_deck_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
            if db_card_def.image_data_normal:
                pydantic_deck_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
            if db_card_def.image_data_large:
                pydantic_deck_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
    return pydantic_deck

@app.put("/decks/{deck_id}", response_model=schemas.Deck)
async def update_existing_deck(
    deck_id: int,
    deck_update: schemas.DeckUpdate,
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a deck's details (name, description, format)."""
    db_deck = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id) # Ensure user owns the deck
    if db_deck is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")
    updated_db_deck = await crud.update_deck(db=db, db_deck=db_deck, deck_update=deck_update)

    pydantic_deck = schemas.Deck.from_orm(updated_db_deck)
    for pydantic_deck_entry in pydantic_deck.deck_entries:
        original_db_deck_entry = next((de for de in updated_db_deck.deck_entries if de.id == pydantic_deck_entry.id), None)
        if original_db_deck_entry and original_db_deck_entry.card_definition:
            db_card_def = original_db_deck_entry.card_definition
            if db_card_def.image_data_small:
                pydantic_deck_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
            if db_card_def.image_data_normal:
                pydantic_deck_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
            if db_card_def.image_data_large:
                pydantic_deck_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
    return pydantic_deck

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
    request: Request, # Inject Request
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Add a card to a specific deck owned by the user."""
    # First, verify the deck exists and belongs to the user
    deck_model = await crud.get_deck(db=db, user_id=current_user.id, deck_id=deck_id) # Fetch the full deck model
    if deck_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck not found or not owned by user")
    try:
        db_deck_entry = await crud.add_card_to_deck(db=db, deck_model=deck_model, deck_entry_create=deck_entry_create)
        pydantic_deck_entry = schemas.DeckEntry.from_orm(db_deck_entry)
        if db_deck_entry.card_definition:
            db_card_def = db_deck_entry.card_definition
            if db_card_def.image_data_small:
                pydantic_deck_entry.card_definition.local_image_url_small = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='small'))
            if db_card_def.image_data_normal:
                pydantic_deck_entry.card_definition.local_image_url_normal = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='normal'))
            if db_card_def.image_data_large:
                pydantic_deck_entry.card_definition.local_image_url_large = str(request.url_for('get_card_image_data', scryfall_id=db_card_def.scryfall_id, size='large'))
        return pydantic_deck_entry
    except ValueError as e: # From crud if CardDefinition not found
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# You would also add endpoints for:
# - PUT /decks/{deck_id}/cards/{deck_entry_id} (Update card quantity/role in deck)
# - DELETE /decks/{deck_id}/cards/{deck_entry_id} (Remove a card from a deck)
