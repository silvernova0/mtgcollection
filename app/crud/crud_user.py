from sqlalchemy.orm import Session
from ..models.user import User # Adjust import if your model is elsewhere
from ..schemas.user import UserCreate
from ..core.security import get_password_hash

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user: UserCreate) -> User:
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name
        # is_active is True by default in the model
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user