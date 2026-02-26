"""User model for multi-user authentication."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from flask_login import UserMixin


@dataclass
class User(UserMixin):
    """Application user with optional Google OAuth link."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    email: str = ""
    password_hash: str = ""
    name: str = ""
    google_id: str = ""
    avatar_url: str = ""
    default_tail_number: str = ""
    default_aircraft_type: str = ""
    default_departure: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
