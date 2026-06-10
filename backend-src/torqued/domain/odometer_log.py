from dataclasses import dataclass


@dataclass
class OdometerLog:
    id: int
    vehicle_id: int
    date: str
    odometer_km: float
    unit: str = "mi"
    note: str | None = None
    created_at: str | None = None
