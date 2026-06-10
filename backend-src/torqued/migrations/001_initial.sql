CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    is_readonly   INTEGER NOT NULL DEFAULT 0,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    expires_at    TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicles (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT    NOT NULL,
    kind                    TEXT    NOT NULL DEFAULT 'car',
    make                    TEXT,
    model                   TEXT,
    year                    INTEGER,
    registration            TEXT,
    vin                     TEXT,
    colour                  TEXT,
    fuel_type               TEXT,
    odometer_unit           TEXT    NOT NULL DEFAULT 'mi',
    purchase_date           DATE,
    tyre_size_front         TEXT,
    tyre_size_rear          TEXT,
    tyre_pressure_front_psi REAL,
    tyre_pressure_rear_psi  REAL,
    notes                   TEXT,
    archived                INTEGER NOT NULL DEFAULT 0,
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Free-form per-vehicle reference specs (oil grade, chain slack, torque values, …)
CREATE TABLE vehicle_specs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    value      TEXT    NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE service_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id    INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date          DATE    NOT NULL,
    title         TEXT    NOT NULL,
    category      TEXT,
    description   TEXT,
    performed_by  TEXT,
    cost          REAL,
    odometer_km   REAL,
    odometer_unit TEXT,
    next_due_date DATE,
    next_due_km   REAL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE odometer_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    date        DATE    NOT NULL,
    odometer_km REAL    NOT NULL,
    unit        TEXT    NOT NULL DEFAULT 'mi',
    note        TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE photos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id     INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    service_log_id INTEGER REFERENCES service_logs(id) ON DELETE CASCADE,
    filename       TEXT    NOT NULL,
    original_name  TEXT,
    caption        TEXT,
    uploaded_by    INTEGER REFERENCES users(id),
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicle_history (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id              INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    changed_at              DATETIME DEFAULT CURRENT_TIMESTAMP,
    changed_by              INTEGER,
    name                    TEXT,
    kind                    TEXT,
    make                    TEXT,
    model                   TEXT,
    year                    INTEGER,
    registration            TEXT,
    vin                     TEXT,
    colour                  TEXT,
    fuel_type               TEXT,
    odometer_unit           TEXT,
    purchase_date           TEXT,
    tyre_size_front         TEXT,
    tyre_size_rear          TEXT,
    tyre_pressure_front_psi REAL,
    tyre_pressure_rear_psi  REAL,
    notes                   TEXT,
    archived                INTEGER
);

CREATE TABLE service_log_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    service_log_id INTEGER NOT NULL REFERENCES service_logs(id) ON DELETE CASCADE,
    changed_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    changed_by     INTEGER,
    vehicle_id     INTEGER,
    date           TEXT,
    title          TEXT,
    category       TEXT,
    description    TEXT,
    performed_by   TEXT,
    cost           REAL,
    odometer_km    REAL,
    odometer_unit  TEXT,
    next_due_date  TEXT,
    next_due_km    REAL
);

CREATE INDEX idx_service_logs_vehicle ON service_logs(vehicle_id, date DESC);
CREATE INDEX idx_odometer_logs_vehicle ON odometer_logs(vehicle_id, date DESC);
CREATE INDEX idx_photos_vehicle ON photos(vehicle_id);
CREATE INDEX idx_photos_service_log ON photos(service_log_id);
