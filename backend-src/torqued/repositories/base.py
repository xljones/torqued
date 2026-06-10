import sqlite3
from typing import Any


class BaseRepository:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
        """Convert a single sqlite3.Row to a dict, or return None if the row is None."""
        return dict(r) if r else None

    @staticmethod
    def _rows(rs: list[sqlite3.Row]) -> list[dict[str, Any]]:
        """Convert a list of sqlite3.Row objects to a list of dicts."""
        return [dict(r) for r in rs]
