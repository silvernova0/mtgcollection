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
# from app.schemas import CardDefinitionCreate # No longer using this directly for model creation in script
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

async def process_card_data(db: AsyncSession, card_data: dict, image_client: httpx.AsyncClient):
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

    card_model_data = {
        "scryfall_id": scryfall_id,
        "name": card_data.get("name"),
        "set_code": card_data.get("set"),
        "collector_number": card_data.get("collector_number"),
        "legalities": card_data.get("legalities"),
        "type_line": card_data.get("type_line"),
        "image_uri_small": image_uris.get("small"),
        "image_uri_normal": image_uris.get("normal"),
        "image_uri_large": image_uris.get("large"),
        "image_uri_art_crop": image_uris.get("art_crop"),
        "image_uri_border_crop": image_uris.get("border_crop"),
        # Initialize new image data fields
        "image_data_small": None,
        "image_data_normal": None,
        "image_data_large": None,
    }

    # Validate mandatory fields before creation
    if not card_model_data["name"]: # scryfall_id already checked
        print(f"Skipping card {scryfall_id} due to missing name.")
        return
    
        # Download image data
    if card_model_data["image_uri_small"]:
        try:
            print(f"Attempting to download small image for {card_model_data['name']} from {card_model_data['image_uri_small']}")
            response = await image_client.get(card_model_data["image_uri_small"])
            response.raise_for_status()
            card_model_data["image_data_small"] = response.content
            print(f"Successfully downloaded small image for {card_model_data['name']} ({len(response.content)} bytes)")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error downloading small image for {scryfall_id} ({card_model_data['name']}): {e.response.status_code} - {e.request.url}")
        except Exception as e:
            print(f"Generic Error downloading small image for {scryfall_id} ({card_model_data['name']}): {e}")
            card_model_data["image_uri_small"] = None # Nullify URI if download fails

    if card_model_data["image_uri_normal"]:
        try:
            print(f"Attempting to download normal image for {card_model_data['name']} from {card_model_data['image_uri_normal']}")
            response = await image_client.get(card_model_data["image_uri_normal"])
            response.raise_for_status()
            card_model_data["image_data_normal"] = response.content
            print(f"Successfully downloaded normal image for {card_model_data['name']} ({len(response.content)} bytes)")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error downloading normal image for {scryfall_id} ({card_model_data['name']}): {e.response.status_code} - {e.request.url}")
        except Exception as e:
            print(f"Generic Error downloading normal image for {scryfall_id} ({card_model_data['name']}): {e}")
            card_model_data["image_uri_normal"] = None

    if card_model_data["image_uri_large"]:
        try:
            print(f"Attempting to download large image for {card_model_data['name']} from {card_model_data['image_uri_large']}")
            response = await image_client.get(card_model_data["image_uri_large"])
            response.raise_for_status()
            card_model_data["image_data_large"] = response.content
            print(f"Successfully downloaded large image for {card_model_data['name']} ({len(response.content)} bytes)")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error downloading large image for {scryfall_id} ({card_model_data['name']}): {e.response.status_code} - {e.request.url}")
        except Exception as e:
            print(f"Generic Error downloading large image for {scryfall_id} ({card_model_data['name']}): {e}")
            card_model_data["image_uri_large"] = None


    try:
        # Create the SQLAlchemy model instance directly
        db_card_def = CardDefinitionModel(**card_model_data)
        db.add(db_card_def)
        # The actual db.flush() and db.commit() will be handled by main_populate in batches
        # print(f"Prepared for DB: {card_model_data['name']} ({scryfall_id})")

    except Exception as e:
        print(f"Error creating CardDefinitionModel for {scryfall_id} ({card_model_data['name']}): {e}")
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
        # await conn.run_sync(CardDefinitionModel.__table__.drop, checkfirst=True) # CAUTION: Drops the table! - Commented out
        await conn.run_sync(Base.metadata.create_all)
        # No explicit commit needed here as engine.begin() handles transaction
    print("Database tables ensured.")

    async with AsyncSessionLocal() as session:
        # Create one httpx client for all image downloads within this session
        async with httpx.AsyncClient(timeout=30) as image_download_client: # Timeout for individual image downloads
            try:
                concurrency_factor = 20  # Reduced concurrency due to image downloads
                commit_batch_size = 200 # Commit more frequently due to larger data
                
                processed_count_since_last_commit = 0

                for i in range(0, len(all_cards_data), concurrency_factor):
                    batch_card_data = all_cards_data[i:i + concurrency_factor]
                    # Pass the image_download_client to process_card_data
                    tasks = [process_card_data(session, card_data, image_download_client) for card_data in batch_card_data]
                    
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
                    
                # This final commit block was correctly placed after the loop,
                # but the 'finally' block for session.close() is not strictly needed
                # due to the 'async with AsyncSessionLocal() as session:' context manager.
                if processed_count_since_last_commit > 0: # Commit any remaining cards
                    print(f"Committing final {processed_count_since_last_commit} processed card records...")
                    await session.commit()
                    print("Final commit complete.")
            except Exception as e:
                print(f"An error occurred during bulk processing: {e}")
                await session.rollback()
            # 'finally: await session.close()' is not needed here as the context manager handles it.


    print("Card population process finished.")

if __name__ == "__main__":
    asyncio.run(main_populate())
# This script will download the latest Scryfall bulk data and populate your database with card definitions.