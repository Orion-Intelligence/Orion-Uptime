from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileResponse
from routes import orion_login_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _profile(profile_id="profile-1"):
    return AuthProfileResponse(id=profile_id, name="Portal", login_url="https://example.com/login", method="POST", credential_fields=["username", "password"], created_at=NOW, updated_at=NOW, login_status_code=200)


def _use(override, **returns):
    override(orion_login_routes.get_auth_profile_service, lambda: FakeService(**returns))


def test_create_profile(client, override, as_admin):
    _use(override, create_profile=_profile())
    response = client.post("/api/auth-profiles/create", json={"name": "Portal", "login_url": "https://example.com/login", "credentials": {"username": "a", "password": "b"}})
    assert response.status_code == 201
    assert response.json()["data"]["id"] == "profile-1"


def test_list_profiles(client, override, as_admin):
    _use(override, list_profiles=[])
    response = client.get("/api/auth-profiles/list_all")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_profile(client, override, as_admin):
    _use(override, get_profile=_profile())
    response = client.get("/api/auth-profiles/profile-1")
    assert response.status_code == 200


def test_update_profile(client, override, as_admin):
    _use(override, update_profile=_profile())
    response = client.put("/api/auth-profiles/profile-1", json={"name": "renamed"})
    assert response.status_code == 200


def test_select_log_source(client, override, as_admin):
    _use(override, select_log_source=_profile())
    response = client.post("/api/auth-profiles/profile-1/select-log-source")
    assert response.status_code == 200


def test_clear_log_source(client, override, as_admin):
    _use(override, clear_log_source=None)
    response = client.post("/api/auth-profiles/clear-log-source")
    assert response.status_code == 200


def test_delete_profile(client, override, as_admin):
    _use(override, delete_profile=None)
    response = client.delete("/api/auth-profiles/profile-1")
    assert response.status_code == 200
