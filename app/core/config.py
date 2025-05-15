# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DATABASE_URL: str

    class Config:
        env_file = ".env" # Specifies the .env file to load variables from

@lru_cache() # Cache the settings object so .env is read only once
def get_settings():
    return Settings()

settings = get_settings()
