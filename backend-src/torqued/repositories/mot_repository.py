import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update

from torqued import mot
from torqued.models import DvsaVehicle, MotTest, Vehicle, VehicleVes, to_dict
from torqued.reminders import DEFAULT_WINDOWS, ReminderWindows
from torqued.repositories.base import BaseRepository

# DVSA reports odometer units as 'MI'/'KM'; we store 'mi'/'km' like everywhere else.
_UNIT_MAP = {"MI": "mi", "KM": "km"}


class MotRepository(BaseRepository):
    def get_for_vehicle(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return the stored DVSA snapshot for a vehicle (parsed defects), or None."""
        # vehicle_id is no longer the primary key (migration 0002), so look it up by
        # column rather than session.get().
        dvsa = self.session.scalars(
            select(DvsaVehicle).where(DvsaVehicle.vehicle_id == vehicle_id)
        ).first()
        if dvsa is None:
            return None
        snapshot = to_dict(dvsa)
        snapshot["raw"] = json.loads(snapshot.pop("raw_json"))
        tests = self.session.scalars(
            select(MotTest)
            .where(MotTest.vehicle_id == vehicle_id)
            .order_by(MotTest.completed_date.desc(), MotTest.id.desc())
        ).all()
        parsed = []
        for test in tests:
            t = to_dict(test)
            t["defects"] = json.loads(t.pop("defects_json"))
            del t["raw_json"]
            parsed.append(t)
        snapshot["tests"] = parsed
        return snapshot

    def reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
        windows: dict[int, ReminderWindows] | None = None,
    ) -> list[dict[str, Any]]:
        """Return MOT-expiry reminders for in-scope, non-archived vehicles.

        A vehicle with a stored DVSA snapshot yields a reminder when its MOT has
        lapsed ('overdue') or falls due within the owning garage's MOT window ('due_soon');
        MOTs further out produce nothing. The due date is the **later** of the most
        recent DVSA test's expiry and the DVLA VES current-MOT-status expiry (the DVSA
        history feed lags for e.g. SORN vehicles, so a fresh VES expiry corrects a stale
        DVSA one and prevents a false 'overdue'), falling back to the DVSA vehicle-level
        next-due date — the same value the MOT card shows. Vehicles the DVLA records as
        SORN are skipped entirely: off the road, no MOT needed, nothing to act on.
        Shaped (and tagged type='mot') to merge with the service-log reminders.
        """
        today = today or date.today()
        if not garage_ids:
            return []
        if windows is None:  # standalone use; the orchestrator passes in the map it built
            from torqued.repositories.garage_repository import GarageRepository

            windows = GarageRepository(self.session).reminder_windows(garage_ids)
        latest_expiry = (
            select(MotTest.expiry_date)
            .where(MotTest.vehicle_id == Vehicle.id)
            .order_by(MotTest.completed_date.desc(), MotTest.id.desc())
            .limit(1)
            .correlate(Vehicle)
            .scalar_subquery()
        )
        stmt = (
            select(
                Vehicle.id.label("vehicle_id"),
                Vehicle.name.label("vehicle_name"),
                Vehicle.kind.label("vehicle_kind"),
                Vehicle.garage_id,
                Vehicle.odometer_unit.label("vehicle_odometer_unit"),
                DvsaVehicle.mot_test_due_date,
                latest_expiry.label("latest_expiry"),
                VehicleVes.mot_expiry_date.label("ves_expiry"),
                VehicleVes.tax_status.label("ves_tax_status"),
            )
            .join(DvsaVehicle, DvsaVehicle.vehicle_id == Vehicle.id)
            .outerjoin(VehicleVes, VehicleVes.vehicle_id == Vehicle.id)
            .where(Vehicle.archived == 0, Vehicle.garage_id.in_(garage_ids))
        )
        if vehicle_id is not None:
            stmt = stmt.where(Vehicle.id == vehicle_id)
        rows = self.session.execute(stmt).mappings().all()
        today_iso = today.isoformat()
        reminders: list[dict[str, Any]] = []
        for r in rows:
            # A SORN vehicle is declared off the road and needs no MOT, so a lapsed one
            # isn't actionable. The vehicle card still shows the factual 'expired' status.
            if (r["ves_tax_status"] or "").upper() == "SORN":
                continue
            # Each garage sets its own window, so the cutoff is per row, not hoisted.
            cutoff = (
                today + timedelta(days=windows.get(r["garage_id"], DEFAULT_WINDOWS).mot_days)
            ).isoformat()
            # The later of the DVSA test expiry and the VES expiry (ISO YYYY-MM-DD strings
            # sort chronologically), so a fresh VES status overrides stale DVSA history.
            expiry = max(
                (d for d in (r["latest_expiry"], r["ves_expiry"]) if d), default=None
            )
            due = expiry or r["mot_test_due_date"]
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
                    "type": "mot",
                    "id": None,
                    "vehicle_id": r["vehicle_id"],
                    "vehicle_name": r["vehicle_name"],
                    "vehicle_kind": r["vehicle_kind"],
                    "garage_id": r["garage_id"],
                    "vehicle_odometer_unit": r["vehicle_odometer_unit"],
                    "title": "MOT",
                    "category": "MOT",
                    "date": None,
                    "next_due_date": due,
                    "next_due_km": None,
                    "km_remaining": None,
                    "status": status,
                }
            )
        return reminders

    def clear_for_vehicle(self, vehicle_id: int) -> None:
        """Hard-delete the stored DVSA snapshot and tests for a vehicle.

        Used when the registration changes so the data no longer applies (the vehicle
        disconnect flow). A plain refresh does not delete — see replace_for_vehicle.
        """
        self.session.execute(delete(DvsaVehicle).where(DvsaVehicle.vehicle_id == vehicle_id))
        self.session.execute(delete(MotTest).where(MotTest.vehicle_id == vehicle_id))

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh DVSA lookup, keeping any previous lookup as history.

        Each refresh is one lookup and becomes its own record. Rather than deleting the
        previous snapshot, we drop its link (``vehicle_id`` -> NULL) so it survives as a
        dated historical record, still tied to the vehicle by its normalised
        registration (see ``list_all``'s grouping). The vehicle's normalised
        ``mot_tests`` are rebuilt for the new row while the detached row keeps the whole
        lookup in ``raw_json``; old records can be pruned later by ``fetched_at``.

        Detach-then-insert keeps the ``vehicle_id`` UNIQUE constraint satisfied: at most
        one live row per vehicle, any number of detached (NULL) ones.
        """
        self.session.execute(
            update(DvsaVehicle)
            .where(DvsaVehicle.vehicle_id == vehicle_id)
            .values(vehicle_id=None)
        )
        self.session.execute(delete(MotTest).where(MotTest.vehicle_id == vehicle_id))
        self.session.add(self._snapshot(vehicle_id, payload))
        self._add_tests(vehicle_id, payload)

    def store_detached_lookup(self, payload: dict[str, Any]) -> None:
        """Persist a DVSA lookup not tied to any vehicle (``vehicle_id`` NULL).

        Used by the admin DVSA page to look up any registration and keep the result
        without assigning it to a garage vehicle. If a vehicle on this plate is later
        added, ``relink_detached`` ties this record to it. No ``mot_tests`` rows are
        created (they require a ``vehicle_id``) — the whole lookup lives in ``raw_json``,
        which is what the records view reads.
        """
        self.session.add(self._snapshot(None, payload))

    @staticmethod
    def _snapshot(vehicle_id: int | None, payload: dict[str, Any]) -> DvsaVehicle:
        """Build a DvsaVehicle row from a DVSA payload (verbatim in ``raw_json``)."""
        return DvsaVehicle(
            vehicle_id=vehicle_id,
            registration=payload.get("registration"),
            make=payload.get("make"),
            model=payload.get("model"),
            first_used_date=payload.get("firstUsedDate"),
            fuel_type=payload.get("fuelType"),
            primary_colour=payload.get("primaryColour"),
            registration_date=payload.get("registrationDate"),
            manufacture_date=payload.get("manufactureDate"),
            manufacture_year=payload.get("manufactureYear"),
            engine_size=payload.get("engineSize"),
            has_outstanding_recall=payload.get("hasOutstandingRecall"),
            mot_test_due_date=payload.get("motTestDueDate"),
            raw_json=json.dumps(payload),
        )

    def _add_tests(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Insert MotTest rows for a vehicle from a DVSA payload's motTests array."""
        for test in payload.get("motTests") or []:
            self.session.add(
                MotTest(
                    vehicle_id=vehicle_id,
                    completed_date=test.get("completedDate"),
                    test_result=test.get("testResult"),
                    expiry_date=test.get("expiryDate"),
                    odometer_value=test.get("odometerValue"),
                    odometer_unit=_UNIT_MAP.get((test.get("odometerUnit") or "").upper()),
                    odometer_result_type=test.get("odometerResultType"),
                    mot_test_number=test.get("motTestNumber"),
                    data_source=test.get("dataSource"),
                    location=test.get("location"),
                    defects_json=json.dumps(test.get("defects") or []),
                    raw_json=json.dumps(test),
                )
            )

    def relink_detached(self, vehicle_id: int, registration: str) -> bool:
        """Retie a plate's historic DVSA records to a newly added vehicle.

        Detached records (``vehicle_id`` NULL) accumulate for a plate from earlier
        refreshes and from a deleted vehicle (migration 0002). When a vehicle takes
        that plate, make the **newest** historic lookup its live snapshot — rebuilding
        that record's ``mot_tests`` from ``raw_json`` — since the ``vehicle_id`` FK is
        1:1. The older lookups stay detached but remain tied to the vehicle for display
        by their shared normalised registration (``list_all`` groups by plate). Only
        detached rows are considered, so a live record on another vehicle sharing the
        plate is never touched. Returns True if a record was relinked.
        """
        norm = mot.normalise_registration(registration)
        if not norm:
            return False
        detached = self.session.scalars(
            select(DvsaVehicle)
            .where(
                DvsaVehicle.vehicle_id.is_(None),
                DvsaVehicle.registration.is_not(None),
                func.upper(func.replace(DvsaVehicle.registration, " ", "")) == norm,
            )
            .order_by(DvsaVehicle.fetched_at.desc(), DvsaVehicle.id.desc())
        ).first()
        if detached is None:
            return False
        detached.vehicle_id = vehicle_id
        self._add_tests(vehicle_id, json.loads(detached.raw_json))
        return True
