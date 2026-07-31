from dataclasses import dataclass


@dataclass
class Photo:
    id: int
    vehicle_id: int
    filename: str
    service_log_id: int | None = None
    original_name: str | None = None
    caption: str | None = None
    uploaded_by: int | None = None
    cover_focal_x: float | None = None
    cover_focal_y: float | None = None
    cover_zoom: float | None = None
    created_at: str | None = None
