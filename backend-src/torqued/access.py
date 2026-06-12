"""Per-garage access control.

Roles: 'owner' manages the garage's members and settings; 'member' has full
read-write on its vehicles; 'readonly' can only view. Site admins
(users.is_admin) act as owners of every garage.
"""
import sqlite3
from typing import Any

WRITE_ROLES = ("owner", "member")


def garage_role(db: sqlite3.Connection, user: Any, garage_id: int) -> str | None:
    """Return the user's effective role in a garage, or None if no access."""
    if user.is_admin:
        return "owner"
    from torqued.repositories.garage_repository import GarageRepository

    return GarageRepository(db).member_role(garage_id, user.id)


def vehicle_role(db: sqlite3.Connection, user: Any, vehicle_id: int) -> str | None:
    """Return the user's effective role for the garage owning a vehicle, or None."""
    row = db.execute("SELECT garage_id FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
    if not row:
        return None
    return garage_role(db, user, row["garage_id"])


def can_write(role: str | None) -> bool:
    """True if the role allows creating/editing/deleting within the garage."""
    return role in WRITE_ROLES


def accessible_garage_ids(db: sqlite3.Connection, user: Any) -> list[int]:
    """Garage IDs visible to the user (all garages for site admins)."""
    from torqued.repositories.garage_repository import GarageRepository

    return GarageRepository(db).accessible_garage_ids(user.id, user.is_admin)
