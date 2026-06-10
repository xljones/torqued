from typing import Any

from torqued.repositories.base import BaseRepository


class PhotoRepository(BaseRepository):
    def get_by_id(self, photo_id: int) -> dict[str, Any] | None:
        """Return a single photo record by primary key, or None if not found."""
        return self._row(self.db.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone())

    def create(
        self,
        vehicle_id: int,
        filename: str,
        original_name: str | None = None,
        caption: str | None = None,
        service_log_id: int | None = None,
        uploaded_by: int | None = None,
    ) -> dict[str, Any]:
        """Insert a photo record for an already-saved upload file."""
        cur = self.db.execute(
            "INSERT INTO photos (vehicle_id, service_log_id, filename, original_name,"
            " caption, uploaded_by) VALUES (?,?,?,?,?,?)",
            (vehicle_id, service_log_id, filename, original_name, caption, uploaded_by),
        )
        row_id = cur.lastrowid
        if row_id is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        photo = self.get_by_id(row_id)
        if photo is None:  # pragma: no cover
            raise RuntimeError(f"Row {row_id} not found after INSERT")
        return photo

    def update_caption(self, photo_id: int, caption: str | None) -> dict[str, Any] | None:
        """Update a photo's caption and return the updated record."""
        self.db.execute("UPDATE photos SET caption=? WHERE id=?", (caption, photo_id))
        return self.get_by_id(photo_id)

    def delete(self, photo_id: int) -> bool:
        """Delete a photo record by primary key; return True if a row was removed."""
        return self.db.execute("DELETE FROM photos WHERE id=?", (photo_id,)).rowcount > 0
