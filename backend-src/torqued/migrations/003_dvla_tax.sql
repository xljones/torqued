-- DVLA Vehicle Enquiry Service (VES) snapshot: road-tax status and due date per
-- vehicle (DVLA also reports MOT status/expiry). One row per vehicle, replaced on
-- each refresh. Mirrors dvsa_vehicles; the verbatim API payload lives in raw_json.
CREATE TABLE dvla_vehicles (
    vehicle_id      INTEGER PRIMARY KEY REFERENCES vehicles(id) ON DELETE CASCADE,
    registration    TEXT,
    tax_status      TEXT,
    tax_due_date    TEXT,
    mot_status      TEXT,
    mot_expiry_date TEXT,
    raw_json        TEXT     NOT NULL,
    fetched_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
