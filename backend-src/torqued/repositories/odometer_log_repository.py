from typing import Any

from torqued.repositories.base import BaseRepository


class OdometerLogRepository(BaseRepository):
    def list_for_vehicle(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return a vehicle's manual odometer logs, newest first."""
        return self._rows(
            self.execute(
                "SELECT * FROM odometer_logs WHERE vehicle_id=? AND source='manual'"
                " ORDER BY date DESC, odometer_km DESC, id DESC",
                (vehicle_id,),
            ).fetchall()
        )

    def get_by_id(self, log_id: int) -> dict[str, Any] | None:
        """Return a single odometer log by primary key, or None if not found."""
        return self._row(
            self.execute("SELECT * FROM odometer_logs WHERE id=?", (log_id,)).fetchone()
        )

    def create(
        self,
        vehicle_id: int,
        date: str,
        odometer_km: float,
        unit: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Insert a manual odometer reading (stored canonically in km)."""
        inserted = self.execute(
            "INSERT INTO odometer_logs (vehicle_id, date, odometer_km, unit, note)"
            " VALUES (?,?,?,?,?) RETURNING id",
            (vehicle_id, date, odometer_km, unit, note),
        ).fetchone()
        if inserted is None:  # pragma: no cover
            raise RuntimeError("INSERT returned no row ID")
        log = self.get_by_id(inserted["id"])
        if log is None:  # pragma: no cover
            raise RuntimeError(f"Row {inserted['id']} not found after INSERT")
        return log

    def delete(self, log_id: int) -> bool:
        """Delete an odometer log by primary key; return True if a row was removed."""
        return self.execute("DELETE FROM odometer_logs WHERE id=?", (log_id,)).rowcount > 0
