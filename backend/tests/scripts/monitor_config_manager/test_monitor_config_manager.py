from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.services.mongo_manager.shared_model.db_monitor_config_model import ApiMonitorConfig, HeartbeatMonitorConfig, HttpMonitorConfig, PingMonitorConfig
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from orion.shared_models.exceptions import NotFoundError, ValidationError
from tests.model.fakes import FakeCollection
from tests.scripts.monitor_config_manager.helpers import _api_manager, _auth_profile_service, _heartbeat_manager, _http_manager, _manager, _ping_manager


def test_export_monitor_http_found_resolves_auth_profile_name():
    profile = SimpleNamespace(name="Profile A")
    monitor = SimpleNamespace(persisted_id="http-1", name="HTTP Mon", url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=500, auth_profile_id="auth1", is_active=True)
    manager, _ = _manager(http=_http_manager(monitor=monitor), api=_api_manager(auth_profile_service=_auth_profile_service(by_id=profile)))

    result = asyncio.run(manager.export_monitor(MonitorType.HTTP, "http-1"))

    assert isinstance(result, HttpMonitorConfig)
    assert result.monitor_id == "http-1"
    assert result.url == "https://example.com"
    assert result.auth_profile_id is None
    assert result.auth_profile_name == "Profile A"


def test_export_monitor_http_without_auth_profile_service_keeps_id():
    monitor = SimpleNamespace(persisted_id="http-1", name="HTTP Mon", url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=None, auth_profile_id="auth1", is_active=True)
    manager, _ = _manager(http=_http_manager(monitor=monitor))

    result = asyncio.run(manager.export_monitor(MonitorType.HTTP, "http-1"))

    assert result.auth_profile_id == "auth1"
    assert result.auth_profile_name is None


def test_export_monitor_http_unknown_auth_profile_keeps_id():
    monitor = SimpleNamespace(persisted_id="http-1", name="HTTP Mon", url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=None, auth_profile_id="ghost", is_active=True)
    manager, _ = _manager(http=_http_manager(monitor=monitor), api=_api_manager(auth_profile_service=_auth_profile_service(by_id=None)))

    result = asyncio.run(manager.export_monitor(MonitorType.HTTP, "http-1"))

    assert result.auth_profile_id == "ghost"
    assert result.auth_profile_name is None


def test_export_monitor_http_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.export_monitor(MonitorType.HTTP, "missing"))


def test_export_monitor_api_found_resolves_auth_profile_name():
    profile = SimpleNamespace(name="Profile B")
    monitor = SimpleNamespace(persisted_id="api-1", name="API Mon", url="https://api.example.com", method="POST", headers={"X": "1"}, request_body={"a": 1}, expected_status_code=200, expected_json={"ok": True}, check_interval=60, timeout=10, expected_response_time_ms=300, expected_headers={"Y": "2"}, expected_content_type="application/json", auth_profile_id="auth1", is_active=True)
    manager, _ = _manager(api=_api_manager(monitor=monitor, auth_profile_service=_auth_profile_service(by_id=profile)))

    result = asyncio.run(manager.export_monitor(MonitorType.API, "api-1"))

    assert isinstance(result, ApiMonitorConfig)
    assert result.method == "POST"
    assert result.auth_profile_id is None
    assert result.auth_profile_name == "Profile B"


def test_export_monitor_api_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.export_monitor(MonitorType.API, "missing"))


def test_export_monitor_ping_found_and_not_found():
    monitor = SimpleNamespace(persisted_id="ping-1", name="Ping Mon", host="example.com", check_interval=60, timeout=5, expected_response_time_ms=100, is_active=True)
    manager, _ = _manager(ping=_ping_manager(monitor=monitor))

    result = asyncio.run(manager.export_monitor(MonitorType.PING, "ping-1"))
    assert isinstance(result, PingMonitorConfig)
    assert result.host == "example.com"

    manager_missing, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager_missing.export_monitor(MonitorType.PING, "missing"))


def test_export_monitor_heartbeat_found_and_not_found():
    monitor = SimpleNamespace(persisted_id="hb-1", name="HB Mon", expected_heartbeat_interval=60, grace_period=30, is_active=True)
    manager, _ = _manager(heartbeat=_heartbeat_manager(monitor=monitor))

    result = asyncio.run(manager.export_monitor(MonitorType.HEARTBEAT, "hb-1"))
    assert isinstance(result, HeartbeatMonitorConfig)
    assert result.expected_heartbeat_interval == 60

    manager_missing, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager_missing.export_monitor(MonitorType.HEARTBEAT, "missing"))


