"""Maintenance reminder thresholds.

A reminder is 'overdue' once its due date or mileage has passed, 'due_soon' (amber; counted
by the dashboard's "Maintenance due" stat) once it falls inside its window, and 'upcoming'
beyond that — nothing is ever filtered out server-side.

The window is per garage: each ``garages.reminder_*`` column (migration 0009) is NULL until
the garage sets one, in which case the default below applies. Resolving happens once per
reminder run — :meth:`GarageRepository.reminder_windows` builds the map that
:meth:`ServiceLogRepository.reminders` threads through every stream — because a single
``GET /api/reminders`` can span every garage the user belongs to.
"""
from dataclasses import dataclass
from typing import Any

from torqued.units import to_km

# Service and schedule reminders: a month, or 2,000 miles. The distance does the work here
# — 500 km was barely a fortnight's driving — while a month ahead is enough notice to book
# something in.
DEFAULT_SERVICE_DAYS = 30
DEFAULT_SERVICE_KM = to_km(2000.0, "mi")
DEFAULT_SERVICE_UNIT = "mi"
# The MOT (~2 months) and road tax (~1 month) keep their historic windows.
DEFAULT_MOT_DAYS = 60
DEFAULT_TAX_DAYS = 30


@dataclass(frozen=True)
class ReminderWindows:
    """A garage's resolved thresholds — every field concrete, no None."""

    service_days: int
    service_km: float
    mot_days: int
    tax_days: int


DEFAULT_WINDOWS = ReminderWindows(
    service_days=DEFAULT_SERVICE_DAYS,
    service_km=DEFAULT_SERVICE_KM,
    mot_days=DEFAULT_MOT_DAYS,
    tax_days=DEFAULT_TAX_DAYS,
)


def windows_from_row(row: Any) -> ReminderWindows:
    """Resolve a garages row's reminder columns, filling unset ones from the defaults."""
    return ReminderWindows(
        service_days=row["reminder_service_days"] or DEFAULT_SERVICE_DAYS,
        service_km=(
            DEFAULT_SERVICE_KM
            if row["reminder_service_km"] is None
            else row["reminder_service_km"]
        ),
        mot_days=row["reminder_mot_days"] or DEFAULT_MOT_DAYS,
        tax_days=row["reminder_tax_days"] or DEFAULT_TAX_DAYS,
    )
