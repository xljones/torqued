from typing import Any

from torqued.models import Photo, to_dict
from torqued.repositories.base import BaseRepository


class PhotoRepository(BaseRepository):
    def get_by_id(self, photo_id: int) -> dict[str, Any] | None:
        """Return a single photo record by primary key, or None if not found."""
        photo = self.session.get(Photo, photo_id)
        return to_dict(photo) if photo else None

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
        photo = Photo(
            vehicle_id=vehicle_id,
            service_log_id=service_log_id,
            filename=filename,
            original_name=original_name,
            caption=caption,
            uploaded_by=uploaded_by,
        )
        self.session.add(photo)
        self.session.flush()  # assigns the primary key and emits the INSERT
        self.session.refresh(photo)  # pull DB-side default (created_at)
        return to_dict(photo)

    def update_caption(self, photo_id: int, caption: str | None) -> dict[str, Any] | None:
        """Update a photo's caption and return the updated record."""
        photo = self.session.get(Photo, photo_id)
        if photo is None:
            return None
        photo.caption = caption
        self.session.flush()
        return to_dict(photo)

    def delete(self, photo_id: int) -> bool:
        """Delete a photo record by primary key; return True if a row was removed."""
        photo = self.session.get(Photo, photo_id)
        if photo is None:
            return False
        self.session.delete(photo)
        return True
