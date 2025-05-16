from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .... import crud # Assuming crud/__init__.py might exist or direct import
from .... import schemas # Assuming schemas/__init__.py might exist or direct import
from ....db.session import get_db # Or your equivalent get_db dependency

router = APIRouter()

@router.post("/", response_model=schemas.user.User, status_code=status.HTTP_201_CREATED)
def create_user_registration(
    *,
    db: Session = Depends(get_db),
    user_in: schemas.user.UserCreate
):
    """
    Create new user.
    """
    user = crud.user.get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )
    user = crud.user.create_user(db=db, user=user_in)
    return user