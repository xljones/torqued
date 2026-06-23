from collections.abc import Sequence
from typing import Any

from sqlalchemy import RowMapping
from sqlalchemy.orm import Session

from torqued.db import Result, execute_sql


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        """Run a raw ``?``-placeholder statement (repositories not yet on the ORM)."""
        return execute_sql(self.session, sql, params)

    @staticmethod
    def _row(r: RowMapping | None) -> dict[str, Any] | None:
        """Convert a single row mapping to a mutable dict, or return None."""
        return dict(r) if r is not None else None

    @staticmethod
    def _rows(rs: list[RowMapping]) -> list[dict[str, Any]]:
        """Convert a list of row mappings to a list of mutable dicts."""
        return [dict(r) for r in rs]
