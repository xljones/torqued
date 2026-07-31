import json
from typing import Any

from sqlalchemy import Float, case, cast, delete, func, literal, or_, select, union_all, update
from sqlalchemy.orm import aliased

from torqued import mot, ves
from torqued.db import utcnow_text
from torqued.models import (
    DvsaVehicle,
    Garage,
    MotTest,
    OdometerLog,
    Photo,
    ServiceLog,
    User,
    Vehicle,
    VehicleHistory,
    VehicleSpec,
    VehicleVes,
    to_dict,
)
from torqued.repositories.base import BaseRepository

# Editable vehicle fields, in schema order. History snapshots mirror this list.
VEHICLE_FIELDS: list[str] = [
    "name",
    "kind",
    "make",
    "model",
    "year",
    "registration",
    "vin",
    "colour",
    "fuel_type",
    "odometer_unit",
    "purchase_date",
    "tyre_size_front",
    "tyre_size_rear",
    "tyre_pressure_front_psi",
    "tyre_pressure_rear_psi",
    "notes",
    "archived",
    "engine_size",
    "first_used_date",
    "registration_date",
]


def _mot_km(value: Any, unit: Any) -> Any:
    """SQL expression converting an MOT odometer reading to km (mi readings * 1.609344)."""
    return case(
        (unit == "mi", cast(value, Float) * 1.609344),
        else_=cast(value, Float),
    )


