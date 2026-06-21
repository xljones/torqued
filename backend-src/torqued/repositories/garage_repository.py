from typing import Any

from torqued.repositories.base import BaseRepository

ROLES = ("owner", "member", "readonly")


class GarageRepository(BaseRepository):
    def list_all(self) -> list[dict[str, Any]]:
        """Return every garage with vehicle and member counts (site-admin view)."""
        return self._rows(
            self.db.execute("""
            SELECT g.*,
                   (SELECT COUNT(*) FROM vehicles v WHERE v.garage_id = g.id) AS vehicle_count,
                   (SELECT COUNT(*) FROM garage_members m WHERE m.garage_id = g.id) AS member_count
            FROM garages g ORDER BY g.name
        """).fetchall()
        )

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return the garages a user belongs to, with their role and counts."""
        return self._rows(
            self.db.execute(
                """
                SELECT g.*, gm.role,
                       (SELECT COUNT(*) FROM vehicles v WHERE v.garage_id = g.id) AS vehicle_count,
                       (SELECT COUNT(*) FROM garage_members m
                        WHERE m.garage_id = g.id) AS member_count
                FROM garages g JOIN garage_members gm ON gm.garage_id = g.id
                WHERE gm.user_id = ? ORDER BY g.name
                """,
                (user_id,),
            ).fetchall()
        )

    def get_by_id(self, garage_id: int) -> dict[str, Any] | None:
        """Return a single garage by primary key, or None if not found."""
        return self._row(
            self.db.execute("SELECT * FROM garages WHERE id=?", (garage_id,)).fetchone()
        )

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        """Return a garage by name (case-insensitive), or None if not found."""
        return self._row(
            self.db.execute(
                "SELECT * FROM garages WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()
        )

    def create(self, name: str) -> dict[str, Any]:
        """Insert a new garage and return it."""
        inserted = self.db.execute(
            "INSERT INTO garages (name) VALUES (?) RETURNING id", (name,)
        ).fetchone()
        if inserted is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        garage = self.get_by_id(inserted["id"])
        if garage is None:  # pragma: no cover
            raise RuntimeError(f"Row {inserted['id']} not found after INSERT")
        return garage

    def rename(self, garage_id: int, name: str) -> dict[str, Any] | None:
        """Rename a garage and return the updated row."""
        self.db.execute("UPDATE garages SET name=? WHERE id=?", (name, garage_id))
        return self.get_by_id(garage_id)

    def delete(self, garage_id: int) -> bool:
        """Delete a garage (cascades to members and vehicles); True if a row was removed."""
        return self.db.execute("DELETE FROM garages WHERE id=?", (garage_id,)).rowcount > 0

    # ── membership ───────────────────────────────────────────────────────────

    def member_role(self, garage_id: int, user_id: int) -> str | None:
        """Return the user's role in a garage, or None if they aren't a member."""
        r = self.db.execute(
            "SELECT role FROM garage_members WHERE garage_id=? AND user_id=?",
            (garage_id, user_id),
        ).fetchone()
        return r["role"] if r else None

    def list_members(self, garage_id: int) -> list[dict[str, Any]]:
        """Return a garage's members with usernames, owners first."""
        return self._rows(
            self.db.execute(
                """
                SELECT gm.user_id, gm.role, gm.created_at, u.username
                FROM garage_members gm JOIN users u ON u.id = gm.user_id
                WHERE gm.garage_id = ?
                ORDER BY CASE gm.role WHEN 'owner' THEN 0 WHEN 'member' THEN 1 ELSE 2 END,
                         u.username
                """,
                (garage_id,),
            ).fetchall()
        )

    def add_member(self, garage_id: int, user_id: int, role: str) -> dict[str, Any]:
        """Add a user to a garage with the given role; returns the membership row."""
        self.db.execute(
            "INSERT INTO garage_members (garage_id, user_id, role) VALUES (?,?,?)",
            (garage_id, user_id, role),
        )
        member = self._row(
            self.db.execute(
                """
                SELECT gm.user_id, gm.role, gm.created_at, u.username
                FROM garage_members gm JOIN users u ON u.id = gm.user_id
                WHERE gm.garage_id=? AND gm.user_id=?
                """,
                (garage_id, user_id),
            ).fetchone()
        )
        if member is None:  # pragma: no cover
            raise RuntimeError("Membership not found after INSERT")
        return member

    def set_member_role(self, garage_id: int, user_id: int, role: str) -> bool:
        """Change a member's role; return True if a membership row was updated."""
        return (
            self.db.execute(
                "UPDATE garage_members SET role=? WHERE garage_id=? AND user_id=?",
                (role, garage_id, user_id),
            ).rowcount
            > 0
        )

    def remove_member(self, garage_id: int, user_id: int) -> bool:
        """Remove a user from a garage; return True if a membership row was removed."""
        return (
            self.db.execute(
                "DELETE FROM garage_members WHERE garage_id=? AND user_id=?",
                (garage_id, user_id),
            ).rowcount
            > 0
        )

    def accessible_garage_ids(self, user_id: int, is_admin: bool) -> list[int]:
        """Return garage IDs the user can see — all of them for site admins."""
        if is_admin:
            return [r["id"] for r in self.db.execute("SELECT id FROM garages").fetchall()]
        return [
            r["garage_id"]
            for r in self.db.execute(
                "SELECT garage_id FROM garage_members WHERE user_id=?", (user_id,)
            ).fetchall()
        ]
