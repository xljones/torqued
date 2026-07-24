from dataclasses import dataclass
from enum import StrEnum


class ScheduleKind(StrEnum):
    """The known kinds of service schedule. A ``StrEnum`` so members compare equal to
    (and store as) their plain string value, matching the TEXT ``kind`` column."""

    MINOR = "minor"
    MAJOR = "major"
    CUSTOM = "custom"


@dataclass
class ServiceSchedule:
    id: int
    vehicle_id: int
    kind: ScheduleKind
    name: str | None = None
    interval_months: int | None = None
    interval_km: float | None = None
    enabled: int = 1
    created_at: str | None = None
    updated_at: str | None = None
