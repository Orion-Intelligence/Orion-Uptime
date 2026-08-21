import pytest
from httpx import ASGITransport, AsyncClient

from app.core.app_dependency import app_dependency
from app.main import app
from app.modules.auth_manager.auth_manager import login_throttle
from app.service.authorization import get_auth_service
from app.service.constants import Messages
from app.service.exceptions import AuthenticationError
from app.service.mongo_db.shared_models.db_user_account_model import CurrentUserResponse, TokenResponse, UserRole

pytestmark = pytest.mark.anyio

USER_ID = "507f1f77bcf86cd799439011"


class FakeAuthManager:
    jwt_service = app_dependency

    async def login(self, username: str, password: str) -> TokenResponse:
        if username == "admin" and password == "correct-password":
            return TokenResponse(
                access_token=app_dependency.create_access_token(USER_ID, "admin", UserRole.ADMIN),
                refresh_token=app_dependency.create_refresh_token(USER_ID, "admin", UserRole.ADMIN)[0],
            )
        raise AuthenticationError(Messages.INVALID_CREDENTIALS)

    async def get_current_user(self, user_id: str) -> CurrentUserResponse:
        return CurrentUserResponse(id=user_id, username="admin", role=UserRole.ADMIN)

    async def logout(self, _user_id: str) -> None:
        return None


@pytest.fixture
async def client():
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthManager()
    login_throttle._failures.clear()
    login_throttle._locked_until.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as http:
        yield http
    app.dependency_overrides.clear()


async def test_login_sets_httponly_cookies_and_returns_no_tokens(client):
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "correct-password"})
    assert response.status_code == 200
    assert response.json()["data"] is None
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for cookie in cookies:
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/api" in cookie
        assert "Secure" in cookie


async def test_security_headers_present(client):
    response = await client.get("/api/health")
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


async def test_docs_disabled_outside_development(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        response = await client.get(path)
        assert not response.headers.get("content-type", "").startswith("application/json")
        assert "swagger" not in response.text.lower()
        assert '"paths"' not in response.text


async def test_login_throttled_after_repeated_failures(client):
    for _ in range(5):
        response = await client.post("/api/auth/login", json={"username": "victim", "password": "wrong-password-1"})
        assert response.status_code == 401
    response = await client.post("/api/auth/login", json={"username": "victim", "password": "wrong-password-1"})
    assert response.status_code == 429
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "correct-password"})
    assert response.status_code == 200


async def test_logout_revokes_access_token(client):
    login = await client.post("/api/auth/login", json={"username": "admin", "password": "correct-password"})
    assert login.status_code == 200
    assert (await client.get("/api/auth/me")).status_code == 200
    access_cookie = client.cookies.get("access_token")
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 200
    client.cookies.clear()
    client.cookies.set("access_token", access_cookie, path="/api")
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_bearer_header_is_not_accepted(client):
    token = app_dependency.create_access_token(USER_ID, "admin", UserRole.ADMIN)
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


class FakeScheduler:
    def __init__(self, healthy: bool):
        self.healthy = healthy

    def is_healthy(self, _stall_seconds: float = 0) -> bool:
        return self.healthy

    def status(self) -> dict:
        return {"running": self.healthy, "workers": 1, "alive_workers": 1 if self.healthy else 0, "seconds_since_reconcile": 1.0, "last_reconcile_error": None}


async def test_health_reflects_scheduler_state(client, monkeypatch):
    import app.modules.monitoring_controller.scheduler as scheduler_state

    monkeypatch.setattr(scheduler_state, "scheduler", None)
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"

    monkeypatch.setattr(scheduler_state, "scheduler", FakeScheduler(healthy=False))
    assert (await client.get("/api/health")).status_code == 503

    monkeypatch.setattr(scheduler_state, "scheduler", FakeScheduler(healthy=True))
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["scheduler"]["alive_workers"] == 1
