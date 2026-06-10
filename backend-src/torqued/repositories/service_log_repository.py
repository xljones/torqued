from datetime import date, timedelta
from typing import Any

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

# Reminder proximity thresholds: "due soon" within this window.
DUE_SOON_DAYS = 30
DUE_SOON_KM = 500.0

_VEHICLE_JOIN = """
    SELECT s.*, v.name AS vehicle_name, v.kind AS vehicle_kind,
           v.odometer_unit AS vehicle_odometer_unit,
           (SELECT COUNT(*) FROM photos p WHERE p.service_log_id = s.id) AS photo_count
    FROM service_logs s
    JOIN vehicles v ON v.id = s.vehicle_id
"""


class ServiceLogRepository(BaseRepository):
    def list_all(self) -> list[dict[str, Any]]:
        """Return all service logs across vehicles, newest first."""
        return self._rows(
            self.db.execute(f"{_VEHICLE_JOIN} ORDER BY s.date DESC, s.id DESC").fetchall()
        )

    def list_for_vehicle(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return a vehicle's service logs, newest first."""
        return self._rows(
            self.db.execute(
                f"{_VEHICLE_JOIN} WHERE s.vehicle_id=? ORDER BY s.date DESC, s.id DESC",
                (vehicle_id,),
            ).fetchall()
        )

    def get_by_id(self, log_id: int) -> dict[str, Any] | None:
        """Return a single service log with vehicle info and photos, or None if not found."""
        log = self._row(self.db.execute(f"{_VEHICLE_JOIN} WHERE s.id=?", (log_id,)).fetchone())
        if not log:
            return None
        log["photos"] = self._rows(
            self.db.execute(
                """
                SELECT p.*, u.username AS uploaded_by_username
                FROM photos p LEFT JOIN users u ON u.id = p.uploaded_by
                WHERE p.service_log_id=? ORDER BY p.created_at DESC, p.id DESC
                """,
                (log_id,),
            ).fetchall()
        )
        return log

    def create(self, data: dict[str, Any], changed_by: int | None = None) -> dict[str, Any]:
        """Insert a new service log and record its initial history snapshot."""
        cols = ",".join(SERVICE_FIELDS)
        marks = ",".join("?" * len(SERVICE_FIELDS))
        cur = self.db.execute(
            f"INSERT INTO service_logs ({cols}) VALUES ({marks})",
            tuple(data.get(f) for f in SERVICE_FIELDS),
        )
        row_id = cur.lastrowid
        if row_id is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        log = self.get_by_id(row_id)
        if log is None:  # pragma: no cover
            raise RuntimeError(f"Row {row_id} not found after INSERT")
        self._record_history(log, changed_by)
        return log

    def update(
        self, log_id: int, data: dict[str, Any], changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Update service log fields, record a history snapshot, and return the updated log."""
        fields = [f for f in SERVICE_FIELDS if f != "vehicle_id"]
        sets = ",".join(f"{f}=?" for f in fields)
        self.db.execute(
            f"UPDATE service_logs SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (*(data.get(f) for f in fields), log_id),
        )
        log = self.get_by_id(log_id)
        if log is not None:
            self._record_history(log, changed_by)
        return log

    def delete(self, log_id: int) -> bool:
        """Delete a service log by primary key; return True if a row was removed."""
        return self.db.execute("DELETE FROM service_logs WHERE id=?", (log_id,)).rowcount > 0

    def get_history(self, log_id: int) -> list[dict[str, Any]]:
        """Return full audit history for a service log, newest first, with username."""
        return self._rows(
            self.db.execute(
                """
                SELECT sh.*, u.username AS changed_by_username
                FROM service_log_history sh
                LEFT JOIN users u ON u.id = sh.changed_by
                WHERE sh.service_log_id = ?
                ORDER BY sh.changed_at DESC, sh.id DESC
                """,
                (log_id,),
            ).fetchall()
        )

    def revert(
        self, log_id: int, version_id: int, changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Restore a service log from a history record; return None if it doesn't exist."""
        h = self._row(
            self.db.execute(
                "SELECT * FROM service_log_history WHERE id=? AND service_log_id=?",
                (version_id, log_id),
            ).fetchone()
        )
        if not h:
            return None
        return self.update(log_id, h, changed_by=changed_by)

    def _record_history(self, log: dict[str, Any], changed_by: int | None) -> None:
        """Write a snapshot of the service log's current field values to history."""
        cols = ",".join(SERVICE_FIELDS)
        marks = ",".join("?" * len(SERVICE_FIELDS))
        self.db.execute(
            f"INSERT INTO service_log_history (service_log_id, changed_by, {cols})"
            f" VALUES (?,?,{marks})",
            (log["id"], changed_by, *(log.get(f) for f in SERVICE_FIELDS)),
        )

    def reminders(
        self, vehicle_id: int | None = None, today: date | None = None
    ) -> list[dict[str, Any]]:
        """Return open maintenance reminders, most urgent first.

        A service log with a next_due_date or next_due_km creates a reminder. The
        reminder is closed once a newer log exists for the same vehicle and category.
        Status is 'overdue', 'due_soon' (within DUE_SOON_DAYS / DUE_SOON_KM of the
        vehicle's latest odometer reading), or 'upcoming'.
        """
        today = today or date.today()
        where = ""
        params: tuple[Any, ...] = ()
        if vehicle_id is not None:
            where, params = "AND s.vehicle_id = ?", (vehicle_id,)
        candidates = self._rows(
            self.db.execute(
                f"""
                SELECT s.*, v.name AS vehicle_name, v.kind AS vehicle_kind,
                       v.odometer_unit AS vehicle_odometer_unit
                FROM service_logs s
                JOIN vehicles v ON v.id = s.vehicle_id
                WHERE (s.next_due_date IS NOT NULL OR s.next_due_km IS NOT NULL)
                  AND v.archived = 0
                  AND NOT EXISTS (
                      SELECT 1 FROM service_logs n
                      WHERE n.vehicle_id = s.vehicle_id
                        AND n.category IS s.category
                        AND (n.date > s.date OR (n.date = s.date AND n.id > s.id))
                  )
                  {where}
                ORDER BY s.next_due_date ASC
                """,
                params,
            ).fetchall()
        )
        from torqued.repositories.vehicle_repository import VehicleRepository

        latest = VehicleRepository(self.db).latest_odometers()
        soon_cutoff = (today + timedelta(days=DUE_SOON_DAYS)).isoformat()
        reminders = []
        for s in candidates:
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
            ) or (km_remaining is not None and km_remaining <= DUE_SOON_KM)
            if overdue:
                status = "overdue"
            elif due_soon:
                status = "due_soon"
            reminders.append({**s, "status": status, "km_remaining": km_remaining})
        order = {"overdue": 0, "due_soon": 1, "upcoming": 2}
        reminders.sort(key=lambda r: (order[r["status"]], r["next_due_date"] or "9999-12-31"))
        return reminders

    def search(self, query: str) -> list[dict[str, Any]]:
        """Return up to 10 service logs matching title, description, category, or garage."""
        q = f"%{query}%"
        return self._rows(
            self.db.execute(
                f"""
                {_VEHICLE_JOIN}
                WHERE s.title LIKE ? OR s.description LIKE ? OR s.category LIKE ?
                   OR s.performed_by LIKE ?
                LIMIT 10
                """,
                (q, q, q, q),
            ).fetchall()
        )

    def performers(self) -> list[str]:
        """Return distinct 'performed_by' values for autocomplete suggestions."""
        return [
            r["performed_by"]
            for r in self.db.execute(
                "SELECT DISTINCT performed_by FROM service_logs"
                " WHERE performed_by IS NOT NULL AND performed_by != '' ORDER BY performed_by"
            ).fetchall()
        ]

    def export_flat(self, vehicle_id: int | None = None) -> list[dict[str, Any]]:
        """Return flat export rows for service logs, optionally for one vehicle."""
        where = ""
        params: tuple[Any, ...] = ()
        if vehicle_id is not None:
            where, params = "WHERE s.vehicle_id = ?", (vehicle_id,)
        return self._rows(
            self.db.execute(
                f"""
                SELECT v.name AS vehicle, v.make, v.model, v.registration,
                       s.date, s.title, s.category, s.description, s.performed_by,
                       s.cost, s.odometer_km, s.odometer_unit,
                       s.next_due_date, s.next_due_km, s.created_at
                FROM service_logs s
                JOIN vehicles v ON v.id = s.vehicle_id
                {where}
                ORDER BY v.name ASC, s.date DESC, s.id DESC
                """,
                params,
            ).fetchall()
        )
