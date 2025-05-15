# app/models.py
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime
from sqlalchemy.sql import func # For server-side default timestamp
from .database import Base

class Card(Base):
    __tablename__ = "cards" # Name of the table in the database

    id = Column(Integer, primary_key=True, index=True)
    scryfall_id = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, index=True)
    set_code = Column(String)
    collector_number = Column(String)
    quantity_normal = Column(Integer, default=0)
    quantity_foil = Column(Integer, default=0)
    # Add other fields as per your schema design in mtg_tracker_guide
    # e.g., condition, language, purchase_price, notes
    # For simplicity, we'll keep it shorter for now.

    # Optional: Timestamps
    date_added = Column(DateTime(timezone=True), server_default=func.now())
    date_updated = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Card(name='{self.name}', scryfall_id='{self.scryfall_id}')>"