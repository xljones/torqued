from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from torqued.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def get_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Return a user by their primary key (excluding password_hash), or None if not found."""
        r = self.execute(
            "SELECT id, username, is_admin, expires_at, created_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if r:
            d = dict(r)
            d["is_admin"] = bool(d["is_admin"])
            return d
        return None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a user by username (case-insensitive) including password_hash, or None."""
        r = self.execute(
            "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username,)
        ).fetchone()
        return dict(r) if r else None

    def list_all(self) -> list[dict[str, Any]]:
        """Return all users (excluding password_hash) with their garage memberships."""
        rows = self.execute(
            "SELECT id, username, is_admin, expires_at, created_at FROM users ORDER BY created_at"
        ).fetchall()
        users = [{**dict(r), "is_admin": bool(r["is_admin"])} for r in rows]
        memberships = self.execute("""
            SELECT gm.user_id, gm.garage_id, gm.role, g.name AS garage_name
            FROM garage_members gm JOIN garages g ON g.id = gm.garage_id
            ORDER BY g.name
        """).fetchall()
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
        rows = self.execute(
            """
            SELECT gm.garage_id, gm.role, g.name AS garage_name
            FROM garage_members gm JOIN garages g ON g.id = gm.garage_id
            WHERE gm.user_id = ? ORDER BY g.name
            """,
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def create(
        self,
        username: str,
        password: str,
        is_admin: bool = False,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new user with a hashed password and return the created user (no hash)."""
        inserted = self.execute(
            "INSERT INTO users (username, password_hash, is_admin, expires_at)"
            " VALUES (?,?,?,?) RETURNING id",
            (username, generate_password_hash(password), int(is_admin), expires_at),
        ).fetchone()
        if inserted is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        user = self.get_by_id(inserted["id"])
        if user is None:  # pragma: no cover
            raise RuntimeError(f"Row {inserted['id']} not found after INSERT")
        return user

    def rename(self, user_id: int, new_username: str) -> None:
        """Update a user's username."""
        self.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))

    def delete(self, user_id: int) -> bool:
        """Delete a user by their primary key; return True if a row was removed."""
        return self.execute("DELETE FROM users WHERE id=?", (user_id,)).rowcount > 0

    def verify_password(self, username: str, password: str) -> dict[str, Any] | None:
        """Return the user if username and password match, or None if authentication fails."""
        user = self.get_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            return user
        return None

    def set_password(self, user_id: int, new_password: str) -> None:
        """Overwrite a user's password without verifying the current one (admin reset)."""
        self.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new_password), user_id),
        )

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Verify current_password, update to new_password; return False if wrong."""
        row = self.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], current_password):
            return False
        self.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new_password), user_id),
        )
        return True
