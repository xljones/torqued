from dataclasses import dataclass


@dataclass
class Vehicle:
    id: int
    name: str
    kind: str = "car"
    make: str | None = None
    model: str | None = None
    year: int | None = None
    registration: str | None = None
    vin: str | None = None
    colour: str | None = None
    fuel_type: str | None = None
    odometer_unit: str = "mi"
    purchase_date: str | None = None
    tyre_size_front: str | None = None
    tyre_size_rear: str | None = None
    tyre_pressure_front_psi: float | None = None
    tyre_pressure_rear_psi: float | None = None
    notes: str | None = None
    archived: bool = False
    created_at: str | None = None
    updated_at: str | None = None
