"""User model for multi-user authentication."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from flask_login import UserMixin


def generate_access_token() -> str:
    """Generate a token in xxxx-xxxx-xxxx-xxxx format (16 hex chars, 64-bit entropy)."""
    import secrets
    hex_chars = secrets.token_hex(8)  # 16 hex chars
    return "-".join(hex_chars[i:i + 4] for i in range(0, 16, 4))


@dataclass
class User(UserMixin):
    """Application user with optional Google OAuth link."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    password_hash: str = ""
    name: str = ""
    google_id: str = ""
    avatar_url: str = ""
    google_refresh_token: str = ""
    backup_sheet_id: str = ""
    default_tail_number: str = ""
    default_aircraft_type: str = ""
    default_departure: str = ""
    access_token: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
