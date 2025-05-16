# Suggested location: app/api/v1/endpoints/cards.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import Response # For serving binary image data
from enum import Enum

# Adjust these imports based on your project structure
from app import crud
from app.database import get_db # Your dependency to get the database session

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
    "/cards/{scryfall_id}/image",
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
)
async def get_card_image_data(
    scryfall_id: str,
    size: StoredImageSize = Query(
        StoredImageSize.normal,
        description="The desired image size (small, normal, or large)."
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves and serves the binary image data for a specific card and size.
    """
    card = await crud.get_card_definition_by_scryfall_id(db, scryfall_id=scryfall_id)
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

    # Scryfall images are typically JPEGs.
    # If you store other formats, you might need to store the MIME type
    # or infer it.
    return Response(content=image_data, media_type="image/jpeg")

