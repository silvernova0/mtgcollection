# app/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict # Ensure List and Dict are imported
from datetime import datetime

# --- Card Definition Schemas ---
# (Represents the general information about a card, not a user's specific copy)

class CardDefinitionBase(BaseModel):
    scryfall_id: Optional[str] = None
    name: Optional[str] = None
    set_code: Optional[str] = None
    collector_number: Optional[str] = None
    legalities: Optional[Dict[str, str]] = None
    type_line: Optional[str] = None # Added type_line
    image_uri_small: Optional[str] = None
    image_uri_normal: Optional[str] = None
    image_uri_large: Optional[str] = None
    image_uri_art_crop: Optional[str] = None
    image_uri_border_crop: Optional[str] = None
    
    # New fields for locally served image URLs
    local_image_url_small: Optional[str] = None
    local_image_url_normal: Optional[str] = None
    local_image_url_large: Optional[str] = None

class CardDefinitionCreate(CardDefinitionBase):
    scryfall_id: str # Mandatory for creation
    name: str        # Mandatory for creation
    # Include other mandatory fields if you allow direct creation of definitions

class CardDefinitionUpdate(CardDefinitionBase):
    pass # All fields optional for update

class CardDefinition(CardDefinitionBase): # For returning a card definition
    id: int
    date_added: datetime
    date_updated: Optional[datetime] = None # Make optional or ensure it's always set

    class Config:
        from_attributes = True # Changed from orm_mode = True for Pydantic v2

# --- User Collection Entry Schemas ---
# (Represents a specific card instance in a user's collection)

class UserCollectionEntryBase(BaseModel):
    quantity_normal: int = Field(default=0, ge=0)
    quantity_foil: int = Field(default=0, ge=0)
    condition: Optional[str] = None
    language: Optional[str] = Field(default="en")
    notes: Optional[str] = None

class UserCollectionEntryCreate(UserCollectionEntryBase):
    card_definition_scryfall_id: str # User provides Scryfall ID of the card to add
    # quantity_normal and quantity_foil will use defaults if not provided

class UserCollectionEntryUpdate(BaseModel): # More specific for updates
    quantity_normal: Optional[int] = Field(default=None, ge=0)
    quantity_foil: Optional[int] = Field(default=None, ge=0)
    condition: Optional[str] = None
    language: Optional[str] = None
    notes: Optional[str] = None

class UserCollectionEntry(UserCollectionEntryBase): # For returning a collection entry
    id: int
    user_id: int
    card_definition_id: int # The ID of the CardDefinition
    date_added_to_collection: datetime
    date_updated_in_collection: Optional[datetime] = None
    card_definition: CardDefinition # Nested card definition details

    class Config:
        from_attributes = True

# Schemas for User Authentication
class UserBase(BaseModel):
    username: str
    email: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase): # Schema for returning user data
    id: int
    is_active: bool

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Deck Schemas ---
class DeckEntryBase(BaseModel):
    quantity: int = Field(default=1, ge=1)
    is_commander: bool = False
    is_sideboard: bool = False

class DeckEntryCreate(DeckEntryBase):
    card_definition_scryfall_id: str # To identify the card to add

class DeckEntryUpdate(BaseModel):
    quantity: Optional[int] = Field(default=None, ge=0) # Allow setting to 0 to remove, or handle removal separately
    is_commander: Optional[bool] = None
    is_sideboard: Optional[bool] = None

class DeckEntry(DeckEntryBase): # For returning a deck entry
    id: int
    deck_id: int
    card_definition: CardDefinition # Nested card definition details

    class Config:
        from_attributes = True

class DeckBase(BaseModel):
    name: str
    description: Optional[str] = None
    format: Optional[str] = None

class DeckCreate(DeckBase):
    pass

class DeckUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = None

class Deck(DeckBase): # For returning a deck
    id: int
    user_id: int
    date_created: datetime
    date_updated: Optional[datetime] = None
    deck_entries: List[DeckEntry] = [] # List of cards in the deck

    class Config:
        from_attributes = True
