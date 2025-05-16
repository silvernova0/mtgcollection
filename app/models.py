# app/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, LargeBinary
from sqlalchemy.sql import func # For server-side default timestamp
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    date_joined = Column(DateTime(timezone=True), server_default=func.now())

    collection_entries = relationship("UserCollectionEntry", back_populates="owner")
    decks = relationship("Deck", back_populates="owner")

class CardDefinition(Base): # Renamed from Card
    __tablename__ = "card_definitions"

    id = Column(Integer, primary_key=True, index=True)
    scryfall_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True)
    set_code = Column(String)
    collector_number = Column(String)
    type_line = Column(String, index=True, nullable=True) # Added for searching by type
    legalities = Column(JSON, nullable=True) # To store format legalities e.g. {"standard": "legal", "commander": "legal"}
    image_uri_small = Column(String, nullable=True)
    image_uri_normal = Column(String, nullable=True)
    image_uri_large = Column(String, nullable=True)
    image_uri_art_crop = Column(String, nullable=True)
    image_uri_border_crop = Column(String, nullable=True)
        # New columns for storing raw image data
    image_data_small = Column(LargeBinary, nullable=True)
    image_data_normal = Column(LargeBinary, nullable=True)
    image_data_large = Column(LargeBinary, nullable=True)

    # color_identity = Column(String, nullable=True) # e.g., "W,U,B,R,G"
    # rarity = Column(String, nullable=True)

    date_added = Column(DateTime(timezone=True), server_default=func.now())
    date_updated = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    collection_entries = relationship("UserCollectionEntry", back_populates="card_definition")
    deck_entries = relationship("DeckEntry", back_populates="card_definition")

class Deck(Base):
    __tablename__ = "decks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)
    format = Column(String, nullable=True) # e.g., "Commander", "Standard", "Modern"
    date_created = Column(DateTime(timezone=True), server_default=func.now())
    date_updated = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    owner = relationship("User", back_populates="decks")
    deck_entries = relationship("DeckEntry", back_populates="deck", cascade="all, delete-orphan")

class DeckEntry(Base):
    __tablename__ = "deck_entries"

    id = Column(Integer, primary_key=True, index=True)
    deck_id = Column(Integer, ForeignKey("decks.id"), nullable=False)
    card_definition_id = Column(Integer, ForeignKey("card_definitions.id"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    is_commander = Column(Boolean, default=False)
    is_sideboard = Column(Boolean, default=False)

    deck = relationship("Deck", back_populates="deck_entries")
    card_definition = relationship("CardDefinition", back_populates="deck_entries")

class UserCollectionEntry(Base):
    __tablename__ = "user_collection_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    card_definition_id = Column(Integer, ForeignKey("card_definitions.id"), nullable=False) # Or use scryfall_id as FK

    quantity_normal = Column(Integer, default=0, nullable=False)
    quantity_foil = Column(Integer, default=0, nullable=False)
    condition = Column(String, nullable=True) # e.g., "NM", "LP"
    language = Column(String, default="en", nullable=False) # e.g., "en", "ja"
    notes = Column(String, nullable=True)
    date_added_to_collection = Column(DateTime(timezone=True), server_default=func.now())
    date_updated_in_collection = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    owner = relationship("User", back_populates="collection_entries")
    card_definition = relationship("CardDefinition", back_populates="collection_entries")