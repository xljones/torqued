"""Per-garage access control.

Roles: 'owner' manages the garage's members and settings; 'member' has full
read-write on its vehicles; 'readonly' can only view. Site admins
(users.is_admin) act as owners of every garage.
"""
from typing import Any

from sqlalchemy.orm import Session

WRITE_ROLES = ("owner", "member")


def garage_role(session: Session, user: Any, garage_id: int) -> str | None:
    """Return the user's effective role in a garage, or None if no access."""
    if user.is_admin:
        return "owner"
    from torqued.repositories.garage_repository import GarageRepository

    return GarageRepository(session).member_role(garage_id, user.id)


def vehicle_role(session: Session, user: Any, vehicle_id: int) -> str | None:
    """Return the user's effective role for the garage owning a vehicle, or None."""
    from torqued.repositories.vehicle_repository import VehicleRepository

    garage_id = VehicleRepository(session).garage_id_for(vehicle_id)
    if garage_id is None:
        return None
    return garage_role(session, user, garage_id)


def can_write(role: str | None) -> bool:
    """True if the role allows creating/editing/deleting within the garage."""
    return role in WRITE_ROLES


def accessible_garage_ids(session: Session, user: Any) -> list[int]:
    """Garage IDs visible to the user (all garages for site admins)."""
    from torqued.repositories.garage_repository import GarageRepository

    return GarageRepository(session).accessible_garage_ids(user.id, user.is_admin)
