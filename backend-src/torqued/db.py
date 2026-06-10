import os
import sqlite3
from pathlib import Path

_DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent / "data" / "garage.db")
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def get_db() -> sqlite3.Connection:
    db_path = os.environ.get("DB_PATH", _DEFAULT_DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def run_migrations() -> None:
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT     PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        applied = {r[0] for r in db.execute("SELECT version FROM schema_migrations").fetchall()}

    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        with get_db() as db:
            db.executescript(path.read_text())
            db.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
        print(f"  [migration] applied {version}")
