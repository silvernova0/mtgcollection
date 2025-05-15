# app/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List # For list responses

from . import models, schemas, crud # Import schemas and crud
from .database import engine, get_db

async def create_db_and_tables():
    async with engine.begin() as conn:
        # await conn.run_sync(models.Base.metadata.drop_all) # Optional: drop tables for clean slate
        await conn.run_sync(models.Base.metadata.create_all)

app = FastAPI(
    title="MTG Collection Tracker API",
    description="API for managing a Magic: The Gathering card collection.",
    version="0.1.0",
    on_startup=[create_db_and_tables]
)

@app.get("/")
async def read_root():
    return {"message": "Welcome to the MTG Collection Tracker API!"}

@app.post("/cards/", response_model=schemas.Card, status_code=201) # Use Card schema for response
async def create_new_card(card: schemas.CardCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new card in the collection.
    - **card**: Card details based on CardCreate schema.
    """
    # Check if card already exists by Scryfall ID
    db_card = await crud.get_card_by_scryfall_id(db=db, scryfall_id=card.scryfall_id)
    if db_card:
        raise HTTPException(status_code=400, detail="Card with this Scryfall ID already exists in collection")
    return await crud.create_card(db=db, card=card)

@app.get("/cards/{card_id}", response_model=schemas.Card)
async def read_card(card_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get a specific card by its database ID.
    """
    db_card = await crud.get_card(db=db, card_id=card_id)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return db_card

@app.get("/cards/scryfall/{scryfall_id}", response_model=schemas.Card)
async def read_card_by_scryfall_id(scryfall_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a specific card by its Scryfall ID.
    """
    db_card = await crud.get_card_by_scryfall_id(db=db, scryfall_id=scryfall_id)
    if db_card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return db_card

@app.get("/cards/", response_model=List[schemas.Card]) # Response is a list of Cards
async def read_cards_list(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a list of cards from the collection.
    Supports pagination via `skip` and `limit` query parameters.
    """
    cards = await crud.get_cards(db=db, skip=skip, limit=limit)
    return cards

# Remove or comment out the old create_card_example endpoint if it's still there
# @app.post("/cards_initial_test/") ...
