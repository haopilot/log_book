"""Configuration settings for the Pilot Logbook application."""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration."""

    # Flask settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")
    DEBUG = os.environ.get("DEBUG", "True").lower() == "true"

    # Google OAuth
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    # FlightAware API
    FLIGHTAWARE_API_KEY = os.environ.get("FLIGHTAWARE_API_KEY", "")
    FLIGHTAWARE_API_URL = "https://aeroapi.flightaware.com/aeroapi"

    # Default aircraft settings
    DEFAULT_TAIL_NUMBER = os.environ.get("AIRCRAFT_TAIL_NUMBER", "N790TB")
    DEFAULT_AIRCRAFT_TYPE = os.environ.get("AIRCRAFT_TYPE", "TBM7")
    DEFAULT_DEPARTURE = os.environ.get("DEFAULT_DEPARTURE", "KPAE")

    # Logbook defaults
    DEFAULT_PILOT_FUNCTION = os.environ.get("DEFAULT_PILOT_FUNCTION", "PIC")

    # Server settings
    PORT = int(os.environ.get("PORT", 5051))
    HOST = os.environ.get("HOST", "0.0.0.0")

    # Local storage path for logbook data
    DATA_FILE = os.environ.get("DATA_FILE", "logbook_data.json")

    # SQLite database path (primary local storage)
    SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "logbook.db")
