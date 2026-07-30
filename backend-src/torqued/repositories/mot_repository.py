import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select

from torqued import mot
from torqued.models import DvsaVehicle, MotTest, Vehicle, to_dict
from torqued.repositories.base import BaseRepository

# DVSA reports odometer units as 'MI'/'KM'; we store 'mi'/'km' like everywhere else.
_UNIT_MAP = {"MI": "mi", "KM": "km"}

# An MOT surfaces as a maintenance reminder once its expiry is within this window
# (~2 months) or already lapsed.
MOT_DUE_SOON_DAYS = 60


def _record_count(raw_json: str) -> int:
    """Count the raw DVSA records in a stored snapshot: the vehicle itself + each MOT test."""
    payload = json.loads(raw_json)
    return 1 + len(payload.get("motTests") or [])


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

    def list_all(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """Return a page of every stored DVSA snapshot, newest refresh first.

        ``vehicle_id`` is included verbatim: NULL marks a record whose vehicle has
        since been deleted (see migration 0002), which the admin view shows as a
        detached record rather than a link.

        Each item carries a ``record_count`` — the number of raw DVSA records we hold
        for that vehicle: the snapshot itself plus one per stored MOT test (both
        derived from ``raw_json`` so attached and detached rows count the same way).
        ``total_records`` sums that across every stored vehicle.
        """
        total = self.session.scalar(select(func.count()).select_from(DvsaVehicle)) or 0
        total_records = sum(
            _record_count(raw)
            for raw in self.session.scalars(select(DvsaVehicle.raw_json)).all()
        )
        rows = (
            self.session.execute(
                select(
                    DvsaVehicle.id,
                    DvsaVehicle.vehicle_id,
                    DvsaVehicle.registration,
                    DvsaVehicle.make,
                    DvsaVehicle.model,
                    DvsaVehicle.fetched_at,
                    DvsaVehicle.raw_json,
                )
                .order_by(DvsaVehicle.fetched_at.desc(), DvsaVehicle.id.desc())
                .limit(per_page)
                .offset((page - 1) * per_page)
            )
            .mappings()
            .all()
        )
        items = []
        for r in rows:
            item = dict(r)
            item["record_count"] = _record_count(item.pop("raw_json"))
            items.append(item)
        return {
            "items": items,
            "total": total,
            "total_records": total_records,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    def get_records_by_id(self, dvsa_id: int) -> dict[str, Any] | None:
        """Return every stored DVSA record for one snapshot, keyed by its surrogate id.

        The vehicle snapshot and its MOT tests are decomposed from the stored
        ``raw_json`` (the complete DVSA payload) so this works identically for a live
        record and a detached one whose normalized ``mot_tests`` rows have cascaded
        away. ``vehicle`` is the payload with its ``motTests`` array split out into
        ``tests`` so each record is shown once, without duplication.
        """
        dvsa = self.session.get(DvsaVehicle, dvsa_id)
        if dvsa is None:
            return None
        raw = json.loads(dvsa.raw_json)
        tests = raw.pop("motTests", None) or []
        return {
            "id": dvsa.id,
            "vehicle_id": dvsa.vehicle_id,
            "registration": dvsa.registration,
            "make": dvsa.make,
            "model": dvsa.model,
            "fetched_at": dvsa.fetched_at,
            "vehicle": raw,
            "tests": tests,
        }

    def reminders(
        self,
        garage_ids: list[int],
        vehicle_id: int | None = None,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return MOT-expiry reminders for in-scope, non-archived vehicles.

        A vehicle with a stored DVSA snapshot yields a reminder when its MOT has
        lapsed ('overdue') or falls due within MOT_DUE_SOON_DAYS ('due_soon');
        MOTs further out produce nothing. The due date is the most recent test's
        expiry, falling back to the DVSA vehicle-level next-due date — the same
        value the MOT card shows. Shaped (and tagged type='mot') to merge with
        the service-log reminders.
        """
        today = today or date.today()
        if not garage_ids:
            return []
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
            )
            .join(DvsaVehicle, DvsaVehicle.vehicle_id == Vehicle.id)
            .where(Vehicle.archived == 0, Vehicle.garage_id.in_(garage_ids))
        )
        if vehicle_id is not None:
            stmt = stmt.where(Vehicle.id == vehicle_id)
        rows = self.session.execute(stmt).mappings().all()
        cutoff = (today + timedelta(days=MOT_DUE_SOON_DAYS)).isoformat()
        today_iso = today.isoformat()
        reminders: list[dict[str, Any]] = []
        for r in rows:
            due = r["latest_expiry"] or r["mot_test_due_date"]
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
        """Remove the stored DVSA snapshot and tests for a vehicle.

        Used when the registration changes so the data no longer applies, and as the
        first step of a replace.
        """
        self.session.execute(delete(DvsaVehicle).where(DvsaVehicle.vehicle_id == vehicle_id))
        self.session.execute(delete(MotTest).where(MotTest.vehicle_id == vehicle_id))

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh DVSA response, replacing any previous snapshot and tests."""
        self.clear_for_vehicle(vehicle_id)
        self.session.add(
            DvsaVehicle(
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
        )
        self._add_tests(vehicle_id, payload)

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
        """Re-attach the newest detached DVSA record matching a plate to a vehicle.

        A deleted vehicle's DVSA snapshot survives with ``vehicle_id`` NULL
        (migration 0002). When a vehicle later takes that plate, relink the record
        and rebuild its cascade-deleted ``mot_tests`` from ``raw_json``. Only
        detached rows are considered, so a live record on another vehicle that
        shares the plate is never touched. Returns True if a record was relinked.
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