def test_import_monitor_http_creates_new_when_active():
    created = SimpleNamespace(id="new-http-1")
    manager, calls = _manager(http=_http_manager(create_result=created))
    config = HttpMonitorConfig(name="New HTTP", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert result.monitor_id == "new-http-1"
    assert result.monitor_type == MonitorType.HTTP
    assert result.heartbeat_token is None
    assert calls["http"]["create"][0]["url"] == "https://example.com"
    assert calls["http"]["update"] == []


def test_import_monitor_http_creates_and_deactivates_when_inactive():
    created = SimpleNamespace(id="new-http-2")
    manager, calls = _manager(http=_http_manager(create_result=created))
    config = HttpMonitorConfig(name="New HTTP", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, is_active=False)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert len(calls["http"]["update"]) == 1
    assert calls["http"]["update"][0]["is_active"] is False
    assert calls["http"]["update"][0]["name"] is None


def test_import_monitor_api_creates_new_when_active():
    created = SimpleNamespace(id="new-api-1")
    manager, calls = _manager(api=_api_manager(create_result=created))
    config = ApiMonitorConfig(name="New API", monitor_type=MonitorType.API, url="https://api.example.com", expected_status_code=200, check_interval=60)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert result.monitor_id == "new-api-1"
    request = calls["api"]["create"][0]
    assert request.url == "https://api.example.com"
    assert request.name == "New API"
    assert calls["api"]["update"] == []


def test_import_monitor_api_creates_and_deactivates_when_inactive():
    created = SimpleNamespace(id="new-api-2")
    manager, calls = _manager(api=_api_manager(create_result=created))
    config = ApiMonitorConfig(name="New API", monitor_type=MonitorType.API, url="https://api.example.com", expected_status_code=200, check_interval=60, is_active=False)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    monitor_id, request = calls["api"]["update"][0]
    assert monitor_id == "new-api-2"
    assert request.is_active is False


def test_import_monitor_ping_creates_new_when_active():
    created = SimpleNamespace(id="new-ping-1")
    manager, calls = _manager(ping=_ping_manager(create_result=created))
    config = PingMonitorConfig(name="New Ping", monitor_type=MonitorType.PING, host="example.com", check_interval=60, timeout=5)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert result.monitor_id == "new-ping-1"
    assert calls["ping"]["create"][0]["host"] == "example.com"
    assert calls["ping"]["update"] == []


def test_import_monitor_ping_creates_and_deactivates_when_inactive():
    created = SimpleNamespace(id="new-ping-2")
    manager, calls = _manager(ping=_ping_manager(create_result=created))
    config = PingMonitorConfig(name="New Ping", monitor_type=MonitorType.PING, host="example.com", check_interval=60, timeout=5, is_active=False)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert calls["ping"]["update"][0]["is_active"] is False


def test_import_monitor_heartbeat_creates_new_and_returns_token():
    token = "heartbeat-token-1"
    object_id = ObjectId()
    collection = FakeCollection()
    collection.documents.append({"_id": object_id, "heartbeat_token_hash": hashlib.sha256(token.encode()).hexdigest()})
    manager, calls = _manager(heartbeat=_heartbeat_manager(create_result=SimpleNamespace(heartbeat_token=token), collection=collection))
    config = HeartbeatMonitorConfig(name="HB", monitor_type=MonitorType.HEARTBEAT, expected_heartbeat_interval=60, grace_period=30)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert result.monitor_id == str(object_id)
    assert result.heartbeat_token == token
    assert calls["heartbeat"]["update"] == []


def test_import_monitor_heartbeat_creates_and_deactivates_when_inactive():
    token = "heartbeat-token-2"
    object_id = ObjectId()
    collection = FakeCollection()
    collection.documents.append({"_id": object_id, "heartbeat_token_hash": hashlib.sha256(token.encode()).hexdigest()})
    manager, calls = _manager(heartbeat=_heartbeat_manager(create_result=SimpleNamespace(heartbeat_token=token), collection=collection))
    config = HeartbeatMonitorConfig(name="HB", monitor_type=MonitorType.HEARTBEAT, expected_heartbeat_interval=60, grace_period=30, is_active=False)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    monitor_id, kwargs = calls["heartbeat"]["update"][0]
    assert monitor_id == str(object_id)
    assert kwargs["is_active"] is False


def test_import_monitor_heartbeat_creation_lookup_failure_raises_runtime_error():
    manager, _ = _manager(heartbeat=_heartbeat_manager(create_result=SimpleNamespace(heartbeat_token="whatever")))
    config = HeartbeatMonitorConfig(name="HB", monitor_type=MonitorType.HEARTBEAT, expected_heartbeat_interval=60, grace_period=30)

    with pytest.raises(RuntimeError):
        asyncio.run(manager.import_monitor(config))


def test_import_monitor_http_updates_existing_when_changed():
    existing = SimpleNamespace(persisted_id="http-1", name="Old Name", url="https://same.example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=None, auth_profile_id=None, is_active=True)
    manager, calls = _manager(http=_http_manager(monitor=existing))
    config = HttpMonitorConfig(monitor_id="http-1", name="New Name", monitor_type=MonitorType.HTTP, url="https://same.example.com", check_interval=60, timeout=5, expected_status_code=200)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert result.monitor_id == "http-1"
    assert calls["http"]["update"][0]["name"] == "New Name"
    assert calls["http"]["update"][0]["url"] is None


def test_import_monitor_http_update_skips_call_when_no_changes():
    existing = SimpleNamespace(persisted_id="http-1", name="Same", url="https://same.example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=None, auth_profile_id=None, is_active=True)
    manager, calls = _manager(http=_http_manager(monitor=existing))
    config = HttpMonitorConfig(monitor_id="http-1", name="Same", monitor_type=MonitorType.HTTP, url="https://same.example.com", check_interval=60, timeout=5, expected_status_code=200)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert calls["http"]["update"] == []


def test_import_monitor_http_update_clears_expected_response_time():
    object_id = ObjectId()
    monitor_id = str(object_id)
    existing = SimpleNamespace(persisted_id=monitor_id, name="Same", url="https://same.example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=500, auth_profile_id=None, is_active=True)
    collection = FakeCollection()
    collection.documents.append({"_id": object_id, "expected_response_time_ms": 500})
    manager, calls = _manager(http=_http_manager(monitor=existing, collection=collection))
    config = HttpMonitorConfig(monitor_id=monitor_id, name="Same", monitor_type=MonitorType.HTTP, url="https://same.example.com", check_interval=60, timeout=5, expected_status_code=200, expected_response_time_ms=None)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert collection.documents[0]["expected_response_time_ms"] is None
    assert calls["http"]["update"][0]["expected_response_time_ms"] is None


def test_import_monitor_api_updates_existing_when_changed():
    existing = SimpleNamespace(persisted_id="api-1", name="Old", url="https://api.example.com", method="GET", headers={}, request_body=None, expected_status_code=200, expected_json=None, check_interval=60, timeout=10, expected_response_time_ms=None, expected_headers=None, expected_content_type=None, auth_profile_id=None, is_active=True)
    manager, calls = _manager(api=_api_manager(monitor=existing))
    config = ApiMonitorConfig(monitor_id="api-1", name="New", monitor_type=MonitorType.API, url="https://api.example.com", expected_status_code=200, check_interval=60)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    monitor_id, request = calls["api"]["update"][0]
    assert monitor_id == "api-1"
    assert request.name == "New"


def test_import_monitor_api_update_skips_call_when_no_changes():
    existing = SimpleNamespace(persisted_id="api-1", name="Same", url="https://api.example.com", method="GET", headers={}, request_body=None, expected_status_code=200, expected_json=None, check_interval=60, timeout=10, expected_response_time_ms=None, expected_headers=None, expected_content_type=None, auth_profile_id=None, is_active=True)
    manager, calls = _manager(api=_api_manager(monitor=existing))
    config = ApiMonitorConfig(monitor_id="api-1", name="Same", monitor_type=MonitorType.API, url="https://api.example.com", expected_status_code=200, check_interval=60)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert calls["api"]["update"] == []


def test_import_monitor_ping_updates_existing_when_changed():
    existing = SimpleNamespace(persisted_id="ping-1", name="Old", host="same.example.com", check_interval=60, timeout=5, expected_response_time_ms=None, is_active=True)
    manager, calls = _manager(ping=_ping_manager(monitor=existing))
    config = PingMonitorConfig(monitor_id="ping-1", name="New", monitor_type=MonitorType.PING, host="same.example.com", check_interval=60, timeout=5)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert calls["ping"]["update"][0]["name"] == "New"


def test_import_monitor_ping_update_skips_call_when_no_changes():
    existing = SimpleNamespace(persisted_id="ping-1", name="Same", host="same.example.com", check_interval=60, timeout=5, expected_response_time_ms=None, is_active=True)
    manager, calls = _manager(ping=_ping_manager(monitor=existing))
    config = PingMonitorConfig(monitor_id="ping-1", name="Same", monitor_type=MonitorType.PING, host="same.example.com", check_interval=60, timeout=5)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert calls["ping"]["update"] == []


def test_import_monitor_ping_update_clears_expected_response_time():
    object_id = ObjectId()
    monitor_id = str(object_id)
    existing = SimpleNamespace(persisted_id=monitor_id, name="Same", host="same.example.com", check_interval=60, timeout=5, expected_response_time_ms=250, is_active=True)
    collection = FakeCollection()
    collection.documents.append({"_id": object_id, "expected_response_time_ms": 250})
    manager, calls = _manager(ping=_ping_manager(monitor=existing, collection=collection))
    config = PingMonitorConfig(monitor_id=monitor_id, name="Same", monitor_type=MonitorType.PING, host="same.example.com", check_interval=60, timeout=5)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert collection.documents[0]["expected_response_time_ms"] is None
    assert calls["ping"]["update"][0]["expected_response_time_ms"] is None


def test_import_monitor_heartbeat_updates_existing_when_changed():
    existing = SimpleNamespace(persisted_id="hb-1", name="Old", expected_heartbeat_interval=60, grace_period=30, is_active=True)
    manager, calls = _manager(heartbeat=_heartbeat_manager(monitor=existing))
    config = HeartbeatMonitorConfig(monitor_id="hb-1", name="New", monitor_type=MonitorType.HEARTBEAT, expected_heartbeat_interval=60, grace_period=30)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    monitor_id, kwargs = calls["heartbeat"]["update"][0]
    assert monitor_id == "hb-1"
    assert kwargs["name"] == "New"


def test_import_monitor_heartbeat_update_skips_call_when_no_changes():
    existing = SimpleNamespace(persisted_id="hb-1", name="Same", expected_heartbeat_interval=60, grace_period=30, is_active=True)
    manager, calls = _manager(heartbeat=_heartbeat_manager(monitor=existing))
    config = HeartbeatMonitorConfig(monitor_id="hb-1", name="Same", monitor_type=MonitorType.HEARTBEAT, expected_heartbeat_interval=60, grace_period=30)

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "updated"
    assert calls["heartbeat"]["update"] == []


def test_import_monitor_resolves_auth_profile_by_name():
    profile = SimpleNamespace(persisted_id=str(ObjectId()), name="Login Profile")
    created = SimpleNamespace(id="new-http-3")
    manager, calls = _manager(http=_http_manager(create_result=created), api=_api_manager(auth_profile_service=_auth_profile_service(by_name=profile)))
    config = HttpMonitorConfig(name="With Auth", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, auth_profile_name="Login Profile")

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert calls["http"]["create"][0]["auth_profile_id"] == profile.persisted_id


def test_import_monitor_treats_non_object_id_auth_profile_id_as_name():
    profile = SimpleNamespace(persisted_id=str(ObjectId()), name="Legacy Profile")
    created = SimpleNamespace(id="new-http-4")
    manager, calls = _manager(http=_http_manager(create_result=created), api=_api_manager(auth_profile_service=_auth_profile_service(by_name=profile)))
    config = HttpMonitorConfig(name="With Auth", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, auth_profile_id="Legacy Profile")

    asyncio.run(manager.import_monitor(config))

    assert calls["http"]["create"][0]["auth_profile_id"] == profile.persisted_id


def test_import_monitor_accepts_matching_auth_profile_id_and_name():
    profile_id = str(ObjectId())
    profile = SimpleNamespace(persisted_id=profile_id, name="Login Profile")
    created = SimpleNamespace(id="new-http-5")
    manager, calls = _manager(http=_http_manager(create_result=created), api=_api_manager(auth_profile_service=_auth_profile_service(by_name=profile)))
    config = HttpMonitorConfig(name="With Auth", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, auth_profile_id=profile_id, auth_profile_name="Login Profile")

    result = asyncio.run(manager.import_monitor(config))

    assert result.action == "created"
    assert calls["http"]["create"][0]["auth_profile_id"] == profile_id


def test_import_monitor_rejects_mismatched_auth_profile_id_and_name():
    profile = SimpleNamespace(persisted_id=str(ObjectId()), name="Login Profile")
    manager, _ = _manager(api=_api_manager(auth_profile_service=_auth_profile_service(by_name=profile)))
    other_id = str(ObjectId())
    config = HttpMonitorConfig(name="With Auth", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, auth_profile_id=other_id, auth_profile_name="Login Profile")

    with pytest.raises(ValidationError):
        asyncio.run(manager.import_monitor(config))


def test_import_monitor_raises_not_found_for_missing_auth_profile_name():
    manager, _ = _manager(api=_api_manager(auth_profile_service=_auth_profile_service(by_name=None)))
    config = HttpMonitorConfig(name="With Auth", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, auth_profile_name="Ghost")

    with pytest.raises(NotFoundError):
        asyncio.run(manager.import_monitor(config))


def test_import_monitor_requires_auth_profile_service_when_name_given():
    manager, _ = _manager()
    config = HttpMonitorConfig(name="With Auth", monitor_type=MonitorType.HTTP, url="https://example.com", check_interval=60, timeout=5, expected_status_code=200, auth_profile_name="Ghost")

    with pytest.raises(ValidationError):
        asyncio.run(manager.import_monitor(config))
