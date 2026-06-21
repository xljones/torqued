#!/usr/bin/env python3
"""Management CLI. Usage: python manage.py <command> [args]"""
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
# Load the project .env so CLI commands target the same database as the web app.
# On PythonAnywhere a console doesn't otherwise have DATABASE_URL set; existing
# environment variables (e.g. Docker Compose's) are not overridden.
load_dotenv(Path(__file__).parent.parent / ".env")


def cmd_create_user(args: list[str]) -> None:
    is_admin = "--admin" in args
    args = [a for a in args if a != "--admin"]
    if len(args) != 2:
        print("Usage: python manage.py create-user <username> <password> [--admin]")
        sys.exit(1)
    username, password = args
    from torqued.db import get_db
    from torqued.repositories.user_repository import UserRepository
    with get_db() as db:
        repo = UserRepository(db)
        if repo.get_by_username(username):
            print(f"Error: user '{username}' already exists")
            sys.exit(1)
        repo.create(username, password, is_admin=is_admin)
    kind = "admin" if is_admin else "normal"
    print(f"{kind.capitalize()} user '{username}' created.")


def cmd_list_users(_: list[str]) -> None:
    from torqued.db import get_db
    from torqued.repositories.user_repository import UserRepository
    with get_db() as db:
        users = UserRepository(db).list_all()
    if not users:
        print("No users.")
    for u in users:
        kind = "site admin" if u["is_admin"] else "normal"
        expiry = f"  expires {u['expires_at']}" if u["expires_at"] else ""
        garages = ", ".join(
            f"{m['garage_name']} ({m['role']})" for m in u["memberships"]
        ) or "no garages"
        print(f"  [{u['id']}] {u['username']}  ({kind}{expiry})  {garages}")


