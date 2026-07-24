from dataclasses import dataclass


@dataclass
class ServiceLog:
    id: int
    vehicle_id: int
    date: str
    title: str
    category: str | None = None
    description: str | None = None
    performed_by: str | None = None
    cost: float | None = None
    odometer_km: float | None = None
    odometer_unit: str | None = None
    next_due_date: str | None = None
    next_due_km: float | None = None
    service_schedule_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
