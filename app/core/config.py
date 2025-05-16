# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = "your_default_secret_key_please_change_in_env" # Should be overridden by .env
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 # Default to 30 minutes

    class Config:
        env_file = ".env" # Specifies the .env file to load variables from

@lru_cache() # Cache the settings object so .env is read only once
def get_settings():
    return Settings()

settings = get_settings()
# This will load the settings when the module is imported
# and cache them for future use.
# You can access the settings like this:
# settings.DATABASE_URL
# This is a singleton pattern using lru_cache to ensure that the settings are only loaded once.
# This is useful for performance and to avoid re-reading the .env file multiple times.
# The settings can be accessed globally in your application.
