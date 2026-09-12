from __future__ import annotations

import httpx

from orion.management.jobs.monitoring_controller.checkers.http_checker import HTTPChecker
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from tests.model.fakes import FakeTokenManager
from tests.scripts.http_checker_service.helpers import PROFILE_ID, _monitor, _profile, _run


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
