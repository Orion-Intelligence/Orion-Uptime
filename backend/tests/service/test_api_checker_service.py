from __future__ import annotations

import asyncio
import itertools
from datetime import UTC, datetime

import httpx

from orion.management.jobs.monitoring_controller.checkers import api_checker as api_checker_module
from orion.management.jobs.monitoring_controller.checkers.api_checker import ApiChecker
from orion.services.mongo_manager.shared_model.db_api_monitor_model import APIMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel
from tests.fake_model.fakes import FakeTokenManager

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
PROFILE_ID = "64f000000000000000000002"


def _monitor(**overrides) -> APIMonitorModel:
    fields = {"id": "64f000000000000000000001", "name": "API", "url": "https://api.example.com/health", "method": "GET", "expected_status_code": 200, "check_interval": 60, "timeout": 10, "created_at": NOW, "updated_at": NOW}
    fields.update(overrides)
    return APIMonitorModel(**fields)


def _profile(login_url: str = "https://api.example.com/login") -> AuthProfileModel:
    return AuthProfileModel(id=PROFILE_ID, name="App login", login_url=login_url, credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _checker(handler) -> ApiChecker:
    return ApiChecker(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _run(checker: ApiChecker, monitor: APIMonitorModel):
    return asyncio.run(checker.check(monitor))


def test_checker_reports_up_on_matching_status_code():
    checker = _checker(lambda request: httpx.Response(200))
    result = _run(checker, _monitor())

    assert result.success is True
    assert result.status == MonitorStatus.UP
    assert result.status_code == 200
    assert result.error is None


def test_checker_reports_down_on_unexpected_status_code():
    checker = _checker(lambda request: httpx.Response(500))
    result = _run(checker, _monitor(expected_status_code=200))

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert result.status_code == 500
    assert result.error is None


def test_checker_success_when_json_matches_expected_using_operators():
    checker = _checker(lambda request: httpx.Response(200, json={"status": "ok", "code": 5}))
    result = _run(checker, _monitor(expected_json={"status": "ok", "code": {"$gte": 1}}))

    assert result.success is True
    assert result.status == MonitorStatus.UP


def test_checker_reports_down_when_json_does_not_match():
    checker = _checker(lambda request: httpx.Response(200, json={"status": "fail"}))
    result = _run(checker, _monitor(expected_json={"status": "ok"}))

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert result.error == "The response JSON did not match the configured expected JSON."


def test_checker_reports_down_when_response_body_is_not_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    checker = _checker(handler)
    result = _run(checker, _monitor(expected_json={"status": "ok"}))

    assert result.success is False
    assert result.error == "The response JSON did not match the configured expected JSON."


def test_checker_reports_down_when_expected_header_is_missing():
    checker = _checker(lambda request: httpx.Response(200, headers={"X-Api-Version": "1"}))
    result = _run(checker, _monitor(expected_headers={"X-Api-Version": "2"}))

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert result.error == "One or more response headers did not match the configured expected headers."


def test_checker_success_when_expected_headers_match():
    checker = _checker(lambda request: httpx.Response(200, headers={"X-Api-Version": "2"}))
    result = _run(checker, _monitor(expected_headers={"X-Api-Version": "2"}))

    assert result.success is True


def test_checker_success_when_content_type_matches_partially():
    checker = _checker(lambda request: httpx.Response(200, json={"status": "ok"}))
    result = _run(checker, _monitor(expected_content_type="application/json"))

    assert result.success is True


def test_checker_reports_down_when_content_type_does_not_match():
    checker = _checker(lambda request: httpx.Response(200, json={"status": "ok"}))
    result = _run(checker, _monitor(expected_content_type="application/xml"))

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert result.error == "Expected Content-Type 'application/xml', but received 'application/json'."


def test_checker_reports_down_when_content_type_missing_from_response():
    checker = _checker(lambda request: httpx.Response(200, content=b"plain"))
    result = _run(checker, _monitor(expected_content_type="application/json"))

    assert result.success is False
    assert result.error == "Expected Content-Type 'application/json', but received 'not provided'."


def test_checker_reports_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    checker = _checker(handler)
    result = _run(checker, _monitor(timeout=5))

    assert result.success is False
    assert result.timed_out is True
    assert result.error == "The target did not complete its response within 5 seconds."


def test_checker_reports_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    checker = _checker(handler)
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.timed_out is False
    assert "Could not connect to the target" in (result.error or "")


def test_checker_reports_is_slow_when_response_time_exceeds_expectation(monkeypatch):
    timestamps = itertools.count(0.0, 1000.0)
    monkeypatch.setattr(api_checker_module.time, "perf_counter", lambda: next(timestamps))

    checker = _checker(lambda request: httpx.Response(200))
    result = _run(checker, _monitor(expected_response_time_ms=1))

    assert result.response_time_ms is not None
    assert result.response_time_ms > 1
    assert result.is_slow is True
    assert result.success is True


def test_checker_retries_once_after_unauthorized_with_auth_profile():
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cookie = request.headers.get("cookie")
        seen.append(cookie)
        return httpx.Response(401 if cookie == "access_token=token-1" else 200)

    token_manager = FakeTokenManager([_profile()])
    checker = ApiChecker(token_manager=token_manager, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor(auth_profile_id=PROFILE_ID))

    assert result.success is True
    assert seen == ["access_token=token-1", "access_token=token-2"]
    assert token_manager.refreshes == 1
