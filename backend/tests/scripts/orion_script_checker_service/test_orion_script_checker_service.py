from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx

from orion.api.interactive.orion_login_manager.orion_token_manager import AuthTokenError
from orion.constants.constant import OrionIntelligence
from orion.management.jobs.monitoring_controller.checkers.base_checker import CheckState, HttpCheckerBase
from orion.management.jobs.monitoring_controller.checkers.orion_script_checker import OrionScriptChecker
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import feeder_result_id
from tests.model.fakes import FakeTokenManager
from tests.scripts.orion_script_checker_service.fakes import _AccessTokenChecker, _ExplodingTokenManager, _HttpErrorOnListTokenManager, _ScriptedChecker, _TimeoutOnListTokenManager
from tests.scripts.orion_script_checker_service.helpers import _monitor, _profile, _raise, _route, _run, _scripts_payload


def test_checker_builds_feeder_statuses_from_scripts_and_values():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _route(httpx.Response(200, json=_scripts_payload()))(request)

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor())

    assert result.success is True
    assert result.status == MonitorStatus.UP
    assert result.status_code == 200
    assert [request.url.path for request in requests] == ["/api/profile/feeder/catalog", "/api/profile/feeder/scripts"]
    assert [request.url.params.get("entry_type") for request in requests] == [None, "scripts"]
    assert requests[0].headers["cookie"] == "access_token=token-1"
    by_key = {feeder.key: feeder for feeder in result.feeders}
    assert by_key["s1"].status == MonitorStatus.UP
    assert by_key["s1"].message == "ok"
    assert by_key["s1"].last_checked_at == datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
    assert by_key["s2"].status == MonitorStatus.DOWN
    assert by_key["s2"].enabled is False
    assert by_key["s2"].message == "boom"
    assert by_key["s3"].status == MonitorStatus.UNKNOWN
    assert by_key["s3"].section is None
    assert by_key["s1"].section == "leak"
    assert by_key["s4"].section == "social"
    assert "v1" not in by_key
    assert [feeder.key for feeder in result.feeders] == ["s1", "s4", "s2", "s3"]
    assert feeder_result_id("m1", "s1") == "m1:s1"


def test_checker_retries_once_after_unauthorized_response():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.headers["cookie"] == "access_token=token-1":
            return httpx.Response(401, json={"detail": "expired"})
        return _route(httpx.Response(200, json={"scripts": [{"id": "s1", "entry_kind": "script", "file_name": "_a.py"}], "has_more": False}))(request)

    token_manager = FakeTokenManager([_profile()])
    checker = OrionScriptChecker(token_manager=token_manager, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor())

    assert calls == 3
    assert token_manager.refreshes == 1
    assert result.success is True
    assert [feeder.key for feeder in result.feeders] == ["s1"]


def test_checker_reports_down_when_no_feeder_scripts_are_visible():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(httpx.Response(200, json={"scripts": [], "total": 0, "has_more": False})))))
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


def test_checker_uses_the_selected_auth_profile_over_domain_match():
    first = _profile()
    second = _profile().model_copy(update={"id": "64f000000000000000000003", "name": "Orion admin"})
    token_manager = FakeTokenManager([first, second])
    checker = OrionScriptChecker(token_manager=token_manager, client=httpx.AsyncClient(transport=httpx.MockTransport(_route(httpx.Response(200, json=_scripts_payload())))))
    result = _run(checker, _monitor().model_copy(update={"auth_profile_id": second.id}))

    assert result.success is True
    assert token_manager.token_profile_ids == [second.id]


def test_checker_reports_down_when_selected_auth_profile_is_missing():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(httpx.Response(200, json=_scripts_payload())))))
    result = _run(checker, _monitor().model_copy(update={"auth_profile_id": "64f000000000000000000009"}))

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert "no longer exists" in (result.error or "")


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


def test_checker_reports_down_when_scripts_have_no_usable_fields():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(httpx.Response(200, json={"scripts": [{"name": "_a.py", "url": None}], "has_more": False})))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert "Fields received: name, url" in (result.error or "")


def test_find_profile_matches_login_origin_case_insensitively():
    profile = _profile()
    assert OrionScriptChecker.find_profile([profile], "HTTPS://Orion.Example.com/") is profile
    assert OrionScriptChecker.find_profile([profile], "https://other.example.com") is None


def test_find_profile_returns_first_matching_profile_among_multiple():
    other = _profile().model_copy(update={"id": "64f000000000000000000009", "login_url": "https://other.example.com/login"})
    target = _profile()
    assert OrionScriptChecker.find_profile([other, target], "https://orion.example.com/api/feed") is target


