from typing import Any, cast

from sqlalchemy import CursorResult, Executable
from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def affected(self, statement: Executable) -> int:
        """Run a Core INSERT/UPDATE/DELETE construct and return the affected row count."""
        return cast(CursorResult[Any], self.session.execute(statement)).rowcount
