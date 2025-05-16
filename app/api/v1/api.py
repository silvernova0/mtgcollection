from fastapi import APIRouter

from .endpoints import users # Add other endpoints here as you create them

api_router = APIRouter()
api_router.include_router(users.router, prefix="/users", tags=["users"])
# api_router.include_router(auth.router, prefix="/auth", tags=["auth"]) # If you create an auth router