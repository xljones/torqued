"""Tests for /api/vehicles/<id>/photos and /api/photos: upload, serve, caption, delete."""
import io
import os

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
        assert repo.delete(999) is False


def test_photos_deleted_with_vehicle_cascade(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    photo = upload(auth_client, v["id"]).json
    auth_client.delete(f"/api/vehicles/{v['id']}")
    assert auth_client.get(f"/api/photos/{photo['id']}/file").status_code == 404
