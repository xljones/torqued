import json
from datetime import date, timedelta
from typing import Any

from torqued.repositories.base import BaseRepository
from torqued.repositories.service_log_repository import DUE_SOON_DAYS


class VesRepository(BaseRepository):
    def get_for_vehicle(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return the stored DVLA snapshot for a vehicle (parsed raw), or None."""
        snapshot = self._row(
            self.db.execute(
                "SELECT * FROM dvla_vehicles WHERE vehicle_id=?", (vehicle_id,)
            ).fetchone()
        )
        if snapshot is None:
            return None
        snapshot["raw"] = json.loads(snapshot.pop("raw_json"))
        return snapshot

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh DVLA response, replacing any previous snapshot.

        Every scalar field is captured as a column; the full verbatim payload is
        also kept in raw_json so nothing the API returns is ever lost.
        """
        self.db.execute("DELETE FROM dvla_vehicles WHERE vehicle_id=?", (vehicle_id,))
        self.db.execute(
            """
            INSERT INTO dvla_vehicles (
                vehicle_id, registration, tax_status, tax_due_date,
                mot_status, mot_expiry_date, make, colour, fuel_type,
                year_of_manufacture, engine_capacity, co2_emissions,
                marked_for_export, type_approval, wheelplan, revenue_weight,
                real_driving_emissions, euro_status, date_of_last_v5c_issued,
                month_of_first_registration, month_of_first_dvla_registration,
                art_end_date, automated_vehicle, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                vehicle_id,
                payload.get("registrationNumber"),
                payload.get("taxStatus"),
                payload.get("taxDueDate"),
                payload.get("motStatus"),
                payload.get("motExpiryDate"),
                payload.get("make"),
                payload.get("colour"),
                payload.get("fuelType"),
                payload.get("yearOfManufacture"),
                payload.get("engineCapacity"),
                payload.get("co2Emissions"),
                payload.get("markedForExport"),
                payload.get("typeApproval"),
                payload.get("wheelplan"),
                payload.get("revenueWeight"),
                payload.get("realDrivingEmissions"),
                payload.get("euroStatus"),
                payload.get("dateOfLastV5CIssued"),
                payload.get("monthOfFirstRegistration"),
                payload.get("monthOfFirstDvlaRegistration"),
                payload.get("artEndDate"),
                payload.get("automatedVehicle"),
                json.dumps(payload),
            ),
        )

    def tax_reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return open road-tax reminders, one per vehicle with a known tax due date.

        Shaped like the service-log reminders (see ServiceLogRepository.reminders)
        so the two streams can be merged and rendered by the same UI; status reuses
        the DUE_SOON_DAYS window (tax has no mileage component). A `source` of 'tax'
        marks the origin (service reminders carry no source).
        """
        today = today or date.today()
        if not garage_ids:
            return []
        placeholders = ",".join("?" * len(garage_ids))
        where = ""
        params: tuple[Any, ...] = tuple(garage_ids)
        if vehicle_id is not None:
            where, params = "AND d.vehicle_id = ?", (*garage_ids, vehicle_id)
        rows = self._rows(
            self.db.execute(
                f"""
                SELECT d.vehicle_id, d.tax_due_date, d.fetched_at,
                       v.name AS vehicle_name, v.kind AS vehicle_kind, v.garage_id,
                       v.odometer_unit AS vehicle_odometer_unit
                FROM dvla_vehicles d
                JOIN vehicles v ON v.id = d.vehicle_id
                WHERE d.tax_due_date IS NOT NULL
                  AND v.archived = 0
                  AND v.garage_id IN ({placeholders})
                  {where}
                """,
                params,
            ).fetchall()
        )
        soon_cutoff = (today + timedelta(days=DUE_SOON_DAYS)).isoformat()
        reminders = []
        for r in rows:
            due = r["tax_due_date"]
            if due < today.isoformat():
                status = "overdue"
            elif due <= soon_cutoff:
                status = "due_soon"
            else:
                status = "upcoming"
            reminders.append({
                "id": f"tax-{r['vehicle_id']}",
                "source": "tax",
                "vehicle_id": r["vehicle_id"],
                "vehicle_name": r["vehicle_name"],
                "vehicle_kind": r["vehicle_kind"],
                "garage_id": r["garage_id"],
                "vehicle_odometer_unit": r["vehicle_odometer_unit"],
                "date": (r["fetched_at"] or "")[:10],
                "title": "Road tax",
                "category": None,
                "next_due_date": due,
                "next_due_km": None,
                "km_remaining": None,
                "status": status,
            })
        return reminders
