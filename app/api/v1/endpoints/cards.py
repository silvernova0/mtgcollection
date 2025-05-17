# Suggested location: app/api/v1/endpoints/cards.py
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import Response # For serving binary image data
from enum import Enum

# Adjust these imports based on your project structure
from app import crud
from app.models import CardDefinition as CardDefinitionModel # For direct model access if needed, though CRUD is used
from app.database import get_db # Your dependency to get the database session

# Optional: For more advanced image verification/MIME type detection
# import io
# from PIL import Image
# PIL_AVAILABLE = True # You'd set this based on Pillow installation

router = APIRouter()

class StoredImageSize(str, Enum):
    """
    Represents the image sizes for which binary data is stored in the database
    by the populate_cards.py script.
    """
    small = "small"
    normal = "normal"
    large = "large"

@router.get(
    "/cards/{scryfall_id}/image/{size}", # Changed: size is now a path parameter
    responses={
        200: {
            "content": {"image/jpeg": {}, "image/png": {}}, # More descriptive content types
            "description": "The card image in the specified size.",
        },
        404: {"description": "Card or image data not found"},
        400: {"description": "Invalid image size requested"},
    },
    summary="Get Card Image Data",
    description="Serves the stored binary image data for a card. "
                "Currently supports 'small', 'normal', and 'large' sizes "
                "and typically serves JPEG format.",
)
async def get_card_image_data(
    scryfall_id: str = Path(..., description="The Scryfall ID of the card."),
    size: StoredImageSize = Path(
        ..., # Made 'size' a required path parameter
        description="The desired image size (small, normal, or large)."
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves and serves the binary image data for a specific card and size.
    """
    card = await crud.get_card_definition_by_scryfall_id(db, scryfall_id=scryfall_id)
    # The example used:
    # stmt = select(CardDefinitionModel).where(CardDefinitionModel.scryfall_id == scryfall_id)
    # result = await db.execute(stmt)
    # card = result.scalars().first()
    # Your CRUD method is fine.

    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    image_data: bytes | None = None

    if size == StoredImageSize.small:
        image_data = card.image_data_small
    elif size == StoredImageSize.normal:
        image_data = card.image_data_normal
    elif size == StoredImageSize.large:
        image_data = card.image_data_large
    # Note: The populate_cards.py script currently only downloads binary data for
    # 'small', 'normal', and 'large' images. 'art_crop' and 'border_crop' are
    # stored as URIs. If you need to serve their binary data directly,
    # you would need to:
    # 1. Add `image_data_art_crop` and `image_data_border_crop` (LargeBinary)
    #    fields to your `CardDefinitionModel`.
    # 2. Update `populate_cards.py` to download and store this data.
    # 3. Extend the `StoredImageSize` enum and this logic.

    if not image_data:
        raise HTTPException(
            status_code=404,
            detail=f"Image data for size '{size.value}' not found for card {scryfall_id}."
        )

    media_type = "image/jpeg" # Default assumption

    # Optional: Dynamic MIME type detection using Pillow (if installed and image_data is valid)
    # if PIL_AVAILABLE and image_data:
    #     try:
    #         pil_img = Image.open(io.BytesIO(image_data))
    #         detected_mime = Image.MIME.get(pil_img.format)
    #         if detected_mime:
    #             media_type = detected_mime
    #         else:
    #             # Fallback if Pillow format isn't in its MIME dictionary
    #             media_type = "application/octet-stream"
    #         # print(f"Pillow detected format: {pil_img.format}, MIME: {media_type} for {scryfall_id} size {size.value}")
    #     except Exception as e:
    #         # print(f"Could not determine MIME type with Pillow for {scryfall_id} size {size.value}: {e}")
    #         # Keep default media_type or use "application/octet-stream" as a generic fallback
    #         pass # Keep default media_type

    return Response(content=image_data, media_type=media_type)
