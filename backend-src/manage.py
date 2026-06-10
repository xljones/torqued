#!/usr/bin/env python3
"""Management CLI. Usage: python manage.py <command> [args]"""
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


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
    with get_db() as db:
        users = db.execute(
            "SELECT id, username, is_readonly, is_admin, expires_at, created_at FROM users ORDER BY id"
        ).fetchall()
    if not users:
        print("No users.")
    for u in users:
        kind = "admin" if u[3] else ("read-only" if u[2] else "normal")
        expiry = f"  expires {u[4]}" if u[4] else ""
        print(f"  [{u[0]}] {u[1]}  ({kind}{expiry})  created {u[5]}")


def cmd_seed(_: list[str]) -> None:
    from torqued.db import get_db, run_migrations
    from torqued.repositories.odometer_log_repository import OdometerLogRepository
    from torqued.repositories.service_log_repository import ServiceLogRepository
    from torqued.repositories.vehicle_repository import VehicleRepository
    from torqued.units import to_km

    run_migrations()

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
        ("Street Triple", "2025-04-05", "Annual service + MOT", "Service",
         "Oil + filter, brake fluid flush. MOT pass, no advisories.",
         "Triumph Leicester", 342.00, 12800, "mi", "2026-07-01", 18800),
        ("Daily", "2024-10-19", "Full service", "Service",
         "Oil, oil filter, air filter, pollen filter.", "Halfords Autocentre", 215.00,
         41200, "mi", "2025-10-19", 51200),
        ("Daily", "2025-03-08", "Front brake pads & discs", "Brakes",
         "Pagid discs and pads, copper grease on sliders.", "Me", 145.20, 43900, "mi",
         None, None),
        ("Daily", "2026-05-30", "MOT", "Inspection",
         "Pass. Advisory: rear tyres close to legal limit.", "Halfords Autocentre", 39.99,
         45050, "mi", "2027-05-30", None),
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
        vehicle_repo = VehicleRepository(db)
        service_repo = ServiceLogRepository(db)
        odo_repo = OdometerLogRepository(db)
        ids: dict[str, int] = {}

        existing = {v["name"] for v in vehicle_repo.list_all(include_archived=True)}
        for v in VEHICLES:
            specs = v.pop("specs")
            if v["name"] in existing:
                print(f"  skip vehicle {v['name']} (already exists)")
                continue
            created = vehicle_repo.create(v)
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

    print(f"\nDone. {len(VEHICLES)} vehicles, {len(SERVICES)} services, "
          f"{len(ODOMETER)} odometer logs.")


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


def cmd_db_restore(args: list[str]) -> None:
    import os
    import sqlite3 as _sqlite3

    if len(args) != 1:
        print("Usage: python manage.py db-restore <backup-file>")
        sys.exit(1)

    db_path = os.environ.get("DB_PATH", "data/garage.db")
    backup_path = Path(args[0])
    if not backup_path.is_absolute():
        backup_path = Path(db_path).parent / args[0]

    if not backup_path.exists():
        print(f"Error: backup file not found: {backup_path}")
        sys.exit(1)

    confirm = input(f"Restore from '{backup_path}'? This will overwrite the current database. Type YES to confirm: ")
    if confirm.strip() != "YES":
        print("Aborted.")
        sys.exit(0)

    sql = backup_path.read_text()
    Path(db_path).unlink(missing_ok=True)
    con = _sqlite3.connect(db_path)
    con.executescript(sql)
    con.close()
    print(f"Database restored from {backup_path}")


def cmd_db_backup(_: list[str]) -> None:
    import datetime
    import os
    import sqlite3 as _sqlite3

    db_path = os.environ.get("DB_PATH", "data/garage.db")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = str(Path(db_path).parent / f"db-backup-{ts}.sql")

    con = _sqlite3.connect(db_path)
    with open(backup_path, "w") as f:
        for line in con.iterdump():
            f.write(line + "\n")
    con.close()
    print(f"Backup written to {backup_path}")


def cmd_migrate(_: list[str]) -> None:
    from torqued.db import run_migrations
    run_migrations()
    print("Migrations complete.")


def cmd_reset_db(args: list[str]) -> None:
    msg = "This will drop ALL tables including users. Type YES to confirm: "
    confirm = input(msg)
    if confirm.strip() != "YES":
        print("Aborted.")
        sys.exit(0)
    from torqued.db import get_db
    with get_db() as db:
        tables = [
            "photos", "service_log_history", "vehicle_history",
            "odometer_logs", "service_logs", "vehicle_specs", "vehicles",
            "schema_migrations", "users",
        ]
        for table in tables:
            db.execute(f"DROP TABLE IF EXISTS {table}")
    print("All tables dropped. Run seed to repopulate.")


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "create-user": cmd_create_user,
    "list-users":  cmd_list_users,
    "rename-user": cmd_rename_user,
    "delete-user": cmd_delete_user,
    "migrate":     cmd_migrate,
    "seed":        cmd_seed,
    "reset-db":    cmd_reset_db,
    "db-backup":   cmd_db_backup,
    "db-restore":  cmd_db_restore,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