def cmd_seed(_: list[str]) -> None:
    from torqued.db import get_db, run_migrations
    from torqued.repositories.garage_repository import GarageRepository
    from torqued.repositories.odometer_log_repository import OdometerLogRepository
    from torqued.repositories.service_log_repository import ServiceLogRepository
    from torqued.repositories.vehicle_repository import VehicleRepository
    from torqued.units import to_km

    run_migrations()

    GARAGE_NAME = "Home Garage"

    VEHICLES = [
        {
            "name": "Street Triple",
            "kind": "motorcycle",
            "make": "Triumph",
            "model": "Street Triple RS",
            "year": 2021,
            "registration": "LB21 XYZ",
            "colour": "Silver Ice",
            "fuel_type": "Petrol",
            "odometer_unit": "mi",
            "purchase_date": "2022-03-12",
            "tyre_size_front": "120/70 ZR17",
            "tyre_size_rear": "180/55 ZR17",
            "tyre_pressure_front_psi": 36.0,
            "tyre_pressure_rear_psi": 42.0,
            "notes": "Quickshifter fitted. Arrow exhaust.",
            "specs": [
                ("Engine oil", "10W-40 fully synthetic, 3.1 L with filter"),
                ("Chain slack", "20–30 mm on side stand"),
                ("Rear axle torque", "110 Nm"),
                ("Battery", "YTX9-BS"),
            ],
        },
        {
            "name": "Daily",
            "kind": "car",
            "make": "Honda",
            "model": "Civic 1.0 VTEC Turbo",
            "year": 2019,
            "registration": "KK19 ABC",
            "colour": "Polished Metal",
            "fuel_type": "Petrol",
            "odometer_unit": "mi",
            "purchase_date": "2021-08-02",
            "tyre_size_front": "215/55 R16",
            "tyre_size_rear": "215/55 R16",
            "tyre_pressure_front_psi": 32.0,
            "tyre_pressure_rear_psi": 30.0,
            "notes": None,
            "specs": [
                ("Engine oil", "0W-20, 3.5 L with filter"),
                ("Wheel nut torque", "108 Nm"),
                ("Wiper blades", "Bosch Aerotwin A862S"),
            ],
        },
        {
            "name": "Weekend toy",
            "kind": "car",
            "make": "Mazda",
            "model": "MX-5 NC 2.0 Sport",
            "year": 2008,
            "registration": "WX08 DEF",
            "colour": "True Red",
            "fuel_type": "Petrol",
            "odometer_unit": "km",
            "purchase_date": "2023-05-20",
            "tyre_size_front": "205/45 R17",
            "tyre_size_rear": "205/45 R17",
            "tyre_pressure_front_psi": 29.0,
            "tyre_pressure_rear_psi": 29.0,
            "notes": "Imported. Odometer in km.",
            "specs": [
                ("Engine oil", "5W-30, 4.3 L with filter"),
                ("Soft top care", "Renovo treatment yearly"),
            ],
        },
    ]

    # (vehicle_name, date, title, category, description, performed_by, cost,
    #  odometer, odometer_unit, next_due_date, next_due_distance)
    SERVICES = [
        ("Street Triple", "2024-04-02", "Annual service", "Service",
         "Oil + filter, air filter, plugs checked, all torques checked.",
         "Triumph Leicester", 289.00, 8200, "mi", "2025-04-02", 14200),
        ("Street Triple", "2024-09-14", "Chain clean & adjust", "Chain & sprockets",
         "Cleaned, lubed, slack set to 25 mm.", "Me", 0.0, 10650, "mi", None, None),
        ("Street Triple", "2025-02-21", "New rear tyre", "Tyres",
         "Michelin Road 6, fitted and balanced.", "Two Wheel Tyres", 189.50, 12100, "mi",
         None, None),
        ("Street Triple", "2025-04-05", "Annual service", "Service",
         "Oil + filter, brake fluid flush.",
         "Triumph Leicester", 342.00, 12800, "mi", "2026-07-01", 18800),
        ("Daily", "2024-10-19", "Full service", "Service",
         "Oil, oil filter, air filter, pollen filter.", "Halfords Autocentre", 215.00,
         41200, "mi", "2025-10-19", 51200),
        ("Daily", "2025-03-08", "Front brake pads & discs", "Brakes",
         "Pagid discs and pads, copper grease on sliders.", "Me", 145.20, 43900, "mi",
         None, None),
        ("Weekend toy", "2024-06-15", "Oil change", "Oil change",
         "5W-30 + filter. Sump washer replaced.", "Me", 62.40, 88500, "km",
         "2025-06-15", 98500),
        ("Weekend toy", "2025-04-12", "New soft top", "Repair",
         "Replacement vinyl top with heated glass window.", "Soft Top Specialists",
         850.00, 91200, "km", None, None),
    ]

    # (vehicle_name, date, odometer, unit, note)
    ODOMETER = [
        ("Street Triple", "2025-05-01", 13150, "mi", "Post-trip reading"),
        ("Street Triple", "2025-06-01", 13420, "mi", None),
        ("Daily", "2025-06-07", 45310, "mi", None),
        ("Weekend toy", "2025-06-01", 91890, "km", "First show of the season"),
    ]

    with get_db() as db:
        garage_repo = GarageRepository(db)
        vehicle_repo = VehicleRepository(db)
        service_repo = ServiceLogRepository(db)
        odo_repo = OdometerLogRepository(db)
        ids: dict[str, int] = {}

        garage = garage_repo.get_by_name(GARAGE_NAME)
        if garage is None:
            garage = garage_repo.create(GARAGE_NAME)
            print(f"  garage {GARAGE_NAME}")
        else:
            print(f"  skip garage {GARAGE_NAME} (already exists)")

        existing = {
            v["name"]
            for v in vehicle_repo.list_for_garages([garage["id"]], include_archived=True)
        }
        for v in VEHICLES:
            specs = v.pop("specs")
            if v["name"] in existing:
                print(f"  skip vehicle {v['name']} (already exists)")
                continue
            created = vehicle_repo.create(garage["id"], v)
            ids[v["name"]] = created["id"]
            vehicle_repo.replace_specs(
                created["id"], [{"name": n, "value": val} for n, val in specs]
            )
            print(f"  vehicle {v['name']} — {v['make']} {v['model']}")

        for (vname, sdate, title, category, desc, by, cost,
             odo, unit, due_date, due_dist) in SERVICES:
            if vname not in ids:
                continue
            service_repo.create({
                "vehicle_id": ids[vname],
                "date": sdate,
                "title": title,
                "category": category,
                "description": desc,
                "performed_by": by,
                "cost": cost,
                "odometer_km": to_km(odo, unit),
                "odometer_unit": unit,
                "next_due_date": due_date,
                "next_due_km": to_km(due_dist, unit) if due_dist is not None else None,
            })
            print(f"  service {vname}: {title} ({sdate})")

        for (vname, odate, odo, unit, note) in ODOMETER:
            if vname not in ids:
                continue
            odo_repo.create(ids[vname], odate, to_km(odo, unit), unit, note=note)
            print(f"  odometer {vname}: {odo} {unit} ({odate})")

    print(f"\nDone. 1 garage, {len(VEHICLES)} vehicles, {len(SERVICES)} services, "
          f"{len(ODOMETER)} odometer logs.")
    print("Add members with: python manage.py add-member <garage> <username> <role>")


