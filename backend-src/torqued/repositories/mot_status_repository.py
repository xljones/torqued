import json
from typing import Any

from sqlalchemy import delete, func, select, update

from torqued import mot
from torqued.models import VehicleMotStatus, to_dict
from torqued.repositories.base import BaseRepository


class MotStatusRepository(BaseRepository):
    """The DVLA VES *current MOT status* record (status + expiry), a sibling of the tax
    record scraped from the same page. Structurally identical to ``TaxRepository`` — one
    live row per vehicle plus any number of detached history rows — but deliberately has
    **no** ``reminders()``: MOT reminders stay a single ``type='mot'`` item emitted by
    ``MotRepository``, which folds this record's expiry in (so a fresh VES expiry can
    correct a stale DVSA one) rather than raising a second, duplicate MOT reminder.
    """

    def get_for_vehicle(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return the live MOT-status snapshot for a vehicle (raw payload parsed), or None."""
        row = self.session.scalars(
            select(VehicleMotStatus).where(VehicleMotStatus.vehicle_id == vehicle_id)
        ).first()
        if row is None:
            return None
        snapshot = to_dict(row)
        snapshot["raw"] = json.loads(snapshot.pop("raw_json"))
        return snapshot

    def clear_for_vehicle(self, vehicle_id: int) -> None:
        """Hard-delete the stored MOT-status snapshot for a vehicle (registration no longer
        applies). Used by the vehicle disconnect flow; a plain refresh keeps history — see
        replace_for_vehicle."""
        self.session.execute(
            delete(VehicleMotStatus).where(VehicleMotStatus.vehicle_id == vehicle_id)
        )

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh MOT-status lookup, keeping any previous lookup as history.

        Detach-then-insert (drop the old row's ``vehicle_id`` -> NULL, add the new live row)
        keeps the ``vehicle_id`` UNIQUE constraint satisfied: one live row per vehicle, any
        number of detached ones still grouped by registration.
        """
        self.session.execute(
            update(VehicleMotStatus)
            .where(VehicleMotStatus.vehicle_id == vehicle_id)
            .values(vehicle_id=None)
        )
        self.session.add(self._snapshot(vehicle_id, payload))

    def store_detached_lookup(self, payload: dict[str, Any]) -> None:
        """Persist a MOT-status lookup not tied to any vehicle (``vehicle_id`` NULL).

        Used by the records page to look up any registration without assigning it to a
        vehicle; ``relink_detached`` ties it to a vehicle added on that plate later.
        """
        self.session.add(self._snapshot(None, payload))

    # The fields of the VES payload that belong to the *MOT-status* record. The one VES
    # fetch also carries tax fields (stored separately in vehicle_tax), so raw_json keeps
    # only this record's own facet — otherwise the tax and MOT records would look identical.
    _RAW_KEYS = ("registration", "mot_status", "mot_expiry_date")

    @classmethod
    def _snapshot(cls, vehicle_id: int | None, payload: dict[str, Any]) -> VehicleMotStatus:
        """Build a VehicleMotStatus row from a VES payload (its MOT facet in ``raw_json``)."""
        return VehicleMotStatus(
            vehicle_id=vehicle_id,
            registration=payload.get("registration"),
            mot_status=payload.get("mot_status"),
            mot_expiry_date=payload.get("mot_expiry_date"),
            raw_json=json.dumps({k: payload.get(k) for k in cls._RAW_KEYS}),
        )

    def relink_detached(self, vehicle_id: int, registration: str) -> bool:
        """Retie a plate's newest detached MOT-status record to a newly added vehicle.

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
            select(VehicleMotStatus)
            .where(
                VehicleMotStatus.vehicle_id.is_(None),
                VehicleMotStatus.registration.is_not(None),
                func.upper(func.replace(VehicleMotStatus.registration, " ", "")) == norm,
            )
            .order_by(VehicleMotStatus.fetched_at.desc(), VehicleMotStatus.id.desc())
        ).first()
        if detached is None:
            return False
        detached.vehicle_id = vehicle_id
        return True
