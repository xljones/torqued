from dataclasses import dataclass
from datetime import datetime, timezone

from flask_login import UserMixin


@dataclass
class User(UserMixin):
    id: int
    username: str
    created_at: str | None = None
    is_readonly: bool = False
    is_admin: bool = False
    expires_at: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        if self.expires_at:
            try:
                return datetime.now(timezone.utc) < datetime.fromisoformat(self.expires_at)
            except ValueError:
                pass
        return True
