"Configuration for the API"

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.getenv("MEMORIX_ENV_FILE") or Path(__file__).resolve().parents[3] / ".env")

class ConfigDB:
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_PORT = os.getenv("DB_PORT")
    DB_HOST = os.getenv("DB_HOST")
    DB_USER = os.getenv("DB_USER")
    DB_NAME = os.getenv("DB_DATABASE")
    DB_SSLMODE = os.getenv("DB_SSLMODE", "require")