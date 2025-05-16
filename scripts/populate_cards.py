# scripts/populate_cards.py
import asyncio
import json
import sys
import os

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

import httpx # Moved import to top level

from sqlalchemy.ext.asyncio import AsyncSession

# You'll need to set up access to your database session and CRUD operations
# This might involve importing from your main app's modules
# For simplicity, assuming you can get a db session and access CRUD
from app.database import AsyncSessionLocal, Base, engine # Adjust imports as needed
from app.models import CardDefinition as CardDefinitionModel # Alias to avoid confusion
from app.schemas import CardDefinitionCreate
from app.crud import get_card_definition_by_scryfall_id, create_card_definition

# URL for a Scryfall bulk data file (e.g., Oracle Cards or All Cards)
# Get the latest download URI from https://api.scryfall.com/bulk-data
# Example: SCRYFALL_BULK_DATA_URL = "https://data.scryfall.io/oracle-cards/oracle-cards-20231030090509.json" 
# It's best to fetch the bulk data list first to get the current download_uri

async def get_latest_bulk_data_uri(bulk_type: str = "oracle_cards"): # or "all_cards"
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.scryfall.com/bulk-data")
        response.raise_for_status()
        bulk_data_list = response.json()["data"]
        for item in bulk_data_list:
            if item["type"] == bulk_type:
                return item["download_uri"]
    return None

async def process_card_data(db: AsyncSession, card_data: dict):
    scryfall_id = card_data.get("id")
    if not scryfall_id:
        print(f"Skipping card with missing Scryfall ID: {card_data.get('name')}")
        return

    existing_card_def = await get_card_definition_by_scryfall_id(db, scryfall_id)
    if existing_card_def:
        # Optionally, you could implement update logic here if the Scryfall data is newer
        # print(f"Card {scryfall_id} ({card_data.get('name')}) already exists. Skipping.")
        return 

    image_uris = card_data.get("image_uris", {})

    # Map Scryfall data to your CardDefinitionCreate schema
    card_def_create = CardDefinitionCreate(
        scryfall_id=scryfall_id,
        name=card_data.get("name"),
        set_code=card_data.get("set"), # For "all_cards" bulk file
        collector_number=card_data.get("collector_number"), # For "all_cards"
        legalities=card_data.get("legalities"),
        image_uri_small=image_uris.get("small"),
        image_uri_normal=image_uris.get("normal"),
        image_uri_large=image_uris.get("large"),
        image_uri_art_crop=image_uris.get("art_crop"),
        image_uri_border_crop=image_uris.get("border_crop"),
        # type_line=card_data.get("type_line"), # Ensure this is in your schema
        # Add other fields you want to store
    )

    # Validate mandatory fields before creation
    if not card_def_create.name: # scryfall_id already checked
        print(f"Skipping card {scryfall_id} due to missing name.")
        return

    try:
        await create_card_definition(db, card_def_create)
        print(f"Stored: {card_def_create.name} ({scryfall_id})")
    except Exception as e:
        print(f"Error storing card {scryfall_id} ({card_def_create.name}): {e}")
        # Potentially rollback this specific card or log for later, depending on transaction strategy

async def main_populate():
    # Initialize DB (if needed for a standalone script, or ensure tables exist)
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)

    bulk_data_uri = await get_latest_bulk_data_uri(bulk_type="all_cards") # or "oracle_cards"
    if not bulk_data_uri:
        print("Could not retrieve bulk data URI.")
        return

    print(f"Downloading bulk data from: {bulk_data_uri}")
    async with httpx.AsyncClient(timeout=None) as client: # Set longer timeout for large files
        response = await client.get(bulk_data_uri)
        response.raise_for_status()
        all_cards_data = response.json() # This will be a list of card objects

    print(f"Downloaded {len(all_cards_data)} card objects.")

    # Ensure database tables are created if not already (idempotent)
    async with engine.begin() as conn:
            # await conn.run_sync(CardDefinitionModel.__table__.drop) # CAUTION: Drops the table!
        await conn.run_sync(Base.metadata.create_all)
            # await conn.commit() # Ensure the drop is committed if you use it
    print("Database tables ensured.")

    async with AsyncSessionLocal() as session:
        try:
            concurrency_factor = 50  # Number of cards to process concurrently
            commit_batch_size = 1000 # Number of cards processed before a DB commit
            
            processed_count_since_last_commit = 0

            for i in range(0, len(all_cards_data), concurrency_factor):
                batch_card_data = all_cards_data[i:i + concurrency_factor]
                tasks = [process_card_data(session, card_data) for card_data in batch_card_data]
                
                # Process a batch of cards concurrently
                await asyncio.gather(*tasks)
                
                processed_count_in_batch = len(batch_card_data)
                processed_count_since_last_commit += processed_count_in_batch
                total_processed = i + processed_count_in_batch
                print(f"Processed batch of {processed_count_in_batch} cards. Total processed: {total_processed}/{len(all_cards_data)}")

                if processed_count_since_last_commit >= commit_batch_size:
                    print(f"Committing batch of {processed_count_since_last_commit} processed card records...")
                    await session.commit()
                    print("Batch committed.")
                    processed_count_since_last_commit = 0
            
            if processed_count_since_last_commit > 0: # Commit any remaining cards
                print(f"Committing final {processed_count_since_last_commit} processed card records...")
                await session.commit()
                print("Final commit complete.")
        except Exception as e:
            print(f"An error occurred during bulk processing: {e}")
            await session.rollback()
        finally:
            await session.close()

    print("Card population process finished.")

if __name__ == "__main__":
    asyncio.run(main_populate())
# This script will download the latest Scryfall bulk data and populate your database with card definitions.