class VehicleRepository(BaseRepository):
    def list_for_garages(
        self, garage_ids: list[int], include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """Return the garages' vehicles with counts and a cover photo, newest first."""
        if not garage_ids:
            return []
        service_count = (
            select(func.count())
            .select_from(ServiceLog)
            .where(ServiceLog.vehicle_id == Vehicle.id)
            .correlate(Vehicle)
        ).scalar_subquery()
        photo_count = (
            select(func.count())
            .select_from(Photo)
            .where(Photo.vehicle_id == Vehicle.id)
            .correlate(Vehicle)
        ).scalar_subquery()
        cover_photo_id = func.coalesce(
            Vehicle.cover_photo_id,
            (
                select(Photo.id)
                .where(Photo.vehicle_id == Vehicle.id)
                .order_by(Photo.created_at.desc(), Photo.id.desc())
                .limit(1)
                .correlate(Vehicle)
            ).scalar_subquery(),
        )
        # Second alias of Photo, joined on the resolved cover id, so the card image can
        # apply the same cover-crop framing the lightbox editor saved for that photo.
        CoverPhoto = aliased(Photo)
        stmt = (
            select(
                Vehicle,
                Garage.name.label("garage_name"),
                service_count.label("service_count"),
                photo_count.label("photo_count"),
                cover_photo_id.label("cover_photo_id"),
                CoverPhoto.cover_focal_x.label("cover_focal_x"),
                CoverPhoto.cover_focal_y.label("cover_focal_y"),
                CoverPhoto.cover_zoom.label("cover_zoom"),
            )
            .join(Garage, Garage.id == Vehicle.garage_id)
            .outerjoin(CoverPhoto, CoverPhoto.id == cover_photo_id)
            .where(Vehicle.garage_id.in_(garage_ids))
        )
        if not include_archived:
            stmt = stmt.where(Vehicle.archived == 0)
        stmt = stmt.order_by(Vehicle.archived.asc(), Vehicle.created_at.desc())
        vehicles = [
            {
                **to_dict(vehicle),
                "garage_name": garage_name,
                "service_count": service_count_,
                "photo_count": photo_count_,
                "cover_photo_id": cover_photo_id_,
                "cover_focal_x": cover_focal_x_,
                "cover_focal_y": cover_focal_y_,
                "cover_zoom": cover_zoom_,
            }
            for (
                vehicle,
                garage_name,
                service_count_,
                photo_count_,
                cover_photo_id_,
                cover_focal_x_,
                cover_focal_y_,
                cover_zoom_,
            ) in (self.session.execute(stmt).all())
        ]
        ids = [v["id"] for v in vehicles]
        latest = self.latest_odometers()
        baselines = self.mot_baselines(ids)
        mot_summaries = self.mot_summaries(ids)
        tax_summaries = self.tax_summaries(ids)
        for v in vehicles:
            v["latest_odometer"] = latest.get(v["id"])
            v["mot_baseline"] = baselines.get(v["id"])
            v["mot_summary"] = mot_summaries.get(v["id"])
            v["tax_summary"] = tax_summaries.get(v["id"])
        return vehicles

    def get_by_id(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return a single vehicle row by primary key, or None if not found."""
        vehicle = self.session.get(Vehicle, vehicle_id)
        return to_dict(vehicle) if vehicle else None

    def garage_id_for(self, vehicle_id: int) -> int | None:
        """Return the id of the garage owning a vehicle, or None if it doesn't exist."""
        return self.session.scalars(
            select(Vehicle.garage_id).where(Vehicle.id == vehicle_id)
        ).first()

    def get_detail(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return a vehicle with its specs, photos, and latest odometer reading."""
        vehicle = self.get_by_id(vehicle_id)
        if not vehicle:
            return None
        vehicle["garage_name"] = self.session.scalars(
            select(Garage.name).where(Garage.id == vehicle["garage_id"])
        ).first()
        vehicle["specs"] = self._specs(vehicle_id)
        photo_rows = self.session.execute(
            select(
                Photo,
                User.username.label("uploaded_by_username"),
                ServiceLog.title.label("service_title"),
            )
            .outerjoin(User, User.id == Photo.uploaded_by)
            .outerjoin(ServiceLog, ServiceLog.id == Photo.service_log_id)
            .where(Photo.vehicle_id == vehicle_id)
            .order_by(Photo.created_at.desc(), Photo.id.desc())
        ).all()
        vehicle["photos"] = [
            {**to_dict(photo), "uploaded_by_username": username, "service_title": service_title}
            for photo, username, service_title in photo_rows
        ]
        # Effective cover: the pinned photo if it still exists, else the latest upload
        # (photos are ordered newest-first above). Keeps the detail-view glyph in step
        # with the list card, which applies the same fallback in SQL.
        photo_ids = {p["id"] for p in vehicle["photos"]}
        if vehicle["cover_photo_id"] not in photo_ids:
            vehicle["cover_photo_id"] = vehicle["photos"][0]["id"] if vehicle["photos"] else None
        vehicle["latest_odometer"] = self.latest_odometers().get(vehicle_id)
        vehicle["mot_baseline"] = self.mot_baseline(vehicle_id)
        # DVLA VES supplements DVSA for the detail card: `ves_baseline` carries the
        # DVLA-only fields (and DVLA fallbacks), `field_sources` tags every field DVSA /
        # DVLA / both once the two sources are normalised (see torqued.ves).
        ves_snapshot = self._ves_snapshot(vehicle_id)
        vehicle["ves_baseline"] = ves.to_baseline(ves_snapshot) if ves_snapshot else None
        vehicle["field_sources"] = ves.field_sources(vehicle["mot_baseline"], ves_snapshot)
        return vehicle

    def _ves_snapshot(self, vehicle_id: int) -> dict[str, Any] | None:
        """The live DVLA VES snapshot for a vehicle (parsed raw_json), or None."""
        raw = self.session.execute(
            select(VehicleVes.raw_json).where(VehicleVes.vehicle_id == vehicle_id)
        ).scalar_one_or_none()
        return json.loads(raw) if raw else None

    def _specs(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return a vehicle's spec rows ordered by position."""
        rows = (
            self.session.execute(
                select(VehicleSpec.id, VehicleSpec.name, VehicleSpec.value, VehicleSpec.position)
                .where(VehicleSpec.vehicle_id == vehicle_id)
                .order_by(VehicleSpec.position.asc(), VehicleSpec.id.asc())
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def mot_baseline(self, vehicle_id: int) -> dict[str, Any] | None:
        """Map the stored DVSA snapshot onto vehicle detail fields, or None if not fetched.

        These are the *baseline* values shown when the matching vehicle column is
        unset; a non-null column overrides them.
        """
        return self.mot_baselines([vehicle_id]).get(vehicle_id)

    def mot_baselines(self, vehicle_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Batch the MOT baseline lookup for several vehicles in one query."""
        if not vehicle_ids:
            return {}
        rows = self.session.execute(
            select(DvsaVehicle.vehicle_id, DvsaVehicle.raw_json).where(
                DvsaVehicle.vehicle_id.in_(vehicle_ids)
            )
        ).all()
        return {vid: mot.to_baseline(json.loads(raw)) for vid, raw in rows}

    def mot_summaries(self, vehicle_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Compact per-vehicle MOT status for the list view: ``{expiry, failed}``.

        ``expiry`` is the **later** of the latest DVSA test's expiry (falling back to the
        DVSA vehicle-level due date) and the DVLA VES current-status expiry — so the list
        pill consolidates both sources exactly like the detail card, and a fresh VES status
        overrides a stale DVSA history. ``failed`` marks a latest DVSA test that didn't pass,
        unless the VES expiry governs (a newer pass exists per the DVLA). A vehicle is
        included if it has either source stored.
        """
        if not vehicle_ids:
            return {}
        # vehicle_ids are live vehicle ids, so every matched row has a non-null vehicle_id
        # (a detached snapshot's NULL can't match an IN list); the filter just narrows the type.
        due: dict[int, str | None] = {
            vid: due_date
            for vid, due_date in self.session.execute(
                select(DvsaVehicle.vehicle_id, DvsaVehicle.mot_test_due_date).where(
                    DvsaVehicle.vehicle_id.in_(vehicle_ids)
                )
            ).all()
            if vid is not None
        }
        latest: dict[int, tuple[Any, Any]] = {}
        rows = self.session.execute(
            select(MotTest.vehicle_id, MotTest.expiry_date, MotTest.test_result)
            .where(MotTest.vehicle_id.in_(vehicle_ids))
            .order_by(MotTest.vehicle_id, MotTest.completed_date.desc(), MotTest.id.desc())
        ).all()
        for vid, expiry, result in rows:
            latest.setdefault(vid, (expiry, result))
        ves: dict[int, str | None] = {
            vid: expiry
            for vid, expiry in self.session.execute(
                select(VehicleVes.vehicle_id, VehicleVes.mot_expiry_date).where(
                    VehicleVes.vehicle_id.in_(vehicle_ids)
                )
            ).all()
            if vid is not None
        }
        summaries: dict[int, dict[str, Any]] = {}
        for vid in due.keys() | ves.keys():
            dvsa_expiry, result = latest.get(vid, (None, None))
            dvsa_expiry = dvsa_expiry or due.get(vid)
            ves_expiry = ves.get(vid)
            # ISO YYYY-MM-DD strings sort chronologically, so max() is the later date.
            expiry = max((d for d in (dvsa_expiry, ves_expiry) if d), default=None)
            ves_governs = ves_expiry is not None and (
                dvsa_expiry is None or ves_expiry >= dvsa_expiry
            )
            failed = (
                result is not None and (result or "").upper() != "PASSED" and not ves_governs
            )
            summaries[vid] = {"expiry": expiry, "failed": failed}
        return summaries

    def tax_summaries(self, vehicle_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Compact per-vehicle tax status for the list view: ``{tax_status, tax_due_date}``."""
        if not vehicle_ids:
            return {}
        rows = self.session.execute(
            select(
                VehicleVes.vehicle_id, VehicleVes.tax_status, VehicleVes.tax_due_date
            ).where(VehicleVes.vehicle_id.in_(vehicle_ids))
        ).all()
        return {
            vid: {"tax_status": status, "tax_due_date": due}
            for vid, status, due in rows
        }

    def create(
        self, garage_id: int, data: dict[str, Any], changed_by: int | None = None
    ) -> dict[str, Any]:
        """Insert a new vehicle into a garage and record its initial history snapshot."""
        data = {"kind": "car", "odometer_unit": "mi", "archived": 0, **{
            k: v for k, v in data.items() if v is not None
        }}
        vehicle_row = Vehicle(garage_id=garage_id, **{f: data.get(f) for f in VEHICLE_FIELDS})
        self.session.add(vehicle_row)
        self.session.flush()
        vehicle = self.get_by_id(vehicle_row.id)
        if vehicle is None:  # pragma: no cover
            raise RuntimeError(f"Row {vehicle_row.id} not found after INSERT")
        self._record_history(vehicle, changed_by)
        return vehicle

    def update(
        self, vehicle_id: int, data: dict[str, Any], changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Update vehicle fields, record a history snapshot, and return the updated row."""
        values = {f: data.get(f) for f in VEHICLE_FIELDS}
        values["updated_at"] = utcnow_text()
        self.session.execute(update(Vehicle).where(Vehicle.id == vehicle_id).values(values))
        vehicle = self.get_by_id(vehicle_id)
        if vehicle is not None:
            self._record_history(vehicle, changed_by)
        return vehicle

    def set_cover_photo(self, vehicle_id: int, photo_id: int) -> None:
        """Pin a specific photo as the vehicle's cover (get_detail derives the fallback)."""
        self.session.execute(
            update(Vehicle).where(Vehicle.id == vehicle_id).values(cover_photo_id=photo_id)
        )

    def delete(self, vehicle_id: int) -> bool:
        """Delete a vehicle (cascades to specs, logs, photos); return True if a row was removed."""
        return self.affected(delete(Vehicle).where(Vehicle.id == vehicle_id)) > 0

    def replace_specs(self, vehicle_id: int, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace the vehicle's free-form spec list; return the new specs in order."""
        self.session.execute(delete(VehicleSpec).where(VehicleSpec.vehicle_id == vehicle_id))
        for i, spec in enumerate(specs):
            self.session.add(
                VehicleSpec(
                    vehicle_id=vehicle_id, name=spec["name"], value=spec["value"], position=i
                )
            )
        return self._specs(vehicle_id)

    def latest_odometers(self) -> dict[int, dict[str, Any]]:
        """Return the most recent odometer reading per vehicle across all three sources."""
        manual = select(
            OdometerLog.vehicle_id, OdometerLog.date, OdometerLog.odometer_km
        ).where(OdometerLog.source == "manual")
        mot_q = select(
            MotTest.vehicle_id,
            func.substr(MotTest.completed_date, 1, 10).label("date"),
            _mot_km(MotTest.odometer_value, MotTest.odometer_unit).label("odometer_km"),
        ).where(MotTest.odometer_value.is_not(None), MotTest.odometer_unit.is_not(None))
        service = select(
            ServiceLog.vehicle_id, ServiceLog.date, ServiceLog.odometer_km
        ).where(ServiceLog.odometer_km.is_not(None))
        combined = union_all(manual, mot_q, service).subquery()
        rows = (
            self.session.execute(
                select(combined.c.vehicle_id, combined.c.date, combined.c.odometer_km).order_by(
                    combined.c.date.asc(), combined.c.odometer_km.asc()
                )
            )
            .mappings()
            .all()
        )
        latest: dict[int, dict[str, Any]] = {}
        for r in rows:
            latest[r["vehicle_id"]] = {"date": r["date"], "odometer_km": r["odometer_km"]}
        return latest

    def mileage_series(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return the merged odometer timeline (manual, MOT, service), oldest first."""
        manual = select(
            literal("manual").label("source"),
            OdometerLog.id,
            OdometerLog.date,
            OdometerLog.odometer_km,
            OdometerLog.unit,
            OdometerLog.note,
        ).where(OdometerLog.vehicle_id == vehicle_id, OdometerLog.source == "manual")
        mot_q = select(
            literal("mot").label("source"),
            MotTest.id,
            func.substr(MotTest.completed_date, 1, 10).label("date"),
            _mot_km(MotTest.odometer_value, MotTest.odometer_unit).label("odometer_km"),
            MotTest.odometer_unit.label("unit"),
            (literal("MOT test (") + MotTest.test_result + literal(")")).label("note"),
        ).where(
            MotTest.vehicle_id == vehicle_id,
            MotTest.odometer_value.is_not(None),
            MotTest.odometer_unit.is_not(None),
        )
        service = select(
            literal("service").label("source"),
            ServiceLog.id,
            ServiceLog.date,
            ServiceLog.odometer_km,
            ServiceLog.odometer_unit.label("unit"),
            ServiceLog.title.label("note"),
        ).where(ServiceLog.vehicle_id == vehicle_id, ServiceLog.odometer_km.is_not(None))
        combined = union_all(manual, mot_q, service).subquery()
        rows = (
            self.session.execute(
                select(combined).order_by(combined.c.date.asc(), combined.c.odometer_km.asc())
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def get_history(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return full audit history for a vehicle, newest first, with username."""
        rows = self.session.execute(
            select(VehicleHistory, User.username.label("changed_by_username"))
            .outerjoin(User, User.id == VehicleHistory.changed_by)
            .where(VehicleHistory.vehicle_id == vehicle_id)
            .order_by(VehicleHistory.changed_at.desc(), VehicleHistory.id.desc())
        ).all()
        return [{**to_dict(h), "changed_by_username": username} for h, username in rows]

    def revert(
        self, vehicle_id: int, version_id: int, changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Restore a vehicle from a history record; return None if the record doesn't exist."""
        h = self.session.execute(
            select(VehicleHistory).where(
                VehicleHistory.id == version_id, VehicleHistory.vehicle_id == vehicle_id
            )
        ).scalar_one_or_none()
        if h is None:
            return None
        return self.update(vehicle_id, to_dict(h), changed_by=changed_by)

    def _record_history(self, vehicle: dict[str, Any], changed_by: int | None) -> None:
        """Write a snapshot of the vehicle's current field values to vehicle_history."""
        self.session.add(
            VehicleHistory(
                vehicle_id=vehicle["id"],
                changed_by=changed_by,
                **{f: vehicle.get(f) for f in VEHICLE_FIELDS},
            )
        )

    def search(self, query: str, garage_ids: list[int]) -> list[dict[str, Any]]:
        """Return up to 10 in-scope vehicles matching name, make, model, or plate."""
        if not garage_ids:
            return []
        like = f"%{query}%"
        rows = self.session.execute(
            select(Vehicle, literal("vehicle").label("type"))
            .where(
                Vehicle.garage_id.in_(garage_ids),
                or_(
                    func.lower(Vehicle.name).like(func.lower(like)),
                    func.lower(Vehicle.make).like(func.lower(like)),
                    func.lower(Vehicle.model).like(func.lower(like)),
                    func.lower(Vehicle.registration).like(func.lower(like)),
                ),
            )
            .limit(10)
        ).all()
        return [{**to_dict(vehicle), "type": type_} for vehicle, type_ in rows]
