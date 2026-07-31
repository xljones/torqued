"""Tests for /api/vehicles/<id>/photos and /api/photos: upload, serve, caption, delete."""
import io
import os
from typing import Any

from flask import Flask
from flask.testing import FlaskClient

from tests.test_services import mk_service
from tests.test_vehicles import mk_vehicle

PNG_BYTES = b"\x89PNG\r\n\x1a\n fake image data"


def upload(client: FlaskClient, vehicle_id: int, filename: str = "bike.png", **form) -> object:
    return client.post(
        f"/api/vehicles/{vehicle_id}/photos",
        data={"file": (io.BytesIO(PNG_BYTES), filename), **form},
        content_type="multipart/form-data",
    )


def test_upload_and_serve(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = upload(auth_client, v["id"], caption="After the wash")
    assert r.status_code == 201
    photo = r.json
    assert photo["original_name"] == "bike.png"
    assert photo["caption"] == "After the wash"
    assert photo["filename"].endswith(".png")
    assert os.path.exists(os.path.join(os.environ["UPLOAD_DIR"], photo["filename"]))

    served = auth_client.get(f"/api/photos/{photo['id']}/file")
    assert served.status_code == 200
    assert served.data == PNG_BYTES
    served.close()


def test_upload_appears_on_vehicle_detail(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    upload(auth_client, v["id"])
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    assert len(detail["photos"]) == 1
    assert detail["photos"][0]["uploaded_by_username"] == "testuser"


def test_upload_scoped_to_service_log(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    r = upload(auth_client, v["id"], service_log_id=str(s["id"]))
    assert r.status_code == 201
    log = auth_client.get(f"/api/services/{s['id']}").json
    assert len(log["photos"]) == 1


def test_upload_requires_file(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/photos", data={},
                         content_type="multipart/form-data")
    assert r.status_code == 400


def test_upload_rejects_bad_extension(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert upload(auth_client, v["id"], filename="malware.exe").status_code == 400
    assert upload(auth_client, v["id"], filename="noext").status_code == 400


def test_upload_vehicle_404(auth_client: FlaskClient) -> None:
    assert upload(auth_client, 999).status_code == 404


def test_upload_bad_service_log(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert upload(auth_client, v["id"], service_log_id="abc").status_code == 400
    assert upload(auth_client, v["id"], service_log_id="999").status_code == 400
    # Service log on a different vehicle is rejected too
    other = mk_vehicle(auth_client, name="Other")
    s = mk_service(auth_client, other["id"])
    assert upload(auth_client, v["id"], service_log_id=str(s["id"])).status_code == 400


def test_serve_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/photos/999/file").status_code == 404


def test_update_caption(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    r = auth_client.put(f"/api/photos/{photo['id']}", json={"caption": "New caption"})
    assert r.status_code == 200
    assert r.json["caption"] == "New caption"
    # Clearing the caption stores NULL
    r = auth_client.put(f"/api/photos/{photo['id']}", json={"caption": ""})
    assert r.json["caption"] is None


def test_update_caption_404(auth_client: FlaskClient) -> None:
    assert auth_client.put("/api/photos/999", json={"caption": "x"}).status_code == 404


def test_delete_removes_file(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    path = os.path.join(os.environ["UPLOAD_DIR"], photo["filename"])
    assert os.path.exists(path)
    assert auth_client.delete(f"/api/photos/{photo['id']}").status_code == 204
    assert not os.path.exists(path)


def test_delete_tolerates_missing_file(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    os.unlink(os.path.join(os.environ["UPLOAD_DIR"], photo["filename"]))
    assert auth_client.delete(f"/api/photos/{photo['id']}").status_code == 204


def test_delete_404(auth_client: FlaskClient) -> None:
    assert auth_client.delete("/api/photos/999").status_code == 404


def test_repo_no_op_paths_on_missing_photo(app: Flask) -> None:
    # The HTTP routes 404 before reaching these repository methods, so cover their
    # "row not found" paths directly.
    from torqued.db import get_db
    from torqued.repositories.photo_repository import PhotoRepository

    with get_db() as db:
        repo = PhotoRepository(db)
        assert repo.update_caption(999, "x") is None
        assert repo.update_cover_frame(999, 0.5, 0.5, 1.0) is None
        assert repo.delete(999) is False


def test_photos_deleted_with_vehicle_cascade(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    auth_client.delete(f"/api/vehicles/{v['id']}")
    assert auth_client.get(f"/api/photos/{photo['id']}/file").status_code == 404


# ── cover photo ─────────────────────────────────────────────────────────────────

def _cover_id(client: FlaskClient, vehicle_id: int) -> Any:
    """The vehicle's effective cover photo id as reported by the list endpoint."""
    listed = next(v for v in client.get("/api/vehicles").json if v["id"] == vehicle_id)
    return listed["cover_photo_id"]


def test_cover_defaults_to_latest_upload(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    upload(auth_client, v["id"])
    p2 = upload(auth_client, v["id"]).json
    # With no explicit pick the cover is the most recently uploaded photo, on both
    # the detail endpoint and the list card.
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["cover_photo_id"] == p2["id"]
    assert _cover_id(auth_client, v["id"]) == p2["id"]


def test_set_cover_photo_overrides_default(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    p1 = upload(auth_client, v["id"]).json
    p2 = upload(auth_client, v["id"]).json
    # Pin the older photo; it beats the latest-upload default everywhere.
    assert auth_client.put(f"/api/photos/{p1['id']}/cover").status_code == 204
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["cover_photo_id"] == p1["id"]
    assert _cover_id(auth_client, v["id"]) == p1["id"]
    # Selecting another photo moves the cover.
    assert auth_client.put(f"/api/photos/{p2['id']}/cover").status_code == 204
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["cover_photo_id"] == p2["id"]


def test_cover_reverts_to_latest_when_pinned_photo_deleted(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    p1 = upload(auth_client, v["id"]).json
    p2 = upload(auth_client, v["id"]).json
    assert auth_client.put(f"/api/photos/{p1['id']}/cover").status_code == 204
    assert auth_client.delete(f"/api/photos/{p1['id']}").status_code == 204
    # The pinned photo is gone → falls back to the latest remaining upload.
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["cover_photo_id"] == p2["id"]
    assert _cover_id(auth_client, v["id"]) == p2["id"]


def test_cover_none_without_photos(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["cover_photo_id"] is None
    assert _cover_id(auth_client, v["id"]) is None


def test_set_cover_404(auth_client: FlaskClient) -> None:
    assert auth_client.put("/api/photos/999/cover").status_code == 404


def test_set_cover_cross_garage_404(client: FlaskClient, garage: dict[str, Any]) -> None:
    from tests.conftest import login, make_member
    from tests.test_garages import mk_garage

    other = mk_garage()
    make_member("alice", "testpass", "member", garage)
    make_member("bob", "testpass", "member", other)

    login(client, "bob")
    foreign = mk_vehicle(client, garage_id=other["id"])
    photo = upload(client, foreign["id"]).json

    login(client, "alice")
    assert client.put(f"/api/photos/{photo['id']}/cover").status_code == 404


# ── cover-crop framing ────────────────────────────────────────────────────────────

def _cover_frame(client: FlaskClient, vehicle_id: int) -> dict[str, Any]:
    """The vehicle's cover-crop framing fields as reported by the list endpoint."""
    listed = next(v for v in client.get("/api/vehicles").json if v["id"] == vehicle_id)
    return {k: listed[k] for k in ("cover_focal_x", "cover_focal_y", "cover_zoom")}


def test_update_cover_frame(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    r = auth_client.put(
        f"/api/photos/{photo['id']}/cover-frame",
        json={"focal_x": 0.25, "focal_y": 0.75, "zoom": 2.5},
    )
    assert r.status_code == 200
    assert r.json["cover_focal_x"] == 0.25
    assert r.json["cover_focal_y"] == 0.75
    assert r.json["cover_zoom"] == 2.5
    # This photo is the (only, latest-upload) cover, so the framing surfaces on the list too.
    assert _cover_frame(auth_client, v["id"]) == {
        "cover_focal_x": 0.25, "cover_focal_y": 0.75, "cover_zoom": 2.5,
    }


def test_cover_frame_null_before_set(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    upload(auth_client, v["id"])
    assert _cover_frame(auth_client, v["id"]) == {
        "cover_focal_x": None, "cover_focal_y": None, "cover_zoom": None,
    }


def test_cover_frame_null_without_photos(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert _cover_frame(auth_client, v["id"]) == {
        "cover_focal_x": None, "cover_focal_y": None, "cover_zoom": None,
    }


def test_cover_frame_follows_pinned_cover_not_fallback(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    p1 = upload(auth_client, v["id"]).json
    p2 = upload(auth_client, v["id"]).json
    auth_client.put(f"/api/photos/{p1['id']}/cover-frame", json={"focal_x": 0.1, "focal_y": 0.2, "zoom": 1.5})
    # p2 is the latest-upload fallback cover, but has no framing of its own.
    assert _cover_frame(auth_client, v["id"]) == {
        "cover_focal_x": None, "cover_focal_y": None, "cover_zoom": None,
    }
    # Pinning p1 as the actual cover surfaces its previously-saved framing.
    auth_client.put(f"/api/photos/{p1['id']}/cover")
    assert _cover_frame(auth_client, v["id"]) == {
        "cover_focal_x": 0.1, "cover_focal_y": 0.2, "cover_zoom": 1.5,
    }


def test_update_cover_frame_missing_fields(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    r = auth_client.put(f"/api/photos/{photo['id']}/cover-frame", json={"focal_x": 0.5, "focal_y": 0.5})
    assert r.status_code == 400


def test_update_cover_frame_non_numeric(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    r = auth_client.put(
        f"/api/photos/{photo['id']}/cover-frame",
        json={"focal_x": "nope", "focal_y": 0.5, "zoom": 1},
    )
    assert r.status_code == 400


def test_update_cover_frame_focal_out_of_range(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    assert auth_client.put(
        f"/api/photos/{photo['id']}/cover-frame", json={"focal_x": -0.1, "focal_y": 0.5, "zoom": 1}
    ).status_code == 400
    assert auth_client.put(
        f"/api/photos/{photo['id']}/cover-frame", json={"focal_x": 0.5, "focal_y": 1.1, "zoom": 1}
    ).status_code == 400


def test_update_cover_frame_zoom_out_of_range(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    assert auth_client.put(
        f"/api/photos/{photo['id']}/cover-frame", json={"focal_x": 0.5, "focal_y": 0.5, "zoom": 0.9}
    ).status_code == 400
    assert auth_client.put(
        f"/api/photos/{photo['id']}/cover-frame", json={"focal_x": 0.5, "focal_y": 0.5, "zoom": 4.1}
    ).status_code == 400


def test_update_cover_frame_404(auth_client: FlaskClient) -> None:
    r = auth_client.put(
        "/api/photos/999/cover-frame", json={"focal_x": 0.5, "focal_y": 0.5, "zoom": 1}
    )
    assert r.status_code == 404


def test_update_cover_frame_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    from torqued.db import get_db
    from torqued.repositories.photo_repository import PhotoRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        vehicle = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
        photo = PhotoRepository(db).create(vehicle["id"], "shared.png")

    r = readonly_client.put(
        f"/api/photos/{photo['id']}/cover-frame", json={"focal_x": 0.5, "focal_y": 0.5, "zoom": 1}
    )
    assert r.status_code == 403
