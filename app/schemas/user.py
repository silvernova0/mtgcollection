from pydantic import BaseModel, EmailStr
from typing import Optional

# Schema for user creation (input)
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

# Schema for reading user data (output, doesn't include password)
class User(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True # Default to active, can be managed by an admin later

    class Config:
        orm_mode = True # For compatibility with SQLAlchemy models

# Schema for token data (if you implement JWT later)
class TokenData(BaseModel):
    email: Optional[EmailStr] = None