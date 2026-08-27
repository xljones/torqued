from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import aliased

from torqued.models import Garage, GarageMember, User, Vehicle, to_dict
from torqued.reminders import ReminderWindows, windows_from_row
from torqued.repositories.base import BaseRepository

ROLES = ("owner", "member", "readonly")


def _count_subqueries() -> tuple[Any, Any]:
    """Correlated per-garage vehicle and member counts (aliased so they never collide
    with a garage_members table joined in the outer query)."""
    v = aliased(Vehicle)
    m = aliased(GarageMember)
    vehicle_count = (
        select(func.count()).select_from(v).where(v.garage_id == Garage.id).correlate(Garage)
    ).scalar_subquery()
    member_count = (
        select(func.count()).select_from(m).where(m.garage_id == Garage.id).correlate(Garage)
    ).scalar_subquery()
    return vehicle_count, member_count


class GarageRepository(BaseRepository):
    def list_all(self) -> list[dict[str, Any]]:
        """Return every garage with vehicle and member counts (site-admin view)."""
        vehicle_count, member_count = _count_subqueries()
        rows = self.session.execute(
            select(
                Garage,
                vehicle_count.label("vehicle_count"),
                member_count.label("member_count"),
            ).order_by(Garage.name)
        ).all()
        return [
            {**to_dict(garage), "vehicle_count": vc, "member_count": mc}
            for garage, vc, mc in rows
        ]

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return the garages a user belongs to, with their role and counts."""
        vehicle_count, member_count = _count_subqueries()
        rows = self.session.execute(
            select(
                Garage,
                GarageMember.role,
                vehicle_count.label("vehicle_count"),
                member_count.label("member_count"),
            )
            .join(GarageMember, GarageMember.garage_id == Garage.id)
            .where(GarageMember.user_id == user_id)
            .order_by(Garage.name)
        ).all()
        return [
            {**to_dict(garage), "role": role, "vehicle_count": vc, "member_count": mc}
            for garage, role, vc, mc in rows
        ]

    def get_by_id(self, garage_id: int) -> dict[str, Any] | None:
        """Return a single garage by primary key, or None if not found."""
        garage = self.session.get(Garage, garage_id)
        return to_dict(garage) if garage else None

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        """Return a garage by name (case-insensitive), or None if not found."""
        garage = self.session.scalars(
            select(Garage).where(func.lower(Garage.name) == func.lower(name))
        ).first()
        return to_dict(garage) if garage else None

    def create(self, name: str) -> dict[str, Any]:
        """Insert a new garage and return it."""
        garage = Garage(name=name)
        self.session.add(garage)
        self.session.flush()  # assigns the PK and surfaces a duplicate-name IntegrityError
        created = self.get_by_id(garage.id)
        if created is None:  # pragma: no cover
            raise RuntimeError(f"Row {garage.id} not found after INSERT")
        return created

    def rename(self, garage_id: int, name: str) -> dict[str, Any] | None:
        """Rename a garage and return the updated row."""
        self.session.execute(update(Garage).where(Garage.id == garage_id).values(name=name))
        return self.get_by_id(garage_id)

    def delete(self, garage_id: int) -> bool:
        """Delete a garage (cascades to members and vehicles); True if a row was removed."""
        return self.affected(delete(Garage).where(Garage.id == garage_id)) > 0

    # ── reminder windows ─────────────────────────────────────────────────────

    def reminder_windows(self, garage_ids: list[int]) -> dict[int, ReminderWindows]:
        """Resolved reminder thresholds per garage, unset columns filled from the defaults.

        Built once per reminder run and threaded into the MOT / VES / schedule streams —
        the same trick as ``VehicleRepository.latest_odometers`` — because one
        ``GET /api/reminders`` can span every garage the user belongs to, so the window has
        to be resolved per garage rather than once.
        """
        if not garage_ids:
            return {}
        rows = (
            self.session.execute(
                select(
                    Garage.id,
                    Garage.reminder_service_days,
                    Garage.reminder_service_km,
                    Garage.reminder_mot_days,
                    Garage.reminder_tax_days,
                ).where(Garage.id.in_(garage_ids))
            )
            .mappings()
            .all()
        )
        return {r["id"]: windows_from_row(r) for r in rows}

    def set_reminder_windows(
        self, garage_id: int, values: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Replace a garage's reminder-window columns and return the updated row."""
        self.session.execute(update(Garage).where(Garage.id == garage_id).values(**values))
        return self.get_by_id(garage_id)

    # ── membership ───────────────────────────────────────────────────────────

    def member_role(self, garage_id: int, user_id: int) -> str | None:
        """Return the user's role in a garage, or None if they aren't a member."""
        return self.session.scalars(
            select(GarageMember.role).where(
                GarageMember.garage_id == garage_id, GarageMember.user_id == user_id
            )
        ).first()

    def list_members(self, garage_id: int) -> list[dict[str, Any]]:
        """Return a garage's members with usernames, owners first."""
        rows = (
            self.session.execute(
                select(
                    GarageMember.user_id,
                    GarageMember.role,
                    GarageMember.created_at,
                    User.username,
                )
                .join(User, User.id == GarageMember.user_id)
                .where(GarageMember.garage_id == garage_id)
                .order_by(
                    case(
                        (GarageMember.role == "owner", 0),
                        (GarageMember.role == "member", 1),
                        else_=2,
                    ),
                    User.username,
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def add_member(self, garage_id: int, user_id: int, role: str) -> dict[str, Any]:
        """Add a user to a garage with the given role; returns the membership row."""
        self.session.add(GarageMember(garage_id=garage_id, user_id=user_id, role=role))
        self.session.flush()  # surfaces the unique (garage_id, user_id) IntegrityError
        member = (
            self.session.execute(
                select(
                    GarageMember.user_id,
                    GarageMember.role,
                    GarageMember.created_at,
                    User.username,
                )
                .join(User, User.id == GarageMember.user_id)
                .where(GarageMember.garage_id == garage_id, GarageMember.user_id == user_id)
            )
            .mappings()
            .first()
        )
        if member is None:  # pragma: no cover
            raise RuntimeError("Membership not found after INSERT")
        return dict(member)

    def set_member_role(self, garage_id: int, user_id: int, role: str) -> bool:
        """Change a member's role; return True if a membership row was updated."""
        return (
            self.affected(
                update(GarageMember)
                .where(GarageMember.garage_id == garage_id, GarageMember.user_id == user_id)
                .values(role=role)
            )
            > 0
        )

    def remove_member(self, garage_id: int, user_id: int) -> bool:
        """Remove a user from a garage; return True if a membership row was removed."""
        return (
            self.affected(
                delete(GarageMember).where(
                    GarageMember.garage_id == garage_id, GarageMember.user_id == user_id
                )
            )
            > 0
        )

    def accessible_garage_ids(self, user_id: int, is_admin: bool) -> list[int]:
        """Return garage IDs the user can see — all of them for site admins."""
        if is_admin:
            return list(self.session.scalars(select(Garage.id)).all())
        return list(
            self.session.scalars(
                select(GarageMember.garage_id).where(GarageMember.user_id == user_id)
            ).all()
        )