def cmd_create_garage(args: list[str]) -> None:
    if len(args) != 1:
        print("Usage: python manage.py create-garage <name>")
        sys.exit(1)
    from torqued.db import get_db, run_migrations
    from torqued.repositories.garage_repository import GarageRepository
    run_migrations()
    with get_db() as db:
        repo = GarageRepository(db)
        if repo.get_by_name(args[0]):
            print(f"Error: garage '{args[0]}' already exists")
            sys.exit(1)
        garage = repo.create(args[0])
    print(f"Garage '{garage['name']}' created (id {garage['id']}).")


def cmd_add_member(args: list[str]) -> None:
    if len(args) not in (2, 3):
        print("Usage: python manage.py add-member <garage-name> <username> [owner|member|readonly]")
        sys.exit(1)
    garage_name, username = args[0], args[1]
    role = args[2] if len(args) == 3 else "member"
    from torqued.db import get_db
    from torqued.repositories.garage_repository import ROLES, GarageRepository
    from torqued.repositories.user_repository import UserRepository
    if role not in ROLES:
        print(f"Error: role must be one of {', '.join(ROLES)}")
        sys.exit(1)
    with get_db() as db:
        garage = GarageRepository(db).get_by_name(garage_name)
        if not garage:
            print(f"Error: garage '{garage_name}' not found")
            sys.exit(1)
        user = UserRepository(db).get_by_username(username)
        if not user:
            print(f"Error: user '{username}' not found")
            sys.exit(1)
        existing_role = GarageRepository(db).member_role(garage["id"], user["id"])
        if existing_role:
            GarageRepository(db).set_member_role(garage["id"], user["id"], role)
            print(f"'{username}' role in '{garage_name}' changed to {role}.")
        else:
            GarageRepository(db).add_member(garage["id"], user["id"], role)
            print(f"'{username}' added to '{garage_name}' as {role}.")


def cmd_rename_user(args: list[str]) -> None:
    if len(args) != 2:
        print("Usage: python manage.py rename-user <username> <new-username>")
        sys.exit(1)
    username, new_username = args
    from torqued.db import get_db
    from torqued.repositories.user_repository import UserRepository
    with get_db() as db:
        repo = UserRepository(db)
        user = repo.get_by_username(username)
        if not user:
            print(f"Error: user '{username}' not found")
            sys.exit(1)
        if repo.get_by_username(new_username):
            print(f"Error: user '{new_username}' already exists")
            sys.exit(1)
        repo.rename(user["id"], new_username)
    print(f"User '{username}' renamed to '{new_username}'.")


def cmd_delete_user(args: list[str]) -> None:
    if len(args) != 1:
        print("Usage: python manage.py delete-user <username>")
        sys.exit(1)
    username = args[0]
    from torqued.db import get_db
    from torqued.repositories.user_repository import UserRepository
    with get_db() as db:
        repo = UserRepository(db)
        if not repo.get_by_username(username):
            print(f"Error: user '{username}' not found")
            sys.exit(1)
    confirm = input(f"Delete user '{username}'? Type YES to confirm: ")
    if confirm.strip() != "YES":
        print("Aborted.")
        sys.exit(0)
    with get_db() as db:
        repo = UserRepository(db)
        user = repo.get_by_username(username)
        repo.delete(user["id"])
    print(f"User '{username}' deleted.")


def _active_url() -> Any:
    """Return the active database URL (SQLAlchemy URL object)."""
    from sqlalchemy.engine import make_url
    from torqued.db import database_url

    return make_url(database_url())


def _backup_dir(url: Any) -> Path:
    """Where backups live: next to the SQLite file, or data/ for everything else."""
    if url.get_backend_name() == "sqlite":
        return Path(url.database).parent
    return Path("data")


