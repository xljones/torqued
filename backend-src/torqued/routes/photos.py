import os
import uuid
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.access import can_write, vehicle_role
from torqued.db import get_db
from torqued.repositories.photo_repository import PhotoRepository
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.vehicle_repository import VehicleRepository

bp = Blueprint("photos", __name__)

_DEFAULT_UPLOAD_DIR = str(Path(__file__).parent.parent.parent.parent / "data" / "uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def upload_dir() -> str:
    d = os.environ.get("UPLOAD_DIR", _DEFAULT_UPLOAD_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _check_photo(
    db: Any, photo: dict[str, Any] | None, write: bool = False
) -> tuple[Response, int] | None:
    """Return an error response if the photo is missing/out of scope/read-only, else None."""
    role = vehicle_role(db, current_user, photo["vehicle_id"]) if photo else None
    if photo is None or role is None:
        return jsonify(error="Not found"), 404
    if write and not can_write(role):
        return jsonify(error="Read-only access to this garage"), 403
    return None


@bp.post("/api/vehicles/<int:vehicle_id>/photos")
@login_required
def upload_photo(vehicle_id: int) -> ResponseReturnValue:
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="file is required"), 400
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify(error=f"file type {ext or '(none)'} not allowed"), 400

    caption = request.form.get("caption") or None
    service_log_id_raw = request.form.get("service_log_id") or None
    service_log_id = None

    with get_db() as db:
        role = vehicle_role(db, current_user, vehicle_id)
        if role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        if service_log_id_raw:
            try:
                service_log_id = int(service_log_id_raw)
            except ValueError:
                return jsonify(error="service_log_id must be an integer"), 400
            log = ServiceLogRepository(db).get_by_id(service_log_id)
            if not log or log["vehicle_id"] != vehicle_id:
                return jsonify(error="service log not found for this vehicle"), 400

        filename = f"{uuid.uuid4().hex}{ext}"
        file.save(os.path.join(upload_dir(), filename))
        photo = PhotoRepository(db).create(
            vehicle_id,
            filename,
            original_name=file.filename,
            caption=caption,
            service_log_id=service_log_id,
            uploaded_by=current_user.id,
        )
    return jsonify(photo), 201


@bp.get("/api/photos/<int:photo_id>/file")
@login_required
def photo_file(photo_id: int) -> ResponseReturnValue:
    with get_db() as db:
        photo = PhotoRepository(db).get_by_id(photo_id)
        err = _check_photo(db, photo)
        if err:
            return err
        assert photo is not None
    return send_from_directory(upload_dir(), photo["filename"], max_age=86400)


@bp.put("/api/photos/<int:photo_id>")
@login_required
def update_photo(photo_id: int) -> ResponseReturnValue:
    d = request.json or {}
    with get_db() as db:
        repo = PhotoRepository(db)
        err = _check_photo(db, repo.get_by_id(photo_id), write=True)
        if err:
            return err
        return jsonify(repo.update_caption(photo_id, d.get("caption") or None))


@bp.put("/api/photos/<int:photo_id>/cover")
@login_required
def set_cover(photo_id: int) -> ResponseReturnValue:
    with get_db() as db:
        photo = PhotoRepository(db).get_by_id(photo_id)
        err = _check_photo(db, photo, write=True)
        if err:
            return err
        assert photo is not None
        VehicleRepository(db).set_cover_photo(photo["vehicle_id"], photo_id)
    return "", 204


@bp.put("/api/photos/<int:photo_id>/cover-frame")
@login_required
def update_cover_frame(photo_id: int) -> ResponseReturnValue:
    d = request.json or {}
    focal_x_raw, focal_y_raw, zoom_raw = d.get("focal_x"), d.get("focal_y"), d.get("zoom")
    if focal_x_raw is None or focal_y_raw is None or zoom_raw is None:
        return jsonify(error="focal_x, focal_y, and zoom are required"), 400
    try:
        focal_x = float(focal_x_raw)
        focal_y = float(focal_y_raw)
        zoom = float(zoom_raw)
    except (TypeError, ValueError):
        return jsonify(error="focal_x, focal_y, and zoom must be numbers"), 400
    if not (0 <= focal_x <= 1) or not (0 <= focal_y <= 1):
        return jsonify(error="focal_x and focal_y must be between 0 and 1"), 400
    if not (1 <= zoom <= 4):
        return jsonify(error="zoom must be between 1 and 4"), 400
    with get_db() as db:
        repo = PhotoRepository(db)
        err = _check_photo(db, repo.get_by_id(photo_id), write=True)
        if err:
            return err
        return jsonify(repo.update_cover_frame(photo_id, focal_x, focal_y, zoom))


@bp.delete("/api/photos/<int:photo_id>")
@login_required
def delete_photo(photo_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = PhotoRepository(db)
        photo = repo.get_by_id(photo_id)
        err = _check_photo(db, photo, write=True)
        if err:
            return err
        assert photo is not None
        repo.delete(photo_id)
    try:
        os.unlink(os.path.join(upload_dir(), photo["filename"]))
    except FileNotFoundError:
        pass
    return "", 204
