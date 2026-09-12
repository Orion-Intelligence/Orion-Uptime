from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_user_account_model import UserResponse, UserRole
from orion.shared_models.exceptions import NotFoundError
from routes import user_account_routes
from tests.model.fakes import FakeService

NOW = datetime.now(UTC)


def _user(user_id="user-1"):
    return UserResponse(id=user_id, username="tester", role=UserRole.VIEWER, is_active=True, created_at=NOW, updated_at=NOW, last_login=None)


def _use(override, **returns):
    override(user_account_routes.get_user_service, lambda: FakeService(**returns))


def test_create_user(client, override, as_admin):
    _use(override, create_user=_user())
    response = client.post("/api/users/create", json={"username": "tester", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == "user-1"


def test_list_users(client, override, as_admin):
    _use(override, list_users=[])
    response = client.get("/api/users/list")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_user(client, override, as_admin):
    _use(override, get_user=_user())
    response = client.get("/api/users/user-1/get_one")
    assert response.status_code == 200


def test_get_user_not_found(client, override, as_admin):
    _use(override, get_user=NotFoundError("User not found."))
    response = client.get("/api/users/missing/get_one")
    assert response.status_code == 404


def test_update_user(client, override, as_admin):
    _use(override, update_user=_user())
    response = client.put("/api/users/user-1/update", json={"username": "renamed"})
    assert response.status_code == 200


def test_delete_user(client, override, as_admin):
    _use(override, delete_user=None)
    response = client.delete("/api/users/user-1/delete")
    assert response.status_code == 200