def _confirm_destructive(url: Any, action: str) -> None:
    """Abort unless the operator retypes the exact target the action will hit.

    A constant "YES" can't tell the local container apart from production; naming the
    target host and requiring it back forces a deliberate acknowledgement of *which*
    database is about to be destroyed — whether ``--prod`` repointed us at
    PROD_DATABASE_URL or DATABASE_URL already is production (PythonAnywhere).
    """
    target = url.host or url.database or "the configured database"
    print(f"⚠  {action}")
    print(f"⚠  Target database: {target}")
    try:
        confirm = input(f"Type the target '{target}' to confirm (anything else aborts): ")
    except EOFError:
        # Non-interactive invocation (no TTY): abort cleanly rather than throwing.
        confirm = ""
    if confirm.strip() != target:
        print("Aborted.")
        sys.exit(0)


def cmd_db_restore(args: list[str]) -> None:
    import subprocess

    if len(args) != 1:
        print("Usage: python manage.py db-restore <backup-file>")
        sys.exit(1)

    url = _active_url()
    backup_path = Path(args[0])
    if not backup_path.is_absolute():
        backup_path = _backup_dir(url) / args[0]

    if not backup_path.exists():
        print(f"Error: backup file not found: {backup_path}")
        sys.exit(1)

    _confirm_destructive(url, f"Restore from '{backup_path}' overwrites the current database")

    if url.get_backend_name() == "sqlite":
        import sqlite3 as _sqlite3

        Path(url.database).unlink(missing_ok=True)
        con = _sqlite3.connect(url.database)
        con.executescript(backup_path.read_text())
        con.close()
    else:
        dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
        subprocess.run(
            ["psql", dsn, "-v", "ON_ERROR_STOP=1",
             "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"],
            check=True,
        )
        subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-f", str(backup_path)], check=True)
    print(f"Database restored from {backup_path}")


def cmd_db_backup(_: list[str]) -> None:
    import datetime
    import subprocess

    url = _active_url()
    backup_dir = _backup_dir(url)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"db-backup-{ts}.sql"

    if url.get_backend_name() == "sqlite":
        import sqlite3 as _sqlite3

        con = _sqlite3.connect(url.database)
        with open(backup_path, "w") as f:
            for line in con.iterdump():
                f.write(line + "\n")
        con.close()
    else:
        dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
        with open(backup_path, "w") as f:
            subprocess.run(["pg_dump", dsn], check=True, stdout=f)
    print(f"Backup written to {backup_path}")


def cmd_migrate(_: list[str]) -> None:
    from torqued.db import run_migrations

    run_migrations()
    print("Migrations complete.")


def cmd_reset_db(args: list[str]) -> None:
    from torqued.db import get_db, run_migrations

    url = _active_url()
    _confirm_destructive(url, "Reset drops ALL tables, including users")

    if url.get_backend_name() == "sqlite":
        # Delete the database file outright rather than dropping tables one by one:
        # a malformed image can't be read, and this also can't miss any tables.
        for suffix in ("", "-wal", "-shm"):
            Path(url.database + suffix).unlink(missing_ok=True)
    else:
        with get_db() as db:
            db.execute("DROP SCHEMA public CASCADE")
            db.execute("CREATE SCHEMA public")

    run_migrations()
    print("Database reset. Run seed to repopulate.")


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "create-user": cmd_create_user,
    "create-garage": cmd_create_garage,
    "add-member": cmd_add_member,
    "list-users":  cmd_list_users,
    "rename-user": cmd_rename_user,
    "delete-user": cmd_delete_user,
    "migrate":     cmd_migrate,
    "seed":        cmd_seed,
    "reset-db":    cmd_reset_db,
    "db-backup":   cmd_db_backup,
    "db-restore":  cmd_db_restore,
}

def _target_production() -> None:
    """Point every following DB operation at PROD_DATABASE_URL (the `--prod` flag).

    On PythonAnywhere there is no separate PROD_DATABASE_URL — DATABASE_URL already is
    production — so `--prod` is a local convenience and errors if it is unset.
    """
    import os

    from sqlalchemy.engine import make_url

    prod = os.environ.get("PROD_DATABASE_URL")
    if not prod:
        print("Error: PROD_DATABASE_URL is not set (it points at the production database).")
        sys.exit(1)
    os.environ["DATABASE_URL"] = prod
    print(f"⚠  Targeting the PRODUCTION database at {make_url(prod).host or '?'} (PROD_DATABASE_URL).")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)
    cmd_args = sys.argv[2:]
    # `--prod` works for any command — strip it here and repoint the DB once.
    if "--prod" in cmd_args:
        cmd_args = [a for a in cmd_args if a != "--prod"]
        _target_production()
    COMMANDS[sys.argv[1]](cmd_args)
