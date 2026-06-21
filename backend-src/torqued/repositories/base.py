from typing import Any

from sqlalchemy import RowMapping

from torqued.db import Connection


class BaseRepository:
    def __init__(self, db: Connection) -> None:
        self.db = db

    @staticmethod
    def _row(r: RowMapping | None) -> dict[str, Any] | None:
        """Convert a single row mapping to a mutable dict, or return None."""
        return dict(r) if r is not None else None

    @staticmethod
    def _rows(rs: list[RowMapping]) -> list[dict[str, Any]]:
        """Convert a list of row mappings to a list of mutable dicts."""
        return [dict(r) for r in rs]
