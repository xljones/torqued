from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import aliased

from torqued.db import utcnow_text
from torqued.domain.service_schedule import ScheduleKind
from torqued.models import (
    ServiceLog,
    ServiceLogServiceSchedule,
    ServiceSchedule,
    Vehicle,
    to_dict,
)
from torqued.repositories.base import BaseRepository

# Persisted schedule columns (id/created_at/updated_at are managed by the DB / here).
SCHEDULE_FIELDS: list[str] = [
    "vehicle_id",
    "kind",
    "name",
    "interval_months",
    "interval_km",
    "enabled",
]

# The recognised schedule kinds (from the ScheduleKind enum). A vehicle typically has one
# 'minor' and one 'major' schedule plus any number of user-named 'custom' ones — but
# nothing here enforces uniqueness; the routes validate the kind and the UI shapes the rest.
KINDS = tuple(ScheduleKind)

_KIND_LABELS = {ScheduleKind.MINOR: "Minor service", ScheduleKind.MAJOR: "Major service"}


def schedule_title(schedule: dict[str, Any]) -> str:
    """A display title for a schedule: its name if set, else a label for its kind."""
    name = (schedule.get("name") or "").strip()
    if name:
        return name
    return _KIND_LABELS.get(schedule["kind"], "Service")


def add_months(iso_date: str, months: int) -> str:
    """Return the ISO date `months` after `iso_date`, clamping to the month's last day."""
    d = date.fromisoformat(iso_date[:10])
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day).isoformat()


