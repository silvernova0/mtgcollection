# c:\Users\social\Desktop\mtg-collection-backend\scripts\verify_image_data.py
import asyncio
import sys
import os
# Add the project root to the Python path
# If this script is in the project root, __file__ gives its path, and dirname gives the project root.
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import CardDefinition as CardDefinitionModel

# Optional: For more advanced image verification
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Pillow library not found. Run 'pip install Pillow' for advanced image verification.")

async def check_card_images(db: AsyncSession, card_name: str = None, card_scryfall_id: str = None):
    """
    Fetches a card from the database and checks its image data fields.
    """
    stmt = select(CardDefinitionModel)
    identifier_used = "a randomly selected card" # Changed default identifier message

    if card_scryfall_id:
        stmt = stmt.where(CardDefinitionModel.scryfall_id == card_scryfall_id)
        identifier_used = f"card with Scryfall ID: {card_scryfall_id}"
        print(f"Attempting to fetch {identifier_used}")
    elif card_name:
        stmt = stmt.where(CardDefinitionModel.name == card_name)
        identifier_used = f"card with name: {card_name}"
        print(f"Attempting to fetch {identifier_used}")
    else:
        # Fetch the first card if no specific identifier is given
        # For PostgreSQL and SQLite, func.random() works.
        # For MySQL, you might need func.rand().
        # This assumes your database supports a RANDOM-like function.
        stmt = stmt.order_by(func.random()).limit(1)
        print(f"Attempting to fetch {identifier_used} from the database.")

    result = await db.execute(stmt)
    card = result.scalars().first()

    if not card:
        print(f"No {identifier_used} in the database.")
        return

    print(f"\n--- Verifying Card: {card.name} (Scryfall ID: {card.scryfall_id}) ---")

    image_fields_to_check = {
        "small": (card.image_uri_small, card.image_data_small),
        "normal": (card.image_uri_normal, card.image_data_normal),
        "large": (card.image_uri_large, card.image_data_large),
    }

    found_any_image_data = False
    for size_key, (uri, data) in image_fields_to_check.items():
        print(f"\nChecking '{size_key}' image:")
        if uri:
            print(f"  URI: {uri}")
            if data:
                print(f"  Data: PRESENT, {len(data)} bytes.")
                found_any_image_data = True
                if PIL_AVAILABLE:
                    try:
                        img = Image.open(io.BytesIO(data))
                        img.verify() # Verifies image integrity
                        # Re-open after verify as verify can make it unusable for some formats
                        img = Image.open(io.BytesIO(data))
                        print(f"  PIL Verification: Success! Format: {img.format}, Mode: {img.mode}, Size: {img.size}")
                        
                        # Optional: Save or show the image for quick local verification
                        # output_filename = f"{card.name.replace(' ', '_').replace('/', '_')}_{size_key}.{img.format.lower()}"
                        # img.save(output_filename)
                        # print(f"  Image saved locally as: {output_filename}")
                        # img.show() # This will open the image with your default image viewer
                    except Exception as e:
                        print(f"  PIL Verification: FAILED to open/verify image data. Error: {e}")
                else:
                    print("  PIL Verification: Pillow library not installed, skipping advanced check.")
            else:
                # This case implies the URI was stored, but the data wasn't.
                # populate_cards.py attempts to nullify URIs if download fails,
                # so this state might indicate an issue or an older record.
                print(f"  Data: NOT Present (but URI exists: {uri}). This might indicate a download failure where URI wasn't nullified.")
        else:
            print(f"  URI: Not present for '{size_key}' size.")
            if data:
                print(f"  Data: PRESENT ({len(data)} bytes), but URI is missing. This is unusual.")
                found_any_image_data = True
            else:
                print(f"  Data: Not present for '{size_key}' size.")
    
    if found_any_image_data:
        print(f"\nSUCCESS: Image data found for '{card.name}'.")
    else:
        print(f"\nINFO: No image data found stored in the database for '{card.name}' for any size.")


async def main():
    async with AsyncSessionLocal() as session:
        # --- !!! IMPORTANT !!! ---
        # CHOOSE ONE WAY TO IDENTIFY THE CARD TO CHECK.
        # Uncomment one of the lines below or add your own.

        # 1. By Scryfall ID (Recommended if you know one that should have images)
        # await check_card_images(session, card_scryfall_id="0000579f-7b35-4ed3-b44c-db2a54860690") # Example: Ancestral Recall (Alpha)

        # 2. By Card Name: Check for "Lightning Bolt"
        await check_card_images(session, card_name="Lightning Bolt")
        
        # 3. Check a random card from the database.
        # await check_card_images(session) # This will now pick a random card

        # You can add more checks here for other cards:
        # print("\n----------------------------------")
        # await check_card_images(session, card_name="Sol Ring")


if __name__ == "__main__":
    print("Starting image data verification script...")
    # Modify the main() function directly to specify the card for this example.
    # For a more advanced script, consider parsing command-line arguments for card_name or scryfall_id.
    asyncio.run(main())
    print("Image data verification script finished.")
