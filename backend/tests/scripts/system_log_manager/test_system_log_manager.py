from __future__ import annotations

import asyncio

import httpx
import pytest

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
from orion.api.interactive.system_log_manager.system_log_manager import SystemLogManager
from orion.shared_models.exceptions import ValidationError
from tests.scripts.system_log_manager.fakes import FakeResponse
from tests.scripts.system_log_manager.fixtures import _reset_token_manager
from tests.scripts.system_log_manager.helpers import _auth_profile_service, _fake_client, _fake_token_manager, _manager


def test_get_logs_without_log_source_profile_raises_validation_error():
    manager, _ = _manager(responses=[FakeResponse(200, [])], profile=None)
    with pytest.raises(ValidationError):
        asyncio.run(manager.get_logs(None, None, None, None, 1, 25))


def test_get_logs_without_token_manager_raises_validation_error():
    manager, _ = _manager(responses=[FakeResponse(200, [])])
    with pytest.raises(ValidationError):
        asyncio.run(manager.get_logs(None, None, None, None, 1, 25))


def test_get_logs_builds_page_from_list_payload():
    token_manager, _ = _fake_token_manager()
    payload = [{"type": "ERROR", "message": "boom", "timestamp": "2024-01-01T00:00:00Z"}]
    manager, calls = _manager(responses=[FakeResponse(200, payload)], token_manager=token_manager)

    result = asyncio.run(manager.get_logs(None, None, None, None, 1, 25))

    assert result.source_profile_name == "Primary"
    assert result.total is None
    assert result.has_more is False
    assert len(result.logs) == 1
    assert result.logs[0].type == "ERROR"
    assert result.logs[0].message == "boom"
    assert calls[0]["url"] == "https://logs.example.com/api/profile/system-logs"


def test_get_logs_applies_filters_to_query_params():
    token_manager, _ = _fake_token_manager()
    manager, calls = _manager(responses=[FakeResponse(200, [])], token_manager=token_manager)

    asyncio.run(manager.get_logs("2024-01-01", "all", "2024-01-01", "2024-01-31", 2, 50))

    params = calls[0]["params"]
    assert params["page"] == 2
    assert params["limit"] == 50
    assert params["date"] == "2024-01-01"
    assert params["date_from"] == "2024-01-01"
    assert params["date_to"] == "2024-01-31"
    assert "log_type" not in params


def test_get_logs_includes_log_type_when_not_all():
    token_manager, _ = _fake_token_manager()
    manager, calls = _manager(responses=[FakeResponse(200, [])], token_manager=token_manager)

    asyncio.run(manager.get_logs(None, "ERROR", None, None, 1, 25))

    assert calls[0]["params"]["log_type"] == "ERROR"


def test_get_logs_nested_dict_payload_uses_total_to_compute_has_more():
    token_manager, _ = _fake_token_manager()
    payload = {"data": {"logs": [{"message": "one"}, {"message": "two"}], "total": 2, "has_more": True}}
    manager, _ = _manager(responses=[FakeResponse(200, payload)], token_manager=token_manager)

    result = asyncio.run(manager.get_logs(None, None, None, None, 1, 25))

    assert result.total == 2
    assert result.has_more is False
    assert len(result.logs) == 2


def test_get_logs_without_total_falls_back_to_limit_comparison():
    token_manager, _ = _fake_token_manager()
    payload = {"results": [{"message": "one"}]}
    manager, _ = _manager(responses=[FakeResponse(200, payload)], token_manager=token_manager)

    result = asyncio.run(manager.get_logs(None, None, None, None, 1, 1))

    assert result.total is None
    assert result.has_more is True


def test_get_logs_retries_once_on_401_then_succeeds():
    token_manager, token_calls = _fake_token_manager()
    manager, calls = _manager(responses=[FakeResponse(401), FakeResponse(200, [{"message": "ok"}])], token_manager=token_manager)

    result = asyncio.run(manager.get_logs(None, None, None, None, 1, 25))

    assert len(calls) == 2
    assert token_calls[0]["force_refresh"] is False
    assert token_calls[1]["force_refresh"] is True
    assert result.logs[0].message == "ok"


def test_get_logs_auth_token_error_raises_validation_error():
    token_manager, _ = _fake_token_manager(error=auth_token_state.AuthTokenError("login failed"))
    manager, _ = _manager(responses=[FakeResponse(200, [])], token_manager=token_manager)

    with pytest.raises(ValidationError):
        asyncio.run(manager.get_logs(None, None, None, None, 1, 25))


def test_get_logs_http_error_raises_validation_error():
    token_manager, _ = _fake_token_manager()
    manager, _ = _manager(responses=[httpx.ConnectError("connection refused")], token_manager=token_manager)

    with pytest.raises(ValidationError):
        asyncio.run(manager.get_logs(None, None, None, None, 1, 25))


def test_get_logs_non_200_status_raises_validation_error():
    token_manager, _ = _fake_token_manager()
    manager, _ = _manager(responses=[FakeResponse(500)], token_manager=token_manager)

    with pytest.raises(ValidationError):
        asyncio.run(manager.get_logs(None, None, None, None, 1, 25))


def test_get_logs_invalid_json_raises_validation_error():
    token_manager, _ = _fake_token_manager()
    manager, _ = _manager(responses=[FakeResponse(200, bad_json=True)], token_manager=token_manager)

    with pytest.raises(ValidationError):
        asyncio.run(manager.get_logs(None, None, None, None, 1, 25))


def test_close_closes_owned_client():
    manager = SystemLogManager(_auth_profile_service())
    asyncio.run(manager.close())
    assert manager.client.is_closed is True


def test_close_leaves_shared_client_open():
    client, _ = _fake_client([FakeResponse(200, [])])
    manager = SystemLogManager(_auth_profile_service(), client=client)
    asyncio.run(manager.close())
    assert manager.client is client
