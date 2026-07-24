from dataclasses import dataclass


@dataclass
class ServiceSchedule:
    id: int
    vehicle_id: int
    kind: str
    name: str | None = None
    interval_months: int | None = None
    interval_km: float | None = None
    enabled: int = 1
    created_at: str | None = None
    updated_at: str | None = None