def test_build_feeders_handles_datetime_instances_duplicate_and_missing_ids():
    scripts = [
        {"id": "", "file_name": "skip.py"},
        {"id": "d1", "rule_key": "leak", "file_name": "_first.py", "last_success_date": datetime(2026, 9, 4, 8, tzinfo=UTC), "last_success_message": "  ok  "},
        {"id": "d1", "rule_key": "leak", "file_name": "_dup.py"},
        {"id": "d2", "rule_key": "news", "file_name": "_only_success.py", "last_success_date": datetime(2026, 9, 4, 7)},
        {"id": "d3", "rule_key": "news", "file_name": "_only_failure.py", "last_failure_date": datetime(2026, 9, 4, 7)},
    ]
    feeders = OrionScriptChecker.build_feeders(scripts, {"leak": "leak_collector/leak", "news": "news_collector"})
    by_key = {feeder.key: feeder for feeder in feeders}

    assert list(by_key) == ["d1", "d2", "d3"]
    assert by_key["d1"].message == "ok"
    assert by_key["d1"].last_checked_at == datetime(2026, 9, 4, 8, tzinfo=UTC)
    assert by_key["d2"].status == MonitorStatus.UP
    assert by_key["d2"].last_checked_at == datetime(2026, 9, 4, 7, tzinfo=UTC)
    assert by_key["d2"].message is None
    assert by_key["d3"].status == MonitorStatus.DOWN
    assert by_key["d3"].last_checked_at == datetime(2026, 9, 4, 7, tzinfo=UTC)


def test_checker_reports_down_when_catalog_has_no_rules_array():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(httpx.Response(200, json=_scripts_payload()), catalog_response=lambda request: httpx.Response(200, json={"rules": "oops"})))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert "without a rules array" in (result.error or "")


def test_checker_reports_down_when_scripts_payload_missing_scripts_array():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(lambda request: httpx.Response(200, json={"has_more": False})))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert "without a scripts array" in (result.error or "")


def test_checker_paginates_until_has_more_is_false():
    pages_requested = []

    def scripts_response(request: httpx.Request) -> httpx.Response:
        pages_requested.append(request.url.params.get("page"))
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json={"scripts": [{"id": "p1", "entry_kind": "script", "file_name": "_p1.py"}], "has_more": True})
        return httpx.Response(200, json={"scripts": [{"id": "p2", "entry_kind": "script", "file_name": "_p2.py"}], "has_more": False})

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(scripts_response))))
    result = _run(checker, _monitor())

    assert pages_requested == ["1", "2"]
    assert result.success is True
    assert [feeder.key for feeder in result.feeders] == ["p1", "p2"]


def test_checker_reports_down_when_response_payload_is_not_an_object():
    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=["unexpected"]))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert "unexpected response for" in (result.error or "")


def test_checker_reports_down_when_token_manager_is_unavailable():
    checker = OrionScriptChecker(token_manager=None, client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.status == MonitorStatus.DOWN
    assert "Authentication failed" in (result.error or "")
    assert "cookie manager is unavailable" in (result.error or "")


def test_checker_reports_timeout_when_feeder_request_times_out():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor().model_copy(update={"timeout": 7}))

    assert result.success is False
    assert result.timed_out is True
    assert result.response_time_ms is not None
    assert "within 7 seconds" in (result.error or "")


def test_checker_reports_connection_error_before_response():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.timed_out is False
    assert "request failed before a response was received" in (result.error or "")


