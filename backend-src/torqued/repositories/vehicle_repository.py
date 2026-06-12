import json
from typing import Any

from torqued import mot
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


class VehicleRepository(BaseRepository):
    def list_for_garages(
        self, garage_ids: list[int], include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """Return the garages' vehicles with counts and a cover photo, newest first."""
        if not garage_ids:
            return []
        placeholders = ",".join("?" * len(garage_ids))
        archived = "" if include_archived else "AND v.archived = 0"
        vehicles = self._rows(
            self.db.execute(
                f"""
            SELECT v.*, g.name AS garage_name,
                   (SELECT COUNT(*) FROM service_logs s WHERE s.vehicle_id = v.id) AS service_count,
                   (SELECT COUNT(*) FROM photos p WHERE p.vehicle_id = v.id) AS photo_count,
                   (SELECT p.id FROM photos p WHERE p.vehicle_id = v.id
                    ORDER BY p.service_log_id IS NOT NULL, p.created_at ASC
                    LIMIT 1) AS cover_photo_id
            FROM vehicles v
            JOIN garages g ON g.id = v.garage_id
            WHERE v.garage_id IN ({placeholders}) {archived}
            ORDER BY v.archived ASC, v.created_at DESC
        """,
                tuple(garage_ids),
            ).fetchall()
        )
        latest = self.latest_odometers()
        baselines = self.mot_baselines([v["id"] for v in vehicles])
        for v in vehicles:
            v["latest_odometer"] = latest.get(v["id"])
            v["mot_baseline"] = baselines.get(v["id"])
        return vehicles

    def get_by_id(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return a single vehicle row by primary key, or None if not found."""
        return self._row(
            self.db.execute("SELECT * FROM vehicles WHERE id=?", (vehicle_id,)).fetchone()
        )

    def get_detail(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return a vehicle with its specs, photos, and latest odometer reading."""
        vehicle = self.get_by_id(vehicle_id)
        if not vehicle:
            return None
        garage = self.db.execute(
            "SELECT name FROM garages WHERE id=?", (vehicle["garage_id"],)
        ).fetchone()
        vehicle["garage_name"] = garage["name"] if garage else None
        vehicle["specs"] = self._rows(
            self.db.execute(
                "SELECT id, name, value, position FROM vehicle_specs"
                " WHERE vehicle_id=? ORDER BY position ASC, id ASC",
                (vehicle_id,),
            ).fetchall()
        )
        vehicle["photos"] = self._rows(
            self.db.execute(
                """
                SELECT p.*, u.username AS uploaded_by_username, s.title AS service_title
                FROM photos p
                LEFT JOIN users u ON u.id = p.uploaded_by
                LEFT JOIN service_logs s ON s.id = p.service_log_id
                WHERE p.vehicle_id=? ORDER BY p.created_at DESC, p.id DESC
                """,
                (vehicle_id,),
            ).fetchall()
        )
        vehicle["latest_odometer"] = self.latest_odometers().get(vehicle_id)
        vehicle["mot_baseline"] = self.mot_baseline(vehicle_id)
        return vehicle

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
        placeholders = ",".join("?" * len(vehicle_ids))
        rows = self.db.execute(
            f"SELECT vehicle_id, raw_json FROM dvsa_vehicles WHERE vehicle_id IN ({placeholders})",
            tuple(vehicle_ids),
        ).fetchall()
        return {r["vehicle_id"]: mot.to_baseline(json.loads(r["raw_json"])) for r in rows}

    def create(
        self, garage_id: int, data: dict[str, Any], changed_by: int | None = None
    ) -> dict[str, Any]:
        """Insert a new vehicle into a garage and record its initial history snapshot."""
        data = {"kind": "car", "odometer_unit": "mi", "archived": 0, **{
            k: v for k, v in data.items() if v is not None
        }}
        cols = ",".join(VEHICLE_FIELDS)
        marks = ",".join("?" * len(VEHICLE_FIELDS))
        cur = self.db.execute(
            f"INSERT INTO vehicles (garage_id, {cols}) VALUES (?,{marks})",
            (garage_id, *(data.get(f) for f in VEHICLE_FIELDS)),
        )
        row_id = cur.lastrowid
        if row_id is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        vehicle = self.get_by_id(row_id)
        if vehicle is None:  # pragma: no cover
            raise RuntimeError(f"Row {row_id} not found after INSERT")
        self._record_history(vehicle, changed_by)
        return vehicle

    def update(
        self, vehicle_id: int, data: dict[str, Any], changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Update vehicle fields, record a history snapshot, and return the updated row."""
        sets = ",".join(f"{f}=?" for f in VEHICLE_FIELDS)
        self.db.execute(
            f"UPDATE vehicles SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (*(data.get(f) for f in VEHICLE_FIELDS), vehicle_id),
        )
        vehicle = self.get_by_id(vehicle_id)
        if vehicle is not None:
            self._record_history(vehicle, changed_by)
        return vehicle

    def delete(self, vehicle_id: int) -> bool:
        """Delete a vehicle (cascades to specs, logs, photos); return True if a row was removed."""
        return self.db.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,)).rowcount > 0

    def replace_specs(self, vehicle_id: int, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace the vehicle's free-form spec list; return the new specs in order."""
        self.db.execute("DELETE FROM vehicle_specs WHERE vehicle_id=?", (vehicle_id,))
        for i, spec in enumerate(specs):
            self.db.execute(
                "INSERT INTO vehicle_specs (vehicle_id, name, value, position) VALUES (?,?,?,?)",
                (vehicle_id, spec["name"], spec["value"], i),
            )
        return self._rows(
            self.db.execute(
                "SELECT id, name, value, position FROM vehicle_specs"
                " WHERE vehicle_id=? ORDER BY position ASC, id ASC",
                (vehicle_id,),
            ).fetchall()
        )

    def latest_odometers(self) -> dict[int, dict[str, Any]]:
        """Return the most recent odometer reading per vehicle across all three sources."""
        rows = self.db.execute("""
            SELECT vehicle_id, date, odometer_km FROM odometer_logs WHERE source='manual'
            UNION ALL
            SELECT vehicle_id, SUBSTR(completed_date, 1, 10) AS date,
                   CASE odometer_unit WHEN 'mi' THEN CAST(odometer_value AS REAL) * 1.609344
                                      ELSE CAST(odometer_value AS REAL) END AS odometer_km
            FROM mot_tests WHERE odometer_value IS NOT NULL AND odometer_unit IS NOT NULL
            UNION ALL
            SELECT vehicle_id, date, odometer_km FROM service_logs WHERE odometer_km IS NOT NULL
            ORDER BY date ASC, odometer_km ASC
        """).fetchall()
        latest: dict[int, dict[str, Any]] = {}
        for r in rows:
            latest[r["vehicle_id"]] = {"date": r["date"], "odometer_km": r["odometer_km"]}
        return latest

    def mileage_series(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return the merged odometer timeline (manual, MOT, service), oldest first."""
        return self._rows(
            self.db.execute(
                """
                SELECT 'manual' AS source, id, date, odometer_km, unit, note
                FROM odometer_logs WHERE vehicle_id=? AND source='manual'
                UNION ALL
                SELECT 'mot' AS source, id, SUBSTR(completed_date, 1, 10) AS date,
                       CASE odometer_unit WHEN 'mi' THEN CAST(odometer_value AS REAL) * 1.609344
                                          ELSE CAST(odometer_value AS REAL) END AS odometer_km,
                       odometer_unit AS unit,
                       'MOT test (' || test_result || ')' AS note
                FROM mot_tests
                WHERE vehicle_id=? AND odometer_value IS NOT NULL AND odometer_unit IS NOT NULL
                UNION ALL
                SELECT 'service' AS source, id, date, odometer_km, odometer_unit AS unit,
                       title AS note
                FROM service_logs WHERE vehicle_id=? AND odometer_km IS NOT NULL
                ORDER BY date ASC, odometer_km ASC
                """,
                (vehicle_id, vehicle_id, vehicle_id),
            ).fetchall()
        )

    def get_history(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return full audit history for a vehicle, newest first, with username."""
        return self._rows(
            self.db.execute(
                """
                SELECT vh.*, u.username AS changed_by_username
                FROM vehicle_history vh
                LEFT JOIN users u ON u.id = vh.changed_by
                WHERE vh.vehicle_id = ?
                ORDER BY vh.changed_at DESC, vh.id DESC
                """,
                (vehicle_id,),
            ).fetchall()
        )

    def revert(
        self, vehicle_id: int, version_id: int, changed_by: int | None = None
    ) -> dict[str, Any] | None:
        """Restore a vehicle from a history record; return None if the record doesn't exist."""
        h = self._row(
            self.db.execute(
                "SELECT * FROM vehicle_history WHERE id=? AND vehicle_id=?",
                (version_id, vehicle_id),
            ).fetchone()
        )
        if not h:
            return None
        return self.update(vehicle_id, h, changed_by=changed_by)

    def _record_history(self, vehicle: dict[str, Any], changed_by: int | None) -> None:
        """Write a snapshot of the vehicle's current field values to vehicle_history."""
        cols = ",".join(VEHICLE_FIELDS)
        marks = ",".join("?" * len(VEHICLE_FIELDS))
        self.db.execute(
            f"INSERT INTO vehicle_history (vehicle_id, changed_by, {cols}) VALUES (?,?,{marks})",
            (vehicle["id"], changed_by, *(vehicle.get(f) for f in VEHICLE_FIELDS)),
        )

    def search(self, query: str, garage_ids: list[int]) -> list[dict[str, Any]]:
        """Return up to 10 in-scope vehicles matching name, make, model, or plate."""
        if not garage_ids:
            return []
        placeholders = ",".join("?" * len(garage_ids))
        q = f"%{query}%"
        return self._rows(
            self.db.execute(
                f"""
                SELECT v.*, 'vehicle' AS type FROM vehicles v
                WHERE v.garage_id IN ({placeholders})
                  AND (v.name LIKE ? OR v.make LIKE ? OR v.model LIKE ? OR v.registration LIKE ?)
                LIMIT 10
                """,
                (*garage_ids, q, q, q, q),
            ).fetchall()
        )
