from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId

from orion.api.interactive.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.shared_models.exceptions import NotFoundError
from tests.scripts.ping_monitor_manager.fixtures import _allow_private_targets
from tests.scripts.ping_monitor_manager.helpers import NOW, _create, _manager


def test_create_monitor_success_persists_and_returns_response():
    manager, collection = _manager()
    created = _create(manager, name="Host")

    assert created.id
    assert created.name == "Host"
    assert created.host == "example.com"
    assert created.status.value == "unknown"
    assert created.is_active is True
    assert collection.documents[0]["_id"] == ObjectId(created.id)


def test_create_monitor_normalizes_host():
    manager, _ = _manager()
    created = _create(manager, host="HTTP://Example.COM:8080/")
    assert created.host == "example.com"


def test_create_monitor_with_created_by():
    manager, _ = _manager()
    created = _create(manager, created_by="user-1")
    assert created.created_by == "user-1"


def test_list_monitors_and_list_monitor_models():
    manager, _ = _manager()
    _create(manager, name="A", host="a.example.com")
    _create(manager, name="B", host="b.example.com")

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

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None))
    assert updated.model_dump(exclude={"updated_at"}) == created.model_dump(exclude={"updated_at"})


def test_update_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(str(ObjectId()), "New", None, None, None, None, None))


def test_update_monitor_changes_simple_fields():
    manager, _ = _manager()
    created = _create(manager, check_interval=60, timeout=10)

    updated = asyncio.run(manager.update_monitor(created.id, "New Name", None, 120, 20, None, False))

    assert updated.name == "New Name"
    assert updated.check_interval == 120
    assert updated.timeout == 20
    assert updated.is_active is False


def test_update_monitor_changes_host():
    manager, _ = _manager()
    created = _create(manager, host="old.example.com")

    updated = asyncio.run(manager.update_monitor(created.id, None, "HTTPS://New.Example.com/", None, None, None, None))
    assert updated.host == "new.example.com"


def test_update_monitor_clears_expected_response_time_ms_when_explicitly_set():
    manager, _ = _manager()
    created = _create(manager, expected_response_time_ms=500)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, expected_response_time_ms_set=True))
    assert updated.expected_response_time_ms is None


def test_update_monitor_sets_expected_response_time_ms():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, 250, None))
    assert updated.expected_response_time_ms == 250


def test_delete_monitor_removes_document():
    manager, collection = _manager()
    created = _create(manager)

    asyncio.run(manager.delete_monitor(created.id))
    assert collection.documents == []


def test_delete_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor(str(ObjectId())))


def test_delete_monitor_invalid_id_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor("not-a-valid-id"))


def test_update_monitoring_result_success_and_invalid_id():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitoring_result(created.id, MonitorStatus.UP, None, 42, NOW))
    assert updated is True

    not_updated = asyncio.run(manager.update_monitoring_result("not-a-valid-id", MonitorStatus.UP, None, 42, NOW))
    assert not_updated is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Example.com", "example.com"),
        ("HTTP://Example.com:8080/", "example.com"),
        ("https://Example.com/path", "example.com"),
        ("  Example.com  ", "example.com"),
        ("Example.com:9000/", "example.com"),
        ("Example.com/", "example.com"),
        ("::1", "::1"),
        ("http:///no-host-path", "http"),
    ],
)
def test_normalize_host_variants(raw, expected):
    assert PingMonitorManager._normalize_host(raw) == expected