class ServiceScheduleRepository(BaseRepository):
    def list_for_vehicle(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return a vehicle's service schedules, minor/major first then by creation."""
        rows = self.session.scalars(
            select(ServiceSchedule)
            .where(ServiceSchedule.vehicle_id == vehicle_id)
            .order_by(ServiceSchedule.kind.asc(), ServiceSchedule.id.asc())
        ).all()
        return [to_dict(s) for s in rows]

    def get_by_id(self, schedule_id: int) -> dict[str, Any] | None:
        """Return a single schedule with its vehicle's garage_id, or None."""
        row = self.session.execute(
            select(ServiceSchedule, Vehicle.garage_id)
            .join(Vehicle, Vehicle.id == ServiceSchedule.vehicle_id)
            .where(ServiceSchedule.id == schedule_id)
        ).first()
        if row is None:
            return None
        schedule, garage_id = row
        return {**to_dict(schedule), "garage_id": garage_id}

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new schedule and return it."""
        row = ServiceSchedule(**{f: data[f] for f in SCHEDULE_FIELDS if f in data})
        self.session.add(row)
        self.session.flush()
        created = self.get_by_id(row.id)
        if created is None:  # pragma: no cover
            raise RuntimeError(f"Row {row.id} not found after INSERT")
        return created

    def update(self, schedule_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a schedule's fields (not vehicle_id) and return it, or None if gone."""
        values = {f: data[f] for f in SCHEDULE_FIELDS if f != "vehicle_id" and f in data}
        values["updated_at"] = utcnow_text()
        self.session.execute(
            update(ServiceSchedule).where(ServiceSchedule.id == schedule_id).values(values)
        )
        return self.get_by_id(schedule_id)

    def delete(self, schedule_id: int) -> bool:
        """Delete a schedule; return True if a row was removed.

        The join rows linking it to fulfilling service logs are removed by the join
        table's ``ON DELETE CASCADE`` (migration 0005); the service logs themselves stay.
        """
        return self.affected(delete(ServiceSchedule).where(ServiceSchedule.id == schedule_id)) > 0

    def reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
        latest: dict[int, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return schedule-derived reminders, shaped to merge with the other streams.

        For each enabled schedule the newest service log that fulfilled it (matching
        ``service_schedule_id``) is the anchor. The next due date is the anchor's date
        plus ``interval_months``; the next due mileage is the anchor's odometer plus
        ``interval_km``. A schedule with no fulfilling log — nothing to project from —
        yields no reminder, as does one that ends up with neither a due date nor a due
        mileage. Status is 'overdue' / 'due_soon' / 'upcoming' on the same thresholds as
        service-log reminders. Each carries type='schedule'.

        ``latest`` is the per-vehicle latest-odometer map from
        ``VehicleRepository.latest_odometers``; the orchestrating
        ``ServiceLogRepository.reminders`` passes in the one it already computed so the
        (fairly heavy) scan isn't repeated. Omitted → computed here for standalone use.
        """
        from torqued.repositories.service_log_repository import DUE_SOON_DAYS, DUE_SOON_KM

        today = today or date.today()
        if not garage_ids:
            return []
        # The anchor is the newest service log linked to this schedule (via the
        # many-to-many join table). A correlated subquery picks its id; a separate alias
        # joins that row so date and odometer come from the same record.
        newest = aliased(ServiceLog)
        link = aliased(ServiceLogServiceSchedule)
        newest_log = (
            select(newest.id)
            .join(link, link.service_log_id == newest.id)
            .where(link.service_schedule_id == ServiceSchedule.id)
            .order_by(newest.date.desc(), newest.id.desc())
            .limit(1)
            .correlate(ServiceSchedule)
            .scalar_subquery()
        )
        anchor = aliased(ServiceLog)
        stmt = (
            select(
                ServiceSchedule,
                Vehicle.name.label("vehicle_name"),
                Vehicle.kind.label("vehicle_kind"),
                Vehicle.garage_id,
                Vehicle.odometer_unit.label("vehicle_odometer_unit"),
                anchor.date.label("anchor_date"),
                anchor.odometer_km.label("anchor_km"),
            )
            .join(Vehicle, Vehicle.id == ServiceSchedule.vehicle_id)
            .outerjoin(anchor, anchor.id == newest_log)
            .where(
                ServiceSchedule.enabled == 1,
                Vehicle.archived == 0,
                Vehicle.garage_id.in_(garage_ids),
            )
        )
        if vehicle_id is not None:
            stmt = stmt.where(ServiceSchedule.vehicle_id == vehicle_id)
        rows = self.session.execute(stmt).all()

        if latest is None:
            from torqued.repositories.vehicle_repository import VehicleRepository

            latest = VehicleRepository(self.session).latest_odometers()
        soon_cutoff = (today + timedelta(days=DUE_SOON_DAYS)).isoformat()
        today_iso = today.isoformat()
        reminders: list[dict[str, Any]] = []
        for schedule, v_name, v_kind, garage_id, v_unit, anchor_date, anchor_km in rows:
            if anchor_date is None:
                continue  # no fulfilling log to project from
            next_due_date = (
                add_months(anchor_date, schedule.interval_months)
                if schedule.interval_months
                else None
            )
            next_due_km = (
                anchor_km + schedule.interval_km
                if schedule.interval_km and anchor_km is not None
                else None
            )
            if next_due_date is None and next_due_km is None:
                continue  # nothing to remind about
            current_km = (latest.get(schedule.vehicle_id) or {}).get("odometer_km")
            km_remaining = (
                next_due_km - current_km
                if next_due_km is not None and current_km is not None
                else None
            )
            overdue = (next_due_date is not None and next_due_date < today_iso) or (
                km_remaining is not None and km_remaining <= 0
            )
            due_soon = (next_due_date is not None and next_due_date <= soon_cutoff) or (
                km_remaining is not None and km_remaining <= DUE_SOON_KM
            )
            status = "overdue" if overdue else "due_soon" if due_soon else "upcoming"
            reminders.append(
                {
                    "type": "schedule",
                    "id": schedule.id,
                    "vehicle_id": schedule.vehicle_id,
                    "vehicle_name": v_name,
                    "vehicle_kind": v_kind,
                    "garage_id": garage_id,
                    "vehicle_odometer_unit": v_unit,
                    "title": schedule_title(to_dict(schedule)),
                    "category": None,
                    "date": anchor_date,
                    "next_due_date": next_due_date,
                    "next_due_km": next_due_km,
                    "km_remaining": km_remaining,
                    "status": status,
                }
            )
        return reminders
