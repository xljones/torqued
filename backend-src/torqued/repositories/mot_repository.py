import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update

from torqued import mot
from torqued.models import DvsaVehicle, Garage, MotTest, Vehicle, to_dict
from torqued.repositories.base import BaseRepository

# DVSA reports odometer units as 'MI'/'KM'; we store 'mi'/'km' like everywhere else.
_UNIT_MAP = {"MI": "mi", "KM": "km"}

# An MOT surfaces as a maintenance reminder once its expiry is within this window
# (~2 months) or already lapsed.
MOT_DUE_SOON_DAYS = 60


def _year(row: Any) -> int | None:
    """Derive a model year from a DVSA row: explicit manufacture year, else a date's year.

    Mirrors ``mot.to_baseline`` so the admin list and the vehicle baseline agree.
    """
    if row["manufacture_year"] is not None:
        return int(row["manufacture_year"])
    for key in ("manufacture_date", "first_used_date", "registration_date"):
        value = row[key]
        if value and str(value)[:4].isdigit():
            return int(str(value)[:4])
    return None


def _group_key(registration: str | None, row_id: int) -> str:
    """The key that folds DVSA rows into one vehicle: the normalised registration.

    A record with no registration can't be grouped by plate, so it stands alone
    (keyed by its own id) rather than colliding with every other blank-plate row.
    """
    norm = mot.normalise_registration(registration or "")
    return norm or f"\x00{row_id}"


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
        """Return a page of stored DVSA vehicles, newest lookup first.

        A "record" is one entire DVSA lookup (a stored snapshot). Rows are grouped by
        registration into vehicles, so a plate looked up more than once — each refresh
        keeps the previous lookup as a detached record (see ``replace_for_vehicle``) —
        appears once with a ``record_count`` of all its lookups. Each item is
        represented by its newest lookup: ``vehicle_id`` (plus ``vehicle_name`` and
        ``garage_name``) is the most recent live one — NULL when every lookup is
        detached (a standalone lookup or a deleted vehicle) — and ``id`` points at the
        newest row so the records endpoint can rebuild the group. ``total`` counts
        vehicles; ``total_records`` counts lookups.
        """
        rows = (
            self.session.execute(
                select(
                    DvsaVehicle.id,
                    DvsaVehicle.vehicle_id,
                    DvsaVehicle.registration,
                    DvsaVehicle.make,
                    DvsaVehicle.model,
                    DvsaVehicle.manufacture_year,
                    DvsaVehicle.manufacture_date,
                    DvsaVehicle.first_used_date,
                    DvsaVehicle.registration_date,
                    DvsaVehicle.fetched_at,
                    Vehicle.name.label("vehicle_name"),
                    Garage.name.label("garage_name"),
                )
                .outerjoin(Vehicle, Vehicle.id == DvsaVehicle.vehicle_id)
                .outerjoin(Garage, Garage.id == Vehicle.garage_id)
                .order_by(DvsaVehicle.fetched_at.desc(), DvsaVehicle.id.desc())
            )
            .mappings()
            .all()
        )
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            key = _group_key(r["registration"], r["id"])
            group = groups.get(key)
            if group is None:
                # First (newest) row for this plate represents the vehicle.
                groups[key] = {
                    "id": r["id"],
                    "vehicle_id": r["vehicle_id"],
                    "vehicle_name": r["vehicle_name"],
                    "garage_name": r["garage_name"],
                    "registration": r["registration"],
                    "make": r["make"],
                    "model": r["model"],
                    "year": _year(r),
                    "fetched_at": r["fetched_at"],
                    "record_count": 1,
                }
            else:
                group["record_count"] += 1
                # Link to (and name) the most recent live vehicle among the lookups.
                if group["vehicle_id"] is None and r["vehicle_id"] is not None:
                    group["vehicle_id"] = r["vehicle_id"]
                    group["vehicle_name"] = r["vehicle_name"]
                    group["garage_name"] = r["garage_name"]

        items = list(groups.values())
        total = len(items)
        return {
            "items": items[(page - 1) * per_page : page * per_page],
            "total": total,
            "total_records": len(rows),
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    def get_records_by_id(self, dvsa_id: int) -> dict[str, Any] | None:
        """Return every stored DVSA lookup (whole raw payload) for one vehicle.

        ``dvsa_id`` is any row in the group (the list endpoint hands back the newest);
        its registration selects every lookup we hold for that plate, newest first, so
        each record is one complete DVSA response. A row with no registration can't be
        grouped, so it returns just itself. Returns None if the id is unknown.
        """
        dvsa = self.session.get(DvsaVehicle, dvsa_id)
        if dvsa is None:
            return None
        norm = mot.normalise_registration(dvsa.registration or "")
        if not norm:
            group = [dvsa]
        else:
            group = list(
                self.session.scalars(
                    select(DvsaVehicle)
                    .where(func.upper(func.replace(DvsaVehicle.registration, " ", "")) == norm)
                    .order_by(DvsaVehicle.fetched_at.desc(), DvsaVehicle.id.desc())
                ).all()
            )
        return {
            "registration": dvsa.registration,
            "records": [
                {
                    "id": r.id,
                    "vehicle_id": r.vehicle_id,
                    "registration": r.registration,
                    "make": r.make,
                    "model": r.model,
                    "fetched_at": r.fetched_at,
                    "raw": json.loads(r.raw_json),
                }
                for r in group
            ],
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
