import json
from datetime import date, timedelta
from typing import Any

from torqued.repositories.base import BaseRepository

# DVSA reports odometer units as 'MI'/'KM'; we store 'mi'/'km' like everywhere else.
_UNIT_MAP = {"MI": "mi", "KM": "km"}

# An MOT surfaces as a maintenance reminder once its expiry is within this window
# (~2 months) or already lapsed.
MOT_DUE_SOON_DAYS = 60


class MotRepository(BaseRepository):
    def get_for_vehicle(self, vehicle_id: int) -> dict[str, Any] | None:
        """Return the stored DVSA snapshot for a vehicle (parsed defects), or None."""
        snapshot = self._row(
            self.db.execute(
                "SELECT * FROM dvsa_vehicles WHERE vehicle_id=?", (vehicle_id,)
            ).fetchone()
        )
        if snapshot is None:
            return None
        snapshot["raw"] = json.loads(snapshot.pop("raw_json"))
        tests = self._rows(
            self.db.execute(
                "SELECT * FROM mot_tests WHERE vehicle_id=?"
                " ORDER BY completed_date DESC, id DESC",
                (vehicle_id,),
            ).fetchall()
        )
        for t in tests:
            t["defects"] = json.loads(t.pop("defects_json"))
            del t["raw_json"]
        snapshot["tests"] = tests
        return snapshot

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
        placeholders = ",".join("?" * len(garage_ids))
        where = ""
        params: tuple[Any, ...] = tuple(garage_ids)
        if vehicle_id is not None:
            where, params = "AND v.id = ?", (*garage_ids, vehicle_id)
        rows = self._rows(
            self.db.execute(
                f"""
                SELECT v.id AS vehicle_id, v.name AS vehicle_name, v.kind AS vehicle_kind,
                       v.garage_id, v.odometer_unit AS vehicle_odometer_unit,
                       d.mot_test_due_date,
                       (SELECT t.expiry_date FROM mot_tests t
                         WHERE t.vehicle_id = v.id
                         ORDER BY t.completed_date DESC, t.id DESC
                         LIMIT 1) AS latest_expiry
                FROM vehicles v
                JOIN dvsa_vehicles d ON d.vehicle_id = v.id
                WHERE v.archived = 0
                  AND v.garage_id IN ({placeholders})
                  {where}
                """,
                params,
            ).fetchall()
        )
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

    def replace_for_vehicle(self, vehicle_id: int, payload: dict[str, Any]) -> None:
        """Store a fresh DVSA response, replacing any previous snapshot and tests."""
        self.db.execute("DELETE FROM dvsa_vehicles WHERE vehicle_id=?", (vehicle_id,))
        self.db.execute("DELETE FROM mot_tests WHERE vehicle_id=?", (vehicle_id,))
        self.db.execute(
            """
            INSERT INTO dvsa_vehicles (
                vehicle_id, registration, make, model, first_used_date, fuel_type,
                primary_colour, registration_date, manufacture_date, manufacture_year,
                engine_size, has_outstanding_recall, mot_test_due_date, raw_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                vehicle_id,
                payload.get("registration"),
                payload.get("make"),
                payload.get("model"),
                payload.get("firstUsedDate"),
                payload.get("fuelType"),
                payload.get("primaryColour"),
                payload.get("registrationDate"),
                payload.get("manufactureDate"),
                payload.get("manufactureYear"),
                payload.get("engineSize"),
                payload.get("hasOutstandingRecall"),
                payload.get("motTestDueDate"),
                json.dumps(payload),
            ),
        )
        for test in payload.get("motTests") or []:
            self.db.execute(
                """
                INSERT INTO mot_tests (
                    vehicle_id, completed_date, test_result, expiry_date, odometer_value,
                    odometer_unit, odometer_result_type, mot_test_number, data_source,
                    location, defects_json, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    vehicle_id,
                    test.get("completedDate"),
                    test.get("testResult"),
                    test.get("expiryDate"),
                    test.get("odometerValue"),
                    _UNIT_MAP.get((test.get("odometerUnit") or "").upper()),
                    test.get("odometerResultType"),
                    test.get("motTestNumber"),
                    test.get("dataSource"),
                    test.get("location"),
                    json.dumps(test.get("defects") or []),
                    json.dumps(test),
                ),
            )

