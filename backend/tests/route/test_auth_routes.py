from __future__ import annotations

from orion.services.mongo_manager.shared_model.db_user_account_model import AuthTokens
from orion.shared_models.exceptions import AuthenticationError
from routes import auth_routes
from tests.fake_model.fakes import FakeService


def test_login_sets_cookies_and_succeeds(client, override):
    override(auth_routes.get_auth_service, lambda: FakeService(login=AuthTokens(access_token="access", refresh_token="refresh")))
    response = client.post("/api/auth/login", json={"username": "tester", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "access_token" in response.cookies


def test_login_rejects_invalid_credentials(client, override):
    override(auth_routes.get_auth_service, lambda: FakeService(login=AuthenticationError("Invalid username or password.")))
    response = client.post("/api/auth/login", json={"username": "tester", "password": "password123"})
    assert response.status_code == 401


def test_session_without_cookies_reports_no_active_session(client, override):
    override(auth_routes.get_auth_service, lambda: FakeService())
    response = client.get("/api/auth/session")
    assert response.status_code == 200
    assert response.json()["data"] is None


def test_me_returns_current_user(client, as_admin):
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["data"]["username"] == as_admin.username


def test_logout_clears_session(client, override, as_admin):
    override(auth_routes.get_auth_service, lambda: FakeService(logout=None))
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["success"] is True
