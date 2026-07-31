from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from torqued import mot, ves
from torqued.access import admin_required
from torqued.db import get_db
from torqued.repositories.mot_repository import MotRepository
from torqued.repositories.records_repository import SOURCES, RecordsRepository
from torqued.repositories.ves_repository import VesRepository

bp = Blueprint("records", __name__)


@bp.get("/api/vehicle-records")
@admin_required
def vehicle_records() -> ResponseReturnValue:
    """List stored DVLA/DVSA records grouped by vehicle (site-admin), newest first."""
    page = max(1, request.args.get("page", 1, type=int))
    with get_db() as db:
        return jsonify(RecordsRepository(db).list_all(page)), 200


@bp.get("/api/vehicle-records/<source>/<int:row_id>/records")
@admin_required
def records_for(source: str, row_id: int) -> ResponseReturnValue:
    """Return every DVSA + tax record for the plate the given row belongs to (site-admin)."""
    if source not in SOURCES:
        return jsonify(error="Not found"), 404
    with get_db() as db:
        records = RecordsRepository(db).get_records(source, row_id)
    if records is None:
        return jsonify(error="Not found"), 404
    return jsonify(records), 200


@bp.post("/api/vehicle-records")
@admin_required
def create_lookup() -> ResponseReturnValue:
    """Look up any registration at the DVSA and DVLA and persist both, unassigned.

    Each source is fetched independently so one failing (e.g. an unknown plate at one
    service) doesn't block the other; the record is stored detached and relinks to a
    vehicle added on this plate later. DVSA is fetched only when its API credentials are
    configured; DVLA VES is a credential-less scrape and is always attempted. A per-source
    failure is reported without discarding the source that succeeded.
    """
    registration = ((request.json or {}).get("registration") or "").strip()
    if not registration:
        return jsonify(error="registration is required"), 400

    saved: dict[str, dict[str, object] | None] = {"dvsa": None, "ves": None}
    errors: list[str] = []
    dvsa_payload = None
    if mot.is_configured():
        try:
            dvsa_payload = mot.fetch_vehicle(registration)
        except mot.MotError as e:
            errors.append(f"DVSA: {e}")
    ves_payload = None
    try:
        ves_payload = ves.fetch_ves(registration)
    except ves.VesError as e:
        errors.append(f"DVLA: {e}")

    if dvsa_payload is None and ves_payload is None:
        # Both configured sources failed (e.g. unknown plate) — relay the errors.
        return jsonify(error="; ".join(errors) or "Lookup failed"), 404

    with get_db() as db:
        if dvsa_payload is not None:
            MotRepository(db).store_detached_lookup(dvsa_payload)
            saved["dvsa"] = {
                "make": dvsa_payload.get("make"),
                "model": dvsa_payload.get("model"),
            }
        if ves_payload is not None:
            VesRepository(db).store_detached_lookup(ves_payload)
            saved["ves"] = {
                "tax_status": ves_payload.get("tax_status"),
                "mot_status": ves_payload.get("mot_status"),
            }

    payload = dvsa_payload or ves_payload or {}
    return jsonify(
        registration=payload.get("registration") or registration,
        make=(dvsa_payload or {}).get("make"),
        model=(dvsa_payload or {}).get("model"),
        saved=saved,
        errors=errors,
    ), 201