def test_checker_reports_down_on_unexpected_runtime_error():
    checker = OrionScriptChecker(token_manager=_ExplodingTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert "failed unexpectedly: RuntimeError" in (result.error or "")


def test_evaluate_not_implemented_on_base_class():
    try:
        asyncio.run(HttpCheckerBase()._evaluate(_monitor(), CheckState()))
    except NotImplementedError:
        pass
    else:
        raise AssertionError("expected NotImplementedError")


def test_close_only_disposes_owned_clients():
    owned = HttpCheckerBase()
    asyncio.run(owned.close())
    assert owned.client.is_closed is True

    external_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    injected = HttpCheckerBase(client=external_client)
    asyncio.run(injected.close())
    assert external_client.is_closed is False
    asyncio.run(external_client.aclose())


def test_check_reports_timeout_and_marks_elapsed():
    checker = _ScriptedChecker(_raise(httpx.TimeoutException("slow", request=httpx.Request("GET", "https://x"))))
    result = asyncio.run(checker.check(_monitor().model_copy(update={"timeout": 9})))

    assert result.success is False
    assert result.timed_out is True
    assert result.response_time_ms is not None
    assert "within 9 seconds" in (result.error or "")


def test_check_reports_http_error_variants():
    cases = [
        (httpx.ConnectError("boom", request=httpx.Request("GET", "https://x")), "Could not connect to the target"),
        (httpx.TooManyRedirects("boom", request=httpx.Request("GET", "https://x")), "too many redirects"),
        (httpx.RemoteProtocolError("boom"), "invalid or incomplete HTTP response"),
        (httpx.HTTPError("boom"), "request failed before a response was received"),
    ]
    for exc, expected in cases:
        checker = _ScriptedChecker(_raise(exc))
        result = asyncio.run(checker.check(_monitor()))
        assert result.success is False
        assert expected in (result.error or "")


def test_check_reports_unexpected_runtime_error():
    checker = _ScriptedChecker(_raise(RuntimeError("boom")))
    result = asyncio.run(checker.check(_monitor()))

    assert result.success is False
    assert "health checker failed unexpectedly: RuntimeError" in (result.error or "")


def test_access_token_reports_missing_token_manager():
    checker = _AccessTokenChecker()
    result = asyncio.run(checker.check(_monitor().model_copy(update={"auth_profile_id": "abc"})))

    assert result.success is False
    assert "cookie manager is unavailable" in (result.error or "")


def test_access_token_reports_missing_profile():
    checker = _AccessTokenChecker(token_manager=FakeTokenManager([]))
    result = asyncio.run(checker.check(_monitor().model_copy(update={"auth_profile_id": "abc123"})))

    assert result.success is False
    assert "Auth profile 'abc123' was not found" in (result.error or "")


def test_access_token_reports_origin_mismatch():
    profile = _profile()
    checker = _AccessTokenChecker(token_manager=FakeTokenManager([profile]))
    monitor = _monitor().model_copy(update={"auth_profile_id": profile.id, "url": "https://different.example.com/page"})
    result = asyncio.run(checker.check(monitor))

    assert result.success is False
    assert "login origin" in (result.error or "")


def test_access_token_returns_token_for_matching_profile():
    profile = _profile()
    token_manager = FakeTokenManager([profile])
    checker = _AccessTokenChecker(token_manager=token_manager)
    monitor = _monitor().model_copy(update={"auth_profile_id": profile.id})
    result = asyncio.run(checker.check(monitor))

    assert result.success is True
    assert token_manager.token_profile_ids == [profile.id]


def test_check_marks_no_elapsed_time_when_start_was_never_recorded():
    async def action(state):
        raise httpx.TimeoutException("slow", request=httpx.Request("GET", "https://x"))

    checker = _ScriptedChecker(action)
    result = asyncio.run(checker.check(_monitor()))

    assert result.success is False
    assert result.timed_out is True
    assert result.response_time_ms is None


def test_checker_reports_timeout_before_start_is_recorded():
    checker = OrionScriptChecker(token_manager=_TimeoutOnListTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.timed_out is True
    assert result.response_time_ms is None


def test_checker_reports_http_error_before_start_is_recorded():
    checker = OrionScriptChecker(token_manager=_HttpErrorOnListTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    result = _run(checker, _monitor())

    assert result.success is False
    assert result.response_time_ms is None
    assert "request failed before a response was received" in (result.error or "")


def test_checker_stops_pagination_at_max_pages_without_has_more_false():
    call_count = 0

    def scripts_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"scripts": [{"id": f"p{call_count}", "entry_kind": "script", "file_name": f"_p{call_count}.py"}], "has_more": True})

    checker = OrionScriptChecker(token_manager=FakeTokenManager([_profile()]), client=httpx.AsyncClient(transport=httpx.MockTransport(_route(scripts_response))))
    result = _run(checker, _monitor())

    assert call_count == OrionIntelligence.FEEDER_MAX_PAGES
    assert result.success is True
    assert len(result.feeders) == OrionIntelligence.FEEDER_MAX_PAGES


def test_build_feeders_ignores_invalid_dates_and_blank_messages():
    scripts = [
        {"id": "e1", "rule_key": "leak", "file_name": "_e1.py", "last_success_date": "not-a-date"},
        {"id": "e2", "rule_key": "leak", "file_name": "_e2.py", "last_success_date": "2026-09-04T08:00:00Z", "last_success_message": "   "},
    ]
    feeders = OrionScriptChecker.build_feeders(scripts)
    by_key = {feeder.key: feeder for feeder in feeders}

    assert by_key["e1"].status == MonitorStatus.UNKNOWN
    assert by_key["e2"].status == MonitorStatus.UP
    assert by_key["e2"].message is None


def test_fetch_scripts_requires_token_manager():
    checker = OrionScriptChecker(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    try:
        asyncio.run(checker._fetch_scripts(_monitor(), "profile-id"))
    except AuthTokenError:
        pass
    else:
        raise AssertionError("expected AuthTokenError")


def test_get_json_requires_token_manager():
    checker = OrionScriptChecker(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))))
    try:
        asyncio.run(checker._get_json(_monitor(), "profile-id", "token", "/path", {}))
    except AuthTokenError:
        pass
    else:
        raise AssertionError("expected AuthTokenError")
