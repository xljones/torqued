import json
from typing import Any

from torqued.repositories.base import BaseRepository

# DVSA reports odometer units as 'MI'/'KM'; we store 'mi'/'km' like everywhere else.
_UNIT_MAP = {"MI": "mi", "KM": "km"}


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

