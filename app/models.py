# app/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
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

class CardDefinition(Base): # Renamed from Card
    __tablename__ = "card_definitions"

    id = Column(Integer, primary_key=True, index=True)
    scryfall_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True)
    set_code = Column(String)
    collector_number = Column(String)
    # Add other Scryfall-specific fields here if you want to cache them, e.g.:
    # image_uri_normal = Column(String, nullable=True)
    # image_uri_large = Column(String, nullable=True)
    # mana_cost = Column(String, nullable=True)
    # cmc = Column(Float, nullable=True)
    # type_line = Column(String, nullable=True)
    # oracle_text = Column(String, nullable=True)
    # color_identity = Column(String, nullable=True) # e.g., "W,U,B,R,G"
    # rarity = Column(String, nullable=True)

    date_added = Column(DateTime(timezone=True), server_default=func.now())
    date_updated = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    collection_entries = relationship("UserCollectionEntry", back_populates="card_definition")

    def __repr__(self):
        return f"<CardDefinition(name='{self.name}', scryfall_id='{self.scryfall_id}')>"

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