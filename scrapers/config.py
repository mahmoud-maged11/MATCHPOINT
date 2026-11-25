import os
from pathlib import Path
from dotenv import load_dotenv

# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# HTTP configuration
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
REQUEST_DELAY = 2

# PostgreSQL configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "matchpoint")
POSTGRES_USER = os.getenv("POSTGRES_USER", "matchpoint")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Project timezone
TIMEZONE = os.getenv("TZ", "Africa/Cairo")