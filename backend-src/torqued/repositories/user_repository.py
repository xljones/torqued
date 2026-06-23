from typing import Any

from sqlalchemy import delete, func, select, update
from werkzeug.security import check_password_hash, generate_password_hash

from torqued.models import Garage, GarageMember, User, to_dict
from torqued.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def get_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Return a user by their primary key (excluding password_hash), or None if not found."""
        user = self.session.get(User, user_id)
        if user is None:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "is_admin": bool(user.is_admin),
            "expires_at": user.expires_at,
            "created_at": user.created_at,
        }

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a user by username (case-insensitive) including password_hash, or None."""
        user = self.session.scalars(
            select(User).where(func.lower(User.username) == func.lower(username))
        ).first()
        return to_dict(user) if user else None

    def list_all(self) -> list[dict[str, Any]]:
        """Return all users (excluding password_hash) with their garage memberships."""
        rows = (
            self.session.execute(
                select(User.id, User.username, User.is_admin, User.expires_at, User.created_at)
                .order_by(User.created_at)
            )
            .mappings()
            .all()
        )
        users = [{**dict(r), "is_admin": bool(r["is_admin"])} for r in rows]
        memberships = (
            self.session.execute(
                select(
                    GarageMember.user_id,
                    GarageMember.garage_id,
                    GarageMember.role,
                    Garage.name.label("garage_name"),
                )
                .join(Garage, Garage.id == GarageMember.garage_id)
                .order_by(Garage.name)
            )
            .mappings()
            .all()
        )
        by_user: dict[int, list[dict[str, Any]]] = {}
        for m in memberships:
            by_user.setdefault(m["user_id"], []).append(
                {"garage_id": m["garage_id"], "garage_name": m["garage_name"], "role": m["role"]}
            )
        for u in users:
            u["memberships"] = by_user.get(u["id"], [])
        return users

    def memberships(self, user_id: int) -> list[dict[str, Any]]:
        """Return the user's garage memberships with garage names."""
        rows = (
            self.session.execute(
                select(GarageMember.garage_id, GarageMember.role, Garage.name.label("garage_name"))
                .join(Garage, Garage.id == GarageMember.garage_id)
                .where(GarageMember.user_id == user_id)
                .order_by(Garage.name)
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def create(
        self,
        username: str,
        password: str,
        is_admin: bool = False,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new user with a hashed password and return the created user (no hash)."""
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            is_admin=int(is_admin),
            expires_at=expires_at,
        )
        self.session.add(user)
        self.session.flush()  # assigns the PK and surfaces a duplicate-username IntegrityError
        created = self.get_by_id(user.id)
        if created is None:  # pragma: no cover
            raise RuntimeError(f"Row {user.id} not found after INSERT")
        return created

    def rename(self, user_id: int, new_username: str) -> None:
        """Update a user's username."""
        self.session.execute(update(User).where(User.id == user_id).values(username=new_username))

    def delete(self, user_id: int) -> bool:
        """Delete a user by their primary key; return True if a row was removed."""
        return self.affected(delete(User).where(User.id == user_id)) > 0

    def verify_password(self, username: str, password: str) -> dict[str, Any] | None:
        """Return the user if username and password match, or None if authentication fails."""
        user = self.get_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            return user
        return None

    def set_password(self, user_id: int, new_password: str) -> None:
        """Overwrite a user's password without verifying the current one (admin reset)."""
        self.session.execute(
            update(User).where(User.id == user_id).values(
                password_hash=generate_password_hash(new_password)
            )
        )

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Verify current_password, update to new_password; return False if wrong."""
        user = self.session.get(User, user_id)
        if user is None or not check_password_hash(user.password_hash, current_password):
            return False
        user.password_hash = generate_password_hash(new_password)
        self.session.flush()
        return True
