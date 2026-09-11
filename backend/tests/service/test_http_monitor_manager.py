from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.shared_models.exceptions import ConflictError, NotFoundError
from tests.fake_model.fakes import FakeCollection

NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _allow_private_targets(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "true")


class RegexCollection(FakeCollection):
    """Adds $regex support to count_documents so _unique_name suffixing can be exercised."""

    async def count_documents(self, query=None):
        query = query or {}

        def matches(document):
            for key, condition in query.items():
                value = document.get(key)
                if isinstance(condition, dict) and "$regex" in condition:
                    if not re.match(condition["$regex"], value or ""):
                        return False
                elif value != condition:
                    return False
            return True

        return sum(1 for document in self.documents if matches(document))


def _auth_profile_service(valid_ids=None):
    valid_ids = valid_ids or []

    async def get_profile_model(profile_id):
        return SimpleNamespace(id=profile_id) if profile_id in valid_ids else None

    return SimpleNamespace(get_profile_model=get_profile_model)


def _manager(*, collection=None, auth_profile_service=None):
    collection = collection if collection is not None else FakeCollection()
    engine = SimpleNamespace(database={Collections.HTTP_MONITORS: collection})
    manager = HttpMonitorManager(engine, auth_profile_service)
    return manager, collection


def _create(manager, *, name="Site", url="http://example.com", check_interval=60, timeout=10, expected_status_code=200, expected_response_time_ms=None, auth_profile_id=None):
    return asyncio.run(manager.create_monitor(name, url, check_interval, timeout, expected_status_code, expected_response_time_ms, auth_profile_id))


def test_create_monitor_success_persists_and_returns_response():
    manager, collection = _manager()
    created = _create(manager, name="Site")

    assert created.id
    assert created.name == "Site"
    assert created.url == "http://example.com"
    assert created.status.value == "unknown"
    assert collection.documents[0]["_id"] == ObjectId(created.id)


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


def test_create_monitor_generates_unique_name_suffix():
    manager, _ = _manager(collection=RegexCollection())
    first = _create(manager, name="Site", url="http://one.example.com")
    second = _create(manager, name="Site", url="http://two.example.com")

    assert first.name == "Site"
    assert second.name == "Site 1"


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

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None))
    assert updated.model_dump() == created.model_dump()


def test_update_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(str(ObjectId()), "New", None, None, None, None, None))


def test_update_monitor_changes_simple_fields():
    manager, _ = _manager()
    created = _create(manager, check_interval=60, timeout=10, expected_status_code=200)

    updated = asyncio.run(manager.update_monitor(created.id, None, None,120, 20, 201, None, is_active=False))

    assert updated.check_interval == 120
    assert updated.timeout == 20
    assert updated.expected_status_code == 201
    assert updated.is_active is False


def test_update_monitor_renames_with_unique_suffix():
    manager, _ = _manager(collection=RegexCollection())
    _create(manager, name="Other", url="http://other.example.com")
    created = _create(manager, name="Site", url="http://site.example.com")

    updated = asyncio.run(manager.update_monitor(created.id, "Other", None, None, None, None, None))
    assert updated.name == "Other 1"


def test_update_monitor_changes_url_when_not_duplicate():
    manager, _ = _manager()
    created = _create(manager, url="http://old.example.com")

    updated = asyncio.run(manager.update_monitor(created.id, None, "http://new.example.com", None, None, None, None))
    assert updated.url == "http://new.example.com"


def test_update_monitor_rejects_duplicate_url():
    manager, _ = _manager()
    _create(manager, name="First", url="http://taken.example.com")
    second = _create(manager, name="Second", url="http://free.example.com")

    with pytest.raises(ConflictError):
        asyncio.run(manager.update_monitor(second.id, None, "http://taken.example.com", None, None, None, None))


def test_update_monitor_clears_expected_response_time_ms_when_explicitly_set():
    manager, _ = _manager()
    created = _create(manager, expected_response_time_ms=500)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, expected_response_time_ms_set=True))
    assert updated.expected_response_time_ms is None


def test_update_monitor_sets_valid_auth_profile():
    manager, _ = _manager(auth_profile_service=_auth_profile_service(["p1"]))
    created = _create(manager)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, auth_profile_id="p1", auth_profile_id_set=True))
    assert updated.auth_profile_id == "p1"


def test_update_monitor_rejects_unknown_auth_profile():
    manager, _ = _manager(auth_profile_service=_auth_profile_service(["p1"]))
    created = _create(manager)

    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, auth_profile_id="ghost", auth_profile_id_set=True))


def test_delete_monitor_removes_document():
    manager, collection = _manager()
    created = _create(manager)

    asyncio.run(manager.delete_monitor(created.id))
    assert collection.documents == []


def test_delete_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor(str(ObjectId())))


def test_update_monitoring_result_success_and_invalid_id():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitoring_result(created.id, MonitorStatus.UP, 200, 42, NOW))
    assert updated is True

    not_updated = asyncio.run(manager.update_monitoring_result("not-a-valid-id", MonitorStatus.UP, 200, 42, NOW))
    assert not_updated is False
