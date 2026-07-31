import json
from typing import Any

from sqlalchemy import func, select

from torqued import mot
from torqued.models import DvsaVehicle, Garage, Vehicle, VehicleVes
from torqued.repositories.base import BaseRepository

# The kinds of record this page unifies. Each row in the corresponding table
# (dvsa_vehicles / vehicle_ves) is one whole lookup — a "record".
SOURCES = ("dvsa", "ves")


def _year(row: Any) -> int | None:
    """Derive a model year from a DVSA row: explicit manufacture year, else a date's year.

    Mirrors ``mot.to_baseline`` so the records list and the vehicle baseline agree.
    """
    if row["manufacture_year"] is not None:
        return int(row["manufacture_year"])
    for key in ("manufacture_date", "first_used_date", "registration_date"):
        value = row[key]
        if value and str(value)[:4].isdigit():
            return int(str(value)[:4])
    return None


def _group_key(registration: str | None, source: str, row_id: int) -> str:
    """Fold rows of either source into one vehicle by normalised registration.

    A record with no registration can't be grouped by plate, so it stands alone (keyed by
    its own source+id) rather than colliding with every other blank-plate row.
    """
    norm = mot.normalise_registration(registration or "")
    return norm or f"\x00{source}:{row_id}"


class RecordsRepository(BaseRepository):
    """Read model unifying stored DVSA (MOT history) and DVLA VES lookups for the records
    page.

    Both tables share the same shape (surrogate id + nullable ``vehicle_id``), so a "record"
    is one lookup and a plate's records are grouped by its normalised registration — spanning
    both sources and surviving vehicle deletion.
    """

    def _rows(self) -> list[dict[str, Any]]:
        """Every DVSA and VES row as uniform dicts, newest lookup first."""
        dvsa = (
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
            )
            .mappings()
            .all()
        )
        ves = (
            self.session.execute(
                select(
                    VehicleVes.id,
                    VehicleVes.vehicle_id,
                    VehicleVes.registration,
                    VehicleVes.make,
                    VehicleVes.tax_status,
                    VehicleVes.tax_due_date,
                    VehicleVes.mot_status,
                    VehicleVes.mot_expiry_date,
                    VehicleVes.fetched_at,
                    Vehicle.name.label("vehicle_name"),
                    Garage.name.label("garage_name"),
                )
                .outerjoin(Vehicle, Vehicle.id == VehicleVes.vehicle_id)
                .outerjoin(Garage, Garage.id == Vehicle.garage_id)
            )
            .mappings()
            .all()
        )
        rows: list[dict[str, Any]] = []
        for r in dvsa:
            rows.append(
                {
                    "source": "dvsa",
                    "id": r["id"],
                    "vehicle_id": r["vehicle_id"],
                    "vehicle_name": r["vehicle_name"],
                    "garage_name": r["garage_name"],
                    "registration": r["registration"],
                    "make": r["make"],
                    "model": r["model"],
                    "year": _year(r),
                    "tax_status": None,
                    "tax_due_date": None,
                    "mot_status": None,
                    "mot_expiry_date": None,
                    "fetched_at": r["fetched_at"],
                }
            )
        for r in ves:
            rows.append(
                {
                    "source": "ves",
                    "id": r["id"],
                    "vehicle_id": r["vehicle_id"],
                    "vehicle_name": r["vehicle_name"],
                    "garage_name": r["garage_name"],
                    "registration": r["registration"],
                    "make": r["make"],
                    "model": None,
                    "year": None,
                    "tax_status": r["tax_status"],
                    "tax_due_date": r["tax_due_date"],
                    "mot_status": r["mot_status"],
                    "mot_expiry_date": r["mot_expiry_date"],
                    "fetched_at": r["fetched_at"],
                }
            )
        # Newest first; fetched_at is ISO text so a string sort is chronological.
        rows.sort(key=lambda r: (r["fetched_at"] or "", r["source"], r["id"]), reverse=True)
        return rows

    def list_all(self, page: int = 1, per_page: int = 25) -> dict[str, Any]:
        """A page of vehicles, each grouping all its DVSA + VES lookups, newest first.

        Each item is represented by its newest lookup across both sources: ``ref`` (source +
        row id) lets the records endpoint rebuild the group; ``vehicle_id`` / ``vehicle_name``
        / ``garage_name`` name the most recent *live* vehicle (NULL when every lookup is
        detached); make/model/year come from the newest DVSA lookup and tax/MOT status from
        the newest VES lookup in the group. ``total`` counts vehicles, ``total_records`` all
        lookups, with a per-source split.
        """
        rows = self._rows()
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            key = _group_key(r["registration"], r["source"], r["id"])
            group = groups.get(key)
            if group is None:
                # First (newest overall) row for this plate represents the vehicle.
                group = groups[key] = {
                    "ref": {"source": r["source"], "id": r["id"]},
                    "vehicle_id": r["vehicle_id"],
                    "vehicle_name": r["vehicle_name"],
                    "garage_name": r["garage_name"],
                    "registration": r["registration"],
                    "make": None,
                    "model": None,
                    "year": None,
                    "tax_status": None,
                    "tax_due_date": None,
                    "mot_status": None,
                    "mot_expiry_date": None,
                    "fetched_at": r["fetched_at"],
                    "record_count": 0,
                    "dvsa_count": 0,
                    "ves_count": 0,
                }
            group["record_count"] += 1
            group[f"{r['source']}_count"] += 1
            # Link to (and name) the most recent live vehicle among the lookups.
            if group["vehicle_id"] is None and r["vehicle_id"] is not None:
                group["vehicle_id"] = r["vehicle_id"]
                group["vehicle_name"] = r["vehicle_name"]
                group["garage_name"] = r["garage_name"]
            # Identity from the newest DVSA lookup; tax + MOT status from the newest VES lookup.
            if r["source"] == "dvsa" and group["make"] is None and group["model"] is None:
                group["make"], group["model"], group["year"] = r["make"], r["model"], r["year"]
            if r["source"] == "ves" and group["tax_status"] is None and group["mot_status"] is None:
                group["tax_status"] = r["tax_status"]
                group["tax_due_date"] = r["tax_due_date"]
                group["mot_status"] = r["mot_status"]
                group["mot_expiry_date"] = r["mot_expiry_date"]

        items = list(groups.values())
        total = len(items)
        return {
            "items": items[(page - 1) * per_page : page * per_page],
            "total": total,
            "total_records": len(rows),
            "total_dvsa": sum(1 for r in rows if r["source"] == "dvsa"),
            "total_ves": sum(1 for r in rows if r["source"] == "ves"),
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    def get_records(self, source: str, row_id: int) -> dict[str, Any] | None:
        """Every stored lookup (whole raw payload) for the plate the given row belongs to.

        ``source``/``row_id`` identify any row in the group (the list hands back the newest);
        its registration selects every DVSA + VES lookup for that plate, newest first, each
        one a complete record tagged with its ``source``. A row with no registration returns
        just itself. Returns None if the source is unknown or the row id doesn't exist.
        """
        dvsa_row = self.session.get(DvsaVehicle, row_id) if source == "dvsa" else None
        ves_row = self.session.get(VehicleVes, row_id) if source == "ves" else None
        row: DvsaVehicle | VehicleVes | None = dvsa_row or ves_row
        if row is None:
            return None
        registration = row.registration
        norm = mot.normalise_registration(registration or "")

        if norm:
            dvsa_rows = list(self.session.scalars(self._by_plate(DvsaVehicle, norm)).all())
            ves_rows = list(self.session.scalars(self._by_plate(VehicleVes, norm)).all())
        else:
            # No registration to group on — return only the single row that was asked for.
            dvsa_rows = [dvsa_row] if dvsa_row is not None else []
            ves_rows = [ves_row] if ves_row is not None else []

        records = [self._dvsa_record(r) for r in dvsa_rows]
        records += [self._ves_record(r) for r in ves_rows]
        records.sort(key=lambda r: (r["fetched_at"] or "", r["source"], r["id"]), reverse=True)
        return {"registration": registration, "records": records}

    @staticmethod
    def _by_plate(model: Any, norm: str) -> Any:
        return select(model).where(
            func.upper(func.replace(model.registration, " ", "")) == norm
        )

    @staticmethod
    def _dvsa_record(r: DvsaVehicle) -> dict[str, Any]:
        return {
            "source": "dvsa",
            "id": r.id,
            "vehicle_id": r.vehicle_id,
            "registration": r.registration,
            "make": r.make,
            "model": r.model,
            "tax_status": None,
            "tax_due_date": None,
            "mot_status": None,
            "mot_expiry_date": None,
            "fetched_at": r.fetched_at,
            "raw": json.loads(r.raw_json),
        }

    @staticmethod
    def _ves_record(r: VehicleVes) -> dict[str, Any]:
        return {
            "source": "ves",
            "id": r.id,
            "vehicle_id": r.vehicle_id,
            "registration": r.registration,
            "make": r.make,
            "model": None,
            "tax_status": r.tax_status,
            "tax_due_date": r.tax_due_date,
            "mot_status": r.mot_status,
            "mot_expiry_date": r.mot_expiry_date,
            "fetched_at": r.fetched_at,
            "raw": json.loads(r.raw_json),
        }
