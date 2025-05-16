# c:\Users\social\Desktop\mtg-collection-backend\app\api\v1\endpoints\users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Ensure these imports are correct for your project structure
from app.crud.crud_user import get_user_by_email, create_user as crud_create_user
from app.schemas.user import User as UserSchema, UserCreate
from app.db.session import get_db

router = APIRouter() # Crucial: defines the router for this file

@router.post( # Ensures this route is part of the 'router' instance above
    "/", # This means the endpoint is at the root of this router's prefix
    response_model=UserSchema,
    status_code=status.HTTP_201_CREATED
)
def create_user_registration(
    *,
    db: Session = Depends(get_db),
    user_in: UserCreate
):
    user = get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )
    created_user = crud_create_user(db=db, user=user_in)
    return created_user

