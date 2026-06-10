import sqlite3
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash


class UserRepository:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def get_by_id(self, user_id: int) -> dict[str, Any] | None:
        """Return a user by their primary key (excluding password_hash), or None if not found."""
        r = self.db.execute(
            "SELECT id, username, is_readonly, is_admin, "
            "expires_at, created_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if r:
            d = dict(r)
            d["is_readonly"] = bool(d["is_readonly"])
            d["is_admin"] = bool(d["is_admin"])
            return d
        return None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        """Return a user by username (case-insensitive) including password_hash, or None."""
        r = self.db.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone()
        return dict(r) if r else None

    def list_all(self) -> list[dict[str, Any]]:
        """Return all users (excluding password_hash), ordered by creation date ascending."""
        rows = self.db.execute(
            "SELECT id, username, is_readonly, is_admin, expires_at, created_at "
            "FROM users ORDER BY created_at"
        ).fetchall()
        return [
            {**dict(r), "is_readonly": bool(r["is_readonly"]), "is_admin": bool(r["is_admin"])}
            for r in rows
        ]

    def create(
        self,
        username: str,
        password: str,
        is_readonly: bool = False,
        is_admin: bool = False,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        """Insert a new user with a hashed password and return the created user (no hash)."""
        cur = self.db.execute(
            "INSERT INTO users (username, password_hash, is_readonly, "
            "is_admin, expires_at) VALUES (?,?,?,?,?)",
            (
                username,
                generate_password_hash(password),
                int(is_readonly),
                int(is_admin),
                expires_at,
            ),
        )
        row_id = cur.lastrowid
        if row_id is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        user = self.get_by_id(row_id)
        if user is None:  # pragma: no cover
            raise RuntimeError(f"Row {row_id} not found after INSERT")
        return user

    def rename(self, user_id: int, new_username: str) -> None:
        """Update a user's username."""
        self.db.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))

    def delete(self, user_id: int) -> bool:
        """Delete a user by their primary key; return True if a row was removed."""
        return self.db.execute("DELETE FROM users WHERE id=?", (user_id,)).rowcount > 0

    def verify_password(self, username: str, password: str) -> dict[str, Any] | None:
        """Return the user if username and password match, or None if authentication fails."""
        user = self.get_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            return user
        return None

    def change_password(
        self,
        user_id: int,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Verify current_password, update to new_password; return False if wrong."""
        row = self.db.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], current_password):
            return False
        self.db.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new_password), user_id),
        )
        return True
