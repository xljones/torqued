import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select

from torqued.models import Vehicle, VehicleTax, to_dict
from torqued.repositories.base import BaseRepository

# Road tax surfaces as a reminder once its due date is within this window or lapsed.
TAX_DUE_SOON_DAYS = 30


class TaxRepository(BaseRepository):
    def get_for_vehicle(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return the stored tax snapshot for a vehicle (raw payload parsed), or None."""
        row = self.session.scalars(
            select(VehicleTax).where(VehicleTax.vehicle_id == vehicle_id)
        ).first()
        if row is None:
            return None
        snapshot = to_dict(row)
        snapshot["raw"] = json.loads(snapshot.pop("raw_json"))
        return snapshot

    def clear_for_vehicle(self, vehicle_id: int) -> None:
        """Remove the stored tax snapshot for a vehicle (plate no longer applies / replace)."""
        self.session.execute(delete(VehicleTax).where(VehicleTax.vehicle_id == vehicle_id))

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh tax lookup, replacing any previous snapshot."""
        self.clear_for_vehicle(vehicle_id)
        self.session.add(
            VehicleTax(
                vehicle_id=vehicle_id,
                registration=payload.get("registration"),
                tax_status=payload.get("tax_status"),
                tax_due_date=payload.get("tax_due_date"),
                raw_json=json.dumps(payload),
            )
        )

    def reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return road-tax reminders for in-scope, non-archived vehicles.

        A vehicle with a stored tax due date yields a reminder when the tax has
        lapsed ('overdue') or falls due within TAX_DUE_SOON_DAYS ('due_soon'); tax
        further out produces nothing. SORN / Untaxed records carry no due date and so
        raise no reminder — the tax card shows that status directly. Shaped (and tagged
        type='tax') to merge with the service-log and MOT reminders.
        """
        today = today or date.today()
        if not garage_ids:
            return []
        stmt = (
            select(
                Vehicle.id.label("vehicle_id"),
                Vehicle.name.label("vehicle_name"),
                Vehicle.kind.label("vehicle_kind"),
                Vehicle.garage_id,
                Vehicle.odometer_unit.label("vehicle_odometer_unit"),
                VehicleTax.tax_due_date,
            )
            .join(VehicleTax, VehicleTax.vehicle_id == Vehicle.id)
            .where(Vehicle.archived == 0, Vehicle.garage_id.in_(garage_ids))
        )
        if vehicle_id is not None:
            stmt = stmt.where(Vehicle.id == vehicle_id)
        rows = self.session.execute(stmt).mappings().all()
        cutoff = (today + timedelta(days=TAX_DUE_SOON_DAYS)).isoformat()
        today_iso = today.isoformat()
        reminders: list[dict[str, Any]] = []
        for r in rows:
            due = r["tax_due_date"]
            if not due:
                continue
            if due < today_iso:
                status = "overdue"
            elif due <= cutoff:
                status = "due_soon"
            else:
                continue
            reminders.append(
                {
                    "type": "tax",
                    "id": None,
                    "vehicle_id": r["vehicle_id"],
                    "vehicle_name": r["vehicle_name"],
                    "vehicle_kind": r["vehicle_kind"],
                    "garage_id": r["garage_id"],
                    "vehicle_odometer_unit": r["vehicle_odometer_unit"],
                    "title": "Road tax",
                    "category": "Tax",
                    "date": None,
                    "next_due_date": due,
                    "next_due_km": None,
                    "km_remaining": None,
                    "status": status,
                }
            )
        return reminders
