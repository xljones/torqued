import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update

from torqued import mot
from torqued.models import Vehicle, VehicleVes, to_dict
from torqued.repositories.base import BaseRepository

# Road tax surfaces as a reminder once its due date is within this window or lapsed.
TAX_DUE_SOON_DAYS = 30


class VesRepository(BaseRepository):
    """The DVLA VES record — one lookup holding tax + MOT status + the vehicle profile.

    One live row per vehicle plus any number of detached history rows (migration 0007).
    Owns the road-tax reminder (``type='tax'``); the MOT reminder stays a single
    ``type='mot'`` item emitted by ``MotRepository``, which folds this record's
    ``mot_expiry_date`` in so a fresh VES status corrects a stale DVSA history.
    """

    def get_for_vehicle(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return the live VES snapshot for a vehicle (raw payload parsed), or None."""
        row = self.session.scalars(
            select(VehicleVes).where(VehicleVes.vehicle_id == vehicle_id)
        ).first()
        if row is None:
            return None
        snapshot = to_dict(row)
        snapshot["raw"] = json.loads(snapshot.pop("raw_json"))
        return snapshot

    def clear_for_vehicle(self, vehicle_id: int) -> None:
        """Hard-delete the stored VES snapshot for a vehicle (registration no longer
        applies). Used by the vehicle disconnect flow; a plain refresh keeps history."""
        self.session.execute(delete(VehicleVes).where(VehicleVes.vehicle_id == vehicle_id))

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh VES lookup, keeping any previous lookup as history.

        Detach-then-insert (drop the old row's ``vehicle_id`` -> NULL, add the new live
        row) keeps the ``vehicle_id`` UNIQUE constraint satisfied: one live row per
        vehicle, any number of detached ones still grouped by registration.
        """
        self.session.execute(
            update(VehicleVes).where(VehicleVes.vehicle_id == vehicle_id).values(vehicle_id=None)
        )
        self.session.add(self._snapshot(vehicle_id, payload))

    def store_detached_lookup(self, payload: dict[str, Any]) -> None:
        """Persist a VES lookup not tied to any vehicle (``vehicle_id`` NULL).

        Used by the records page to look up any registration without assigning it to a
        vehicle; ``relink_detached`` ties it to a vehicle added on that plate later.
        """
        self.session.add(self._snapshot(None, payload))

    @staticmethod
    def _snapshot(vehicle_id: int | None, payload: dict[str, Any]) -> VehicleVes:
        """Build a VehicleVes row from a VES payload (kept verbatim in ``raw_json``)."""
        return VehicleVes(
            vehicle_id=vehicle_id,
            registration=payload.get("registration"),
            tax_status=payload.get("tax_status"),
            tax_due_date=payload.get("tax_due_date"),
            mot_status=payload.get("mot_status"),
            mot_expiry_date=payload.get("mot_expiry_date"),
            make=payload.get("make"),
            colour=payload.get("colour"),
            raw_json=json.dumps(payload),
        )

    def relink_detached(self, vehicle_id: int, registration: str) -> bool:
        """Retie a plate's newest detached VES record to a newly added vehicle.

        Detached records (``vehicle_id`` NULL) accumulate from earlier refreshes, standalone
        lookups, and deleted vehicles. When a vehicle takes that plate, make the newest
        historic lookup its live snapshot (the ``vehicle_id`` FK is 1:1); older lookups stay
        detached but remain grouped under the vehicle by registration. Only detached rows are
        considered. Returns True if a record was relinked.
        """
        norm = mot.normalise_registration(registration)
        if not norm:
            return False
        detached = self.session.scalars(
            select(VehicleVes)
            .where(
                VehicleVes.vehicle_id.is_(None),
                VehicleVes.registration.is_not(None),
                func.upper(func.replace(VehicleVes.registration, " ", "")) == norm,
            )
            .order_by(VehicleVes.fetched_at.desc(), VehicleVes.id.desc())
        ).first()
        if detached is None:
            return False
        detached.vehicle_id = vehicle_id
        return True

    def reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return road-tax reminders for in-scope, non-archived vehicles.

        A vehicle with a stored tax due date yields a reminder when the tax has lapsed
        ('overdue') or falls due within TAX_DUE_SOON_DAYS ('due_soon'); tax further out
        produces nothing. SORN / Untaxed records carry no due date and so raise no reminder —
        the card shows that status directly. Shaped (and tagged type='tax') to merge with the
        service-log and MOT reminders.
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
                VehicleVes.tax_due_date,
            )
            .join(VehicleVes, VehicleVes.vehicle_id == Vehicle.id)
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
