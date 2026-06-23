from typing import Any

from sqlalchemy import select

from torqued.models import OdometerLog, to_dict
from torqued.repositories.base import BaseRepository


class OdometerLogRepository(BaseRepository):
    def list_for_vehicle(self, vehicle_id: int) -> list[dict[str, Any]]:
        """Return a vehicle's manual odometer logs, newest first."""
        rows = self.session.scalars(
            select(OdometerLog)
            .where(OdometerLog.vehicle_id == vehicle_id, OdometerLog.source == "manual")
            .order_by(
                OdometerLog.date.desc(),
                OdometerLog.odometer_km.desc(),
                OdometerLog.id.desc(),
            )
        ).all()
        return [to_dict(r) for r in rows]

    def get_by_id(self, log_id: int) -> dict[str, Any] | None:
        """Return a single odometer log by primary key, or None if not found."""
        log = self.session.get(OdometerLog, log_id)
        return to_dict(log) if log else None

    def create(
        self,
        vehicle_id: int,
        date: str,
        odometer_km: float,
        unit: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Insert a manual odometer reading (stored canonically in km)."""
        log = OdometerLog(
            vehicle_id=vehicle_id, date=date, odometer_km=odometer_km, unit=unit, note=note
        )
        self.session.add(log)
        self.session.flush()  # assigns the primary key and emits the INSERT
        self.session.refresh(log)  # pull DB-side defaults (source, created_at)
        return to_dict(log)

    def delete(self, log_id: int) -> bool:
        """Delete an odometer log by primary key; return True if a row was removed."""
        log = self.session.get(OdometerLog, log_id)
        if log is None:
            return False
        self.session.delete(log)
        return True
