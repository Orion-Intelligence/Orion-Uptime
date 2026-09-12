from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId

from orion.services.mongo_manager.shared_model.db_api_monitor_model import UpdateApiMonitorRequest
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.shared_models.exceptions import ConflictError, NotFoundError, ValidationError
from tests.scripts.api_monitor_manager.fixtures import _allow_private_targets
from tests.scripts.api_monitor_manager.helpers import NOW, _auth_profile_service, _create, _manager


def test_create_monitor_success_persists_and_returns_response():
    manager, collection = _manager()
    created = _create(manager, name="API", url="http://example.com/health", method="POST", headers={"X-Test": "1"}, request_body={"a": 1}, expected_json={"ok": True}, expected_headers={"X-Res": "2"}, expected_content_type="application/json", created_by="user-1")

    assert created.id
    assert created.name == "API"
    assert created.url == "http://example.com/health"
    assert created.method == "POST"
    assert created.headers == {"X-Test": "1"}
    assert created.request_body == {"a": 1}
    assert created.expected_json == {"ok": True}
    assert created.expected_headers == {"X-Res": "2"}
    assert created.expected_content_type == "application/json"
    assert created.created_by == "user-1"
    assert created.status.value == "unknown"
    assert created.is_active is True
    assert created.last_checked_at is None
    assert created.last_status_code is None
    assert collection.documents[0]["_id"] == ObjectId(created.id)


def test_create_monitor_rejects_duplicate_name():
    manager, _ = _manager()
    _create(manager, name="Dup", url="http://one.example.com")

    with pytest.raises(ConflictError):
        _create(manager, name="Dup", url="http://two.example.com")


def test_create_monitor_rejects_duplicate_url():
    manager, _ = _manager()
    _create(manager, name="First", url="http://dup.example.com")

    with pytest.raises(ConflictError):
        _create(manager, name="Second", url="http://dup.example.com")


def test_create_monitor_with_valid_auth_profile():
    manager, _ = _manager(auth_profile_service=_auth_profile_service(["p1"]))
    created = _create(manager, auth_profile_id="p1")
    assert created.auth_profile_id == "p1"


def test_create_monitor_rejects_unknown_auth_profile():
    manager, _ = _manager(auth_profile_service=_auth_profile_service(["p1"]))
    with pytest.raises(NotFoundError):
        _create(manager, auth_profile_id="ghost")


def test_create_monitor_without_auth_profile_service_rejects_auth_profile_id():
    manager, _ = _manager(auth_profile_service=None)
    with pytest.raises(NotFoundError):
        _create(manager, auth_profile_id="p1")


def test_create_monitor_rejects_invalid_url_scheme():
    manager, _ = _manager()
    with pytest.raises(ValidationError):
        _create(manager, url="ftp://example.com")


def test_list_monitors_and_list_monitor_models():
    manager, _ = _manager()
    _create(manager, name="A", url="http://a.example.com")
    _create(manager, name="B", url="http://b.example.com")

    listed = asyncio.run(manager.list_monitors())
    models = asyncio.run(manager.list_monitor_models())

    assert {monitor.name for monitor in listed} == {"A", "B"}
    assert {model.name for model in models} == {"A", "B"}


def test_get_monitor_success_and_not_found():
    manager, _ = _manager()
    created = _create(manager)

    fetched = asyncio.run(manager.get_monitor(created.id))
    assert fetched.id == created.id

    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_monitor("not-a-valid-id"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_monitor(str(ObjectId())))


def test_update_monitor_no_changes_returns_same_response():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest()))
    assert updated.model_dump() == created.model_dump()


def test_update_monitor_skips_when_values_unchanged():
    manager, _ = _manager()
    created = _create(manager, timeout=10)

    updated = asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest(timeout=10)))
    assert updated.model_dump() == created.model_dump()


def test_update_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(str(ObjectId()), UpdateApiMonitorRequest(name="New")))


def test_update_monitor_changes_simple_fields():
    manager, _ = _manager()
    created = _create(manager, check_interval=60, timeout=10)

    updated = asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest(check_interval=120, timeout=20, method="POST", is_active=False)))

    assert updated.check_interval == 120
    assert updated.timeout == 20
    assert updated.method == "POST"
    assert updated.is_active is False


def test_update_monitor_rejects_duplicate_name():
    manager, _ = _manager()
    _create(manager, name="First", url="http://first.example.com")
    second = _create(manager, name="Second", url="http://second.example.com")

    with pytest.raises(ConflictError):
        asyncio.run(manager.update_monitor(second.id, UpdateApiMonitorRequest(name="First")))


def test_update_monitor_changes_url_when_not_duplicate():
    manager, _ = _manager()
    created = _create(manager, url="http://old.example.com")

    updated = asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest(url="http://new.example.com")))
    assert updated.url == "http://new.example.com"


def test_update_monitor_rejects_duplicate_url():
    manager, _ = _manager()
    _create(manager, name="First", url="http://taken.example.com")
    second = _create(manager, name="Second", url="http://free.example.com")

    with pytest.raises(ConflictError):
        asyncio.run(manager.update_monitor(second.id, UpdateApiMonitorRequest(url="http://taken.example.com")))


def test_update_monitor_rejects_invalid_url_scheme():
    manager, _ = _manager()
    created = _create(manager)

    with pytest.raises(ValidationError):
        asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest(url="ftp://example.com")))


def test_update_monitor_sets_valid_auth_profile():
    manager, _ = _manager(auth_profile_service=_auth_profile_service(["p1"]))
    created = _create(manager)

    updated = asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest(auth_profile_id="p1")))
    assert updated.auth_profile_id == "p1"


def test_update_monitor_rejects_unknown_auth_profile():
    manager, _ = _manager(auth_profile_service=_auth_profile_service(["p1"]))
    created = _create(manager)

    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(created.id, UpdateApiMonitorRequest(auth_profile_id="ghost")))


def test_delete_monitor_removes_document():
    manager, collection = _manager()
    created = _create(manager)

    asyncio.run(manager.delete_monitor(created.id))
    assert collection.documents == []


def test_delete_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor("not-a-valid-id"))


def test_update_monitoring_result_success_and_invalid_id():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitoring_result(created.id, MonitorStatus.UP, 200, 42, NOW))
    assert updated is True

    not_updated = asyncio.run(manager.update_monitoring_result("not-a-valid-id", MonitorStatus.UP, 200, 42, NOW))
    assert not_updated is False


def test_validate_auth_profile_none_is_noop():
    manager, _ = _manager()
    asyncio.run(manager._validate_auth_profile(None))
