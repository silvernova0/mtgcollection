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
from app.crud import get_card_definition_by_scryfall_id # create_card_definition no longer used directly here

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

    card_name_from_bulk = card_data.get("name")
    if not card_name_from_bulk:
        print(f"Skipping card {scryfall_id} due to missing name in bulk data.")
        return

    card_to_process: CardDefinitionModel | None = await get_card_definition_by_scryfall_id(db, scryfall_id)
    is_new_card = False

    image_uris = card_data.get("image_uris", {})

    if card_to_process:
        print(f"Card {scryfall_id} ({card_name_from_bulk}) already exists. Checking for updates...")
        # Update existing card's attributes
        card_to_process.name = card_name_from_bulk
        card_to_process.set_code = card_data.get("set")
        card_to_process.collector_number = card_data.get("collector_number")
        card_to_process.legalities = card_data.get("legalities")
        card_to_process.type_line = card_data.get("type_line")
        
        card_to_process.image_uri_small = image_uris.get("small")
        card_to_process.image_uri_normal = image_uris.get("normal")
        card_to_process.image_uri_large = image_uris.get("large")
        card_to_process.image_uri_art_crop = image_uris.get("art_crop")
        card_to_process.image_uri_border_crop = image_uris.get("border_crop")
        # SQLAlchemy's onupdate mechanism should handle 'date_updated'

    else: # Card does not exist, create a new one
        print(f"Card {scryfall_id} ({card_name_from_bulk}) not found. Creating new record...")
        is_new_card = True
        
        card_model_data_for_new = {
            "scryfall_id": scryfall_id,
            "name": card_name_from_bulk,
            "set_code": card_data.get("set"),
            "collector_number": card_data.get("collector_number"),
            "legalities": card_data.get("legalities"),
            "type_line": card_data.get("type_line"),
            "image_uri_small": image_uris.get("small"),
            "image_uri_normal": image_uris.get("normal"),
            "image_uri_large": image_uris.get("large"),
            "image_uri_art_crop": image_uris.get("art_crop"),
            "image_uri_border_crop": image_uris.get("border_crop"),
            "image_data_small": None,
            "image_data_normal": None,
            "image_data_large": None,
        }
        try:
            card_to_process = CardDefinitionModel(**card_model_data_for_new)
        except Exception as e:
            print(f"Error instantiating CardDefinitionModel for new card {scryfall_id} ({card_name_from_bulk}): {e}")
            return

    # Download image data if URI exists and corresponding image_data field is None
    if card_to_process.image_uri_small and not card_to_process.image_data_small:
        try:
            print(f"Attempting to download small image for {card_to_process.name} from {card_to_process.image_uri_small}")
            response = await image_client.get(card_to_process.image_uri_small)
            response.raise_for_status()
            card_to_process.image_data_small = response.content
            print(f"Successfully downloaded small image for {card_to_process.name} ({len(response.content)} bytes)")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error downloading small image for {scryfall_id} ({card_to_process.name}): {e.response.status_code} - {e.request.url}")
            card_to_process.image_uri_small = None
            card_to_process.image_data_small = None
        except Exception as e:
            print(f"Generic Error downloading small image for {scryfall_id} ({card_to_process.name}): {e}")
            card_to_process.image_uri_small = None
            card_to_process.image_data_small = None

    if card_to_process.image_uri_normal and not card_to_process.image_data_normal:
        try:
            print(f"Attempting to download normal image for {card_to_process.name} from {card_to_process.image_uri_normal}")
            response = await image_client.get(card_to_process.image_uri_normal)
            response.raise_for_status()
            card_to_process.image_data_normal = response.content
            print(f"Successfully downloaded normal image for {card_to_process.name} ({len(response.content)} bytes)")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error downloading normal image for {scryfall_id} ({card_to_process.name}): {e.response.status_code} - {e.request.url}")
            card_to_process.image_uri_normal = None
            card_to_process.image_data_normal = None
        except Exception as e:
            print(f"Generic Error downloading normal image for {scryfall_id} ({card_to_process.name}): {e}")
            card_to_process.image_uri_normal = None
            card_to_process.image_data_normal = None

    if card_to_process.image_uri_large and not card_to_process.image_data_large:
        try:
            print(f"Attempting to download large image for {card_to_process.name} from {card_to_process.image_uri_large}")
            response = await image_client.get(card_to_process.image_uri_large)
            response.raise_for_status()
            card_to_process.image_data_large = response.content
            print(f"Successfully downloaded large image for {card_to_process.name} ({len(response.content)} bytes)")
        except httpx.HTTPStatusError as e:
            print(f"HTTP Error downloading large image for {scryfall_id} ({card_to_process.name}): {e.response.status_code} - {e.request.url}")
            card_to_process.image_uri_large = None
            card_to_process.image_data_large = None
        except Exception as e:
            print(f"Generic Error downloading large image for {scryfall_id} ({card_to_process.name}): {e}")
            card_to_process.image_uri_large = None
            card_to_process.image_data_large = None

    if is_new_card and card_to_process:
        try:
            db.add(card_to_process)
        except Exception as e:
            print(f"Error adding new card {card_to_process.name} ({scryfall_id}) to session: {e}")

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
                    current_batch_all_cards = all_cards_data[i:i + concurrency_factor]
                    
                    # Filter this batch for "Lightning Bolt" cards
                    lightning_bolt_batch = [
                        card_data for card_data in current_batch_all_cards
                        if card_data.get("name") == "Lightning Bolt"
                    ]

                    total_scanned_so_far = i + len(current_batch_all_cards)

                    if not lightning_bolt_batch:
                        print(f"Scanned batch up to card {total_scanned_so_far}/{len(all_cards_data)}. No 'Lightning Bolt' found in this specific segment.")
                        continue # Move to the next segment of the bulk data

                    print(f"Found {len(lightning_bolt_batch)} 'Lightning Bolt' card(s) in current batch segment. Processing them...")
                    # Pass the image_download_client and only the filtered Lightning Bolt cards
                    tasks = [process_card_data(session, card_data, image_download_client) for card_data in lightning_bolt_batch]
                    
                    # Process a batch of cards concurrently
                    await asyncio.gather(*tasks)
                    
                    processed_count_in_batch = len(lightning_bolt_batch) # Number of Lightning Bolts processed
                    processed_count_since_last_commit += processed_count_in_batch
                    print(f"Processed {processed_count_in_batch} 'Lightning Bolt' card(s). Total cards scanned from bulk: {total_scanned_so_far}/{len(all_cards_data)}")

                    if processed_count_since_last_commit >= commit_batch_size:
                        print(f"Committing {processed_count_since_last_commit} 'Lightning Bolt' records...")
                        await session.commit()
                        print("Batch committed.")
                        processed_count_since_last_commit = 0
                    
                # This final commit block was correctly placed after the loop,
                # but the 'finally' block for session.close() is not strictly needed
                # due to the 'async with AsyncSessionLocal() as session:' context manager.
                if processed_count_since_last_commit > 0: # Commit any remaining cards
                    print(f"Committing final {processed_count_since_last_commit} 'Lightning Bolt' records...")
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