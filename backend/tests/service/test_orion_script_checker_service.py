from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx

from orion.management.jobs.monitoring_controller.checkers.orion_script_checker import OrionScriptChecker
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionScriptMonitorModel, feeder_result_id

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


class FakeTokenManager:
    def __init__(self, profiles: list[AuthProfileModel], token: str = "token-1"):
        self.auth_profile_service = SimpleNamespace(list_profile_models=self._list_profiles)
        self._profiles = profiles
        self._token = token
        self.refreshes = 0

    async def _list_profiles(self):
        return self._profiles

    async def get_token(self, profile_id: str, *, force_refresh: bool = False) -> str:
        if force_refresh:
            self.refreshes += 1
            self._token = "token-2"
        return self._token


def _monitor() -> OrionScriptMonitorModel:
    return OrionScriptMonitorModel(id="64f000000000000000000001", name="Orion", url="https://orion.example.com", check_interval=300, timeout=10, created_at=NOW, updated_at=NOW)


def _profile() -> AuthProfileModel:
    return AuthProfileModel(id="64f000000000000000000002", name="Orion login", login_url="https://orion.example.com/api/login", credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _scripts_payload() -> dict:
    return {
        "scripts": [
            {"id": "s1", "rule_key": "leak", "entry_kind": "script", "enabled": True, "file_name": "_leak_parser.py", "last_success_date": "2026-09-04T10:00:00Z", "last_failure_date": "2026-09-03T10:00:00Z", "last_success_message": "ok", "values": []},
            {"id": "s2", "rule_key": "news", "entry_kind": "script", "enabled": False, "file_name": "_news_parser.py", "last_success_date": "2026-09-01T10:00:00+00:00", "last_failure_date": "2026-09-02T10:00:00+00:00", "last_failure_message": "boom"},
            {"id": "v1", "rule_key": "generic", "entry_kind": "values", "enabled": True, "file_name": "_generic__values", "values": [{"url": "https://a.example.com", "status": "failure", "last_checked_at": "2026-09-04T09:00:00Z", "last_error": "timeout"}, {"url": "https://b.example.com", "status": "pending"}]},
            {"id": "s3", "entry_kind": "script", "file_name": "_fresh.py"},
        ],
        "has_more": False,
    }


def _run(checker: OrionScriptChecker, monitor: OrionScriptMonitorModel):
    return asyncio.run(checker.check(monitor))


def test_checker_builds_feeder_statuses_from_scripts_and_values():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_scripts_payload())

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor())

    assert result.success is True
    assert result.status == MonitorStatus.UP
    assert result.status_code == 200
    assert requests[0].url.path == "/api/profile/feeder/scripts"
    assert requests[0].headers["cookie"] == "access_token=token-1"
    by_key = {feeder.key: feeder for feeder in result.feeders}
    assert by_key["s1"].status == MonitorStatus.UP
    assert by_key["s1"].message == "ok"
    assert by_key["s1"].last_checked_at == datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    assert by_key["s2"].status == MonitorStatus.DOWN
    assert by_key["s2"].enabled is False
    assert by_key["s2"].message == "boom"
    assert by_key["s3"].status == MonitorStatus.UNKNOWN
    values = [feeder for feeder in result.feeders if feeder.key.startswith("v1:")]
    assert {feeder.name: feeder.status for feeder in values} == {"https://a.example.com": MonitorStatus.DOWN, "https://b.example.com": MonitorStatus.UNKNOWN}
    assert values[0].message == "timeout"
    assert feeder_result_id("m1", values[0].key) == f"m1:{values[0].key}"


def test_checker_retries_once_after_unauthorized_response():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.headers["cookie"] == "access_token=token-1":
            return httpx.Response(401, json={"detail": "expired"})
        return httpx.Response(200, json={"scripts": [{"id": "s1", "entry_kind": "script", "file_name": "_a.py"}], "has_more": False})

    token_manager = FakeTokenManager([_profile()])
    checker = OrionScriptChecker(token_manager=token_manager, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor())

    assert calls == 2
    assert token_manager.refreshes == 1
    assert result.success is True
    assert [feeder.key for feeder in result.feeders] == ["s1"]


def test_checker_reports_down_when_no_feeder_scripts_are_visible():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"scripts": [], "total": 0, "has_more": False}))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert result.status_code == 200
    assert "no feeder scripts" in (result.error or "")


def test_checker_reports_down_without_matching_auth_profile():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"scripts": []}))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert result.error is not None
    assert "https://orion.example.com" in result.error


def test_checker_reports_down_on_error_status_and_invalid_payload():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(403, json={"detail": "forbidden"}))))
    result = _run(checker, _monitor())
    assert result.success is False
    assert result.status_code == 403
    assert "HTTP 403" in (result.error or "")

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json"))))
    result = _run(checker, _monitor())
    assert result.success is False
    assert "valid JSON" in (result.error or "")
    assert json.dumps(result.model_dump(mode="json")["feeders"]) == "[]"


def test_find_profile_matches_login_origin_case_insensitively():
    profile = _profile()
    assert OrionScriptChecker.find_profile([profile], "HTTPS://Orion.Example.com/") is profile
    assert OrionScriptChecker.find_profile([profile], "https://other.example.com") is None
