from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from orion.management.jobs.monitoring_controller.checkers.http_checker import HTTPChecker
from orion.services.mongo_manager.shared_model.db_http_monitor_model import HTTPMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
PROFILE_ID = "64f000000000000000000002"


class FakeTokenManager:
    def __init__(self, profiles: list[AuthProfileModel], token: str = "token-1"):
        self.auth_profile_service = SimpleNamespace(get_profile_model=self._get_profile)
        self._profiles = profiles
        self._token = token
        self.refreshes = 0

    async def _get_profile(self, profile_id: str):
        return next((profile for profile in self._profiles if profile.id == profile_id), None)

    async def get_token(self, profile_id: str, *, force_refresh: bool = False) -> str:
        if force_refresh:
            self.refreshes += 1
            self._token = "token-2"
        return self._token


def _monitor(auth_profile_id: str | None = None) -> HTTPMonitorModel:
    return HTTPMonitorModel(id="64f000000000000000000001", name="Site", url="https://app.example.com/health", check_interval=60, timeout=10, expected_status_code=200, auth_profile_id=auth_profile_id, created_at=NOW, updated_at=NOW)


def _profile(login_url: str = "https://app.example.com/api/login") -> AuthProfileModel:
    return AuthProfileModel(id=PROFILE_ID, name="App login", login_url=login_url, credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _run(checker: HTTPChecker, monitor: HTTPMonitorModel):
    return asyncio.run(checker.check(monitor))


def test_checker_sends_no_cookie_without_an_auth_profile():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200)

    result = _run(HTTPChecker(client=httpx.AsyncClient(transport=httpx.MockTransport(handler))), _monitor())

    assert result.success is True
    assert seen == [None]


def test_checker_sends_session_cookie_and_retries_once_after_unauthorized():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(401 if request.headers.get("cookie") == "access_token=token-1" else 200)

    token_manager = FakeTokenManager([_profile()])
    result = _run(HTTPChecker(token_manager=token_manager, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))), _monitor(PROFILE_ID))

    assert result.success is True
    assert result.status_code == 200
    assert seen == ["access_token=token-1", "access_token=token-2"]
    assert token_manager.refreshes == 1


def test_checker_reports_down_when_profile_origin_differs():
    checker = HTTPChecker(token_manager=FakeTokenManager([_profile("https://other.example.com/login")]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    result = _run(checker, _monitor(PROFILE_ID))

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert "login origin" in (result.error or "")
