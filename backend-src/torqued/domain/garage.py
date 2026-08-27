from dataclasses import dataclass


@dataclass
class Garage:
    id: int
    name: str
    # Per-garage reminder "due soon" windows; None → the torqued.reminders default.
    reminder_service_days: int | None = None
    reminder_service_km: float | None = None
    reminder_service_unit: str | None = None
    reminder_mot_days: int | None = None
    reminder_tax_days: int | None = None
    created_at: str | None = None
