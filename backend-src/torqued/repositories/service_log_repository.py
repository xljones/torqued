from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, and_, delete, func, or_, select, update
from sqlalchemy.orm import aliased

from torqued import dtc
from torqued.db import utcnow_text
from torqued.models import (
    Garage,
    Photo,
    ServiceLog,
    ServiceLogFaultCode,
    ServiceLogHistory,
    ServiceLogServiceSchedule,
    User,
    Vehicle,
    to_dict,
)
from torqued.reminders import DEFAULT_WINDOWS
from torqued.repositories.base import BaseRepository

SERVICE_FIELDS: list[str] = [
    "vehicle_id",
    "date",
    "title",
    "category",
    "description",
    "performed_by",
    "cost",
    "odometer_km",
    "odometer_unit",
    "next_due_date",
    "next_due_km",
]



def _log_select() -> Select[Any]:
    """Base query: each service log joined to its vehicle, plus a per-log photo count."""
    photo_count = (
        select(func.count())
        .select_from(Photo)
        .where(Photo.service_log_id == ServiceLog.id)
        .correlate(ServiceLog)
    ).scalar_subquery()
    return select(
        ServiceLog,
        Vehicle.name.label("vehicle_name"),
        Vehicle.kind.label("vehicle_kind"),
        Vehicle.garage_id,
        Vehicle.odometer_unit.label("vehicle_odometer_unit"),
        photo_count.label("photo_count"),
    ).join(Vehicle, Vehicle.id == ServiceLog.vehicle_id)


def _log_dict(row: Any) -> dict[str, Any]:
    """Flatten a _log_select() result row into the dict shape routes expect."""
    log, vehicle_name, vehicle_kind, garage_id, vehicle_odometer_unit, photo_count = row
    return {
        **to_dict(log),
        "vehicle_name": vehicle_name,
        "vehicle_kind": vehicle_kind,
        "garage_id": garage_id,
        "vehicle_odometer_unit": vehicle_odometer_unit,
        "photo_count": photo_count,
    }


class ServiceLogRepository(BaseRepository):
    def _fault_codes_for_logs(self, log_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        """Batch-load fault codes for a set of service log IDs."""
        if not log_ids:
            return {}
        rows = (
            self.session.execute(
                select(ServiceLogFaultCode.service_log_id, ServiceLogFaultCode.code)
                .where(ServiceLogFaultCode.service_log_id.in_(log_ids))
                .order_by(ServiceLogFaultCode.id)
            )
            .mappings()
            .all()
        )
        result: dict[int, list[dict[str, Any]]] = {}
        for r in rows:
            detail = dtc.lookup(r["code"])
            entry: dict[str, Any] = {"code": r["code"]}
            if detail and detail.get("description"):
                entry["description"] = detail["description"]
                entry["system"] = detail["system"]
            result.setdefault(r["service_log_id"], []).append(entry)
        return result

    def _attach_fault_codes(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach fault_codes list to each log dict."""
        codes_map = self._fault_codes_for_logs([log["id"] for log in logs])
        for log in logs:
            log["fault_codes"] = codes_map.get(log["id"], [])
        return logs

    def _replace_fault_codes(self, log_id: int, codes: list[str]) -> None:
        """Delete and re-insert fault codes for a service log."""
        self.session.execute(
            delete(ServiceLogFaultCode).where(ServiceLogFaultCode.service_log_id == log_id)
        )
        for code in codes:
            stripped = code.strip().upper()
            if stripped:
                self.session.add(ServiceLogFaultCode(service_log_id=log_id, code=stripped))

    def _schedule_ids_for_logs(self, log_ids: list[int]) -> dict[int, list[int]]:
        """Batch-load the fulfilled-schedule ids for a set of service log IDs."""
        rows = self.session.execute(
            select(
                ServiceLogServiceSchedule.service_log_id,
                ServiceLogServiceSchedule.service_schedule_id,
            )
            .where(ServiceLogServiceSchedule.service_log_id.in_(log_ids))
            .order_by(ServiceLogServiceSchedule.service_schedule_id)
        ).all()
        result: dict[int, list[int]] = {}
        for log_id, schedule_id in rows:
            result.setdefault(log_id, []).append(schedule_id)
        return result

    def _replace_schedule_links(self, log_id: int, schedule_ids: list[int]) -> None:
        """Delete and re-insert the schedule links for a service log (deduped)."""
        self.session.execute(
            delete(ServiceLogServiceSchedule).where(
                ServiceLogServiceSchedule.service_log_id == log_id
            )
        )
        for schedule_id in dict.fromkeys(schedule_ids):  # preserve order, drop dups
            self.session.add(
                ServiceLogServiceSchedule(service_log_id=log_id, service_schedule_id=schedule_id)
            )

    def list_for_garages(self, garage_ids: list[int]) -> list[dict[str, Any]]:
        """Return the garages' service logs across vehicles, newest first."""
        if not garage_ids:
            return []
        rows = self.session.execute(
            _log_select()
            .where(Vehicle.garage_id.in_(garage_ids))
            .order_by(ServiceLog.date.desc(), ServiceLog.id.desc())
        ).all()
        return self._attach_fault_codes([_log_dict(r) for r in rows])

    def list_for_vehicle(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return a vehicle's service logs, newest first."""
        rows = self.session.execute(
            _log_select()
            .where(ServiceLog.vehicle_id == vehicle_id)
            .order_by(ServiceLog.date.desc(), ServiceLog.id.desc())
        ).all()
        return self._attach_fault_codes([_log_dict(r) for r in rows])

    def get_by_id(self, log_id: int) -> dict[str, Any] | None:
        """Return a single service log with vehicle info, photos, and fault codes."""
        row = self.session.execute(_log_select().where(ServiceLog.id == log_id)).first()
        if row is None:
            return None
        log = _log_dict(row)
        photo_rows = self.session.execute(
            select(Photo, User.username.label("uploaded_by_username"))
            .outerjoin(User, User.id == Photo.uploaded_by)
            .where(Photo.service_log_id == log_id)
            .order_by(Photo.created_at.desc(), Photo.id.desc())
        ).all()
        log["photos"] = [
            {**to_dict(photo), "uploaded_by_username": username} for photo, username in photo_rows
        ]
        self._attach_fault_codes([log])
        log["service_schedule_ids"] = self._schedule_ids_for_logs([log_id]).get(log_id, [])
        return log

    def create(self, data: dict[str, Any], changed_by: int | None = None) -> dict[str, Any]:
        """Insert a new service log and record its initial history snapshot."""
        log_row = ServiceLog(**{f: data.get(f) for f in SERVICE_FIELDS})
        self.session.add(log_row)
        self.session.flush()
        fault_codes = data.get("fault_codes") or []
        if fault_codes:
            self._replace_fault_codes(log_row.id, fault_codes)
        if data.get("service_schedule_ids"):
            self._replace_schedule_links(log_row.id, data["service_schedule_ids"])
        log = self.get_by_id(log_row.id)
        if log is None:  # pragma: no cover
            raise RuntimeError(f"Row {log_row.id} not found after INSERT")
        self._record_history(log, changed_by)
        return log

    def update(
        self, log_id: int, data: dict[str, Any], changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Update service log fields, record a history snapshot, and return the updated log."""
        values = {f: data.get(f) for f in SERVICE_FIELDS if f != "vehicle_id"}
        values["updated_at"] = utcnow_text()
        self.session.execute(update(ServiceLog).where(ServiceLog.id == log_id).values(values))
        if "fault_codes" in data:
            self._replace_fault_codes(log_id, data["fault_codes"] or [])
        if "service_schedule_ids" in data:
            self._replace_schedule_links(log_id, data["service_schedule_ids"] or [])
        log = self.get_by_id(log_id)
        if log is not None:
            self._record_history(log, changed_by)
        return log

    def delete(self, log_id: int) -> bool:
        """Delete a service log by primary key; return True if a row was removed."""
        return self.affected(delete(ServiceLog).where(ServiceLog.id == log_id)) > 0

    def get_history(self, log_id: int) -> list[dict[str, Any]]:
        """Return full audit history for a service log, newest first, with username."""
        rows = self.session.execute(
            select(ServiceLogHistory, User.username.label("changed_by_username"))
            .outerjoin(User, User.id == ServiceLogHistory.changed_by)
            .where(ServiceLogHistory.service_log_id == log_id)
            .order_by(ServiceLogHistory.changed_at.desc(), ServiceLogHistory.id.desc())
        ).all()
        return [{**to_dict(h), "changed_by_username": username} for h, username in rows]

    def revert(
        self, log_id: int, version_id: int, changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Restore a service log from a history record; return None if it doesn't exist."""
        h = self.session.execute(
            select(ServiceLogHistory).where(
                ServiceLogHistory.id == version_id, ServiceLogHistory.service_log_id == log_id
            )
        ).scalar_one_or_none()
        if h is None:
            return None
        return self.update(log_id, to_dict(h), changed_by=changed_by)

    def _record_history(self, log: dict[str, Any], changed_by: int | None) -> None:
        """Write a snapshot of the service log's current field values to history."""
        self.session.add(
            ServiceLogHistory(
                service_log_id=log["id"],
                changed_by=changed_by,
                **{f: log.get(f) for f in SERVICE_FIELDS},
            )
        )

    def reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return open maintenance reminders, most urgent first.

        A service log with a next_due_date or next_due_km creates a reminder. The
        reminder is closed once a newer log exists for the same vehicle and category.
        Status is 'overdue', 'due_soon' (within the owning garage's service window of
        today / the vehicle's latest odometer reading — see torqued.reminders), or
        'upcoming'. Each carries type='service'.

        MOT-expiry reminders (type='mot') are merged in alongside, so a vehicle's
        upcoming or lapsed MOT surfaces here too.
        """
        today = today or date.today()
        if not garage_ids:
            return []
        newer = aliased(ServiceLog)
        newer_exists = (
            select(newer.id)
            .where(
                newer.vehicle_id == ServiceLog.vehicle_id,
                or_(
                    newer.category == ServiceLog.category,
                    and_(newer.category.is_(None), ServiceLog.category.is_(None)),
                ),
                or_(
                    newer.date > ServiceLog.date,
                    and_(newer.date == ServiceLog.date, newer.id > ServiceLog.id),
                ),
            )
            .correlate(ServiceLog)
            .exists()
        )
        stmt = (
            select(
                ServiceLog,
                Vehicle.name.label("vehicle_name"),
                Vehicle.kind.label("vehicle_kind"),
                Vehicle.garage_id,
                Vehicle.odometer_unit.label("vehicle_odometer_unit"),
            )
            .join(Vehicle, Vehicle.id == ServiceLog.vehicle_id)
            .where(
                or_(ServiceLog.next_due_date.is_not(None), ServiceLog.next_due_km.is_not(None)),
                Vehicle.archived == 0,
                Vehicle.garage_id.in_(garage_ids),
                ~newer_exists,
            )
            .order_by(ServiceLog.next_due_date.asc())
        )
        if vehicle_id is not None:
            stmt = stmt.where(ServiceLog.vehicle_id == vehicle_id)
        candidates = [
            {
                **to_dict(log),
                "vehicle_name": vehicle_name,
                "vehicle_kind": vehicle_kind,
                "garage_id": garage_id,
                "vehicle_odometer_unit": vehicle_odometer_unit,
            }
            for log, vehicle_name, vehicle_kind, garage_id, vehicle_odometer_unit in (
                self.session.execute(stmt).all()
            )
        ]
        from torqued.repositories.garage_repository import GarageRepository
        from torqued.repositories.vehicle_repository import VehicleRepository

        latest = VehicleRepository(self.session).latest_odometers()
        windows = GarageRepository(self.session).reminder_windows(garage_ids)
        reminders = []
        for s in candidates:
            # Each garage sets its own window, so the cutoff is per candidate, not hoisted.
            w = windows.get(s["garage_id"], DEFAULT_WINDOWS)
            soon_cutoff = (today + timedelta(days=w.service_days)).isoformat()
            current_km = (latest.get(s["vehicle_id"]) or {}).get("odometer_km")
            status = "upcoming"
            km_remaining = None
            if s["next_due_km"] is not None and current_km is not None:
                km_remaining = s["next_due_km"] - current_km
            overdue = (
                s["next_due_date"] is not None and s["next_due_date"] < today.isoformat()
            ) or (km_remaining is not None and km_remaining <= 0)
            due_soon = (
                s["next_due_date"] is not None and s["next_due_date"] <= soon_cutoff
            ) or (km_remaining is not None and km_remaining <= w.service_km)
            if overdue:
                status = "overdue"
            elif due_soon:
                status = "due_soon"
            reminders.append(
                {**s, "type": "service", "status": status, "km_remaining": km_remaining}
            )
        from torqued.repositories.mot_repository import MotRepository
        from torqued.repositories.service_schedule_repository import ServiceScheduleRepository
        from torqued.repositories.ves_repository import VesRepository

        reminders.extend(
            MotRepository(self.session).reminders(
                garage_ids, vehicle_id=vehicle_id, today=today, windows=windows
            )
        )
        reminders.extend(
            VesRepository(self.session).reminders(
                garage_ids, vehicle_id=vehicle_id, today=today, windows=windows
            )
        )
        reminders.extend(
            ServiceScheduleRepository(self.session).reminders(
                garage_ids, vehicle_id=vehicle_id, today=today, latest=latest, windows=windows
            )
        )
        order = {"overdue": 0, "due_soon": 1, "upcoming": 2}
        reminders.sort(key=lambda r: (order[r["status"]], r["next_due_date"] or "9999-12-31"))
        return reminders

    def search(self, query: str, garage_ids: list[int]) -> list[dict[str, Any]]:
        """Return up to 10 in-scope service logs matching title, description, or performer."""
        if not garage_ids:
            return []
        like = f"%{query}%"
        rows = self.session.execute(
            _log_select()
            .where(
                Vehicle.garage_id.in_(garage_ids),
                or_(
                    func.lower(ServiceLog.title).like(func.lower(like)),
                    func.lower(ServiceLog.description).like(func.lower(like)),
                    func.lower(ServiceLog.category).like(func.lower(like)),
                    func.lower(ServiceLog.performed_by).like(func.lower(like)),
                ),
            )
            .limit(10)
        ).all()
        return [_log_dict(r) for r in rows]

    def performers(self, garage_ids: list[int]) -> list[str]:
        """Return distinct in-scope 'performed_by' values for autocomplete suggestions."""
        if not garage_ids:
            return []
        values = self.session.scalars(
            select(ServiceLog.performed_by)
            .join(Vehicle, Vehicle.id == ServiceLog.vehicle_id)
            .where(
                Vehicle.garage_id.in_(garage_ids),
                ServiceLog.performed_by.is_not(None),
                ServiceLog.performed_by != "",
            )
            .distinct()
            .order_by(ServiceLog.performed_by)
        ).all()
        return [p for p in values if p is not None]

    def export_flat(
        self, garage_ids: list[int], vehicle_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Return flat in-scope export rows for service logs, optionally for one vehicle."""
        if not garage_ids:
            return []
        stmt = (
            select(
                Garage.name.label("garage"),
                Vehicle.name.label("vehicle"),
                Vehicle.make,
                Vehicle.model,
                Vehicle.registration,
                ServiceLog.date,
                ServiceLog.title,
                ServiceLog.category,
                ServiceLog.description,
                ServiceLog.performed_by,
                ServiceLog.cost,
                ServiceLog.odometer_km,
                ServiceLog.odometer_unit,
                ServiceLog.next_due_date,
                ServiceLog.next_due_km,
                ServiceLog.created_at,
            )
            .join(Vehicle, Vehicle.id == ServiceLog.vehicle_id)
            .join(Garage, Garage.id == Vehicle.garage_id)
            .where(Vehicle.garage_id.in_(garage_ids))
            .order_by(Vehicle.name.asc(), ServiceLog.date.desc(), ServiceLog.id.desc())
        )
        if vehicle_id is not None:
            stmt = stmt.where(ServiceLog.vehicle_id == vehicle_id)
        return [dict(r) for r in self.session.execute(stmt).mappings().all()]
