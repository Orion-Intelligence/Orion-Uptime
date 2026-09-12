from __future__ import annotations

import asyncio

import pytest
from bson import ObjectId

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionFeederStatus
from orion.shared_models.exceptions import ConflictError, NotFoundError, ValidationError
from tests.scripts.orion_script_monitor_manager.fixtures import _allow_private_targets
from tests.scripts.orion_script_monitor_manager.helpers import NOW, _auth_profile_service, _create, _manager, _profile


def test_create_monitor_success_persists_and_returns_response():
    manager, collection = _manager()
    created = _create(manager, name="Site", created_by="alice")

    assert created.id
    assert created.name == "Site"
    assert created.url == "http://example.com"
    assert created.status.value == "unknown"
    assert created.created_by == "alice"
    assert created.feeders == []
    assert collection.documents[0]["_id"] == ObjectId(created.id)


def test_create_monitor_normalizes_url():
    manager, _ = _manager()
    created = _create(manager, url="  http://example.com/path/  ")
    assert created.url == "http://example.com/path"


def test_create_monitor_rejects_duplicate_url():
    manager, _ = _manager()
    _create(manager, name="First", url="http://dup.example.com")

    with pytest.raises(ConflictError):
        _create(manager, name="Second", url="http://dup.example.com")


def test_create_monitor_with_matching_auth_profile_succeeds():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))

    created = _create(manager, auth_profile_id="p1")
    assert created.auth_profile_id == "p1"


def test_create_monitor_missing_auth_profile_raises_not_found():
    manager, _ = _manager(auth_profile_service=_auth_profile_service([]))

    with pytest.raises(NotFoundError):
        _create(manager, auth_profile_id="ghost")


def test_create_monitor_mismatched_auth_profile_raises_validation_error():
    profile = _profile("p1", "http://other.example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))

    with pytest.raises(ValidationError):
        _create(manager, auth_profile_id="p1")


def test_create_monitor_without_profile_id_requires_matching_profile_in_list():
    profile = _profile("p1", "http://other.example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))

    with pytest.raises(ValidationError):
        _create(manager)


def test_create_monitor_without_profile_id_succeeds_when_list_has_match():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))

    created = _create(manager)
    assert created.auth_profile_id is None


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


def test_update_monitor_no_changes_updates_timestamp_only():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None))
    assert updated.name == created.name
    assert updated.url == created.url
    assert updated.updated_at >= created.updated_at


def test_update_monitor_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(str(ObjectId()), "New", None, None, None, None, None))


def test_update_monitor_changes_simple_fields():
    manager, _ = _manager()
    created = _create(manager, check_interval=60, timeout=10, expected_response_time_ms=None)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, 120, 20, 500, False))

    assert updated.check_interval == 120
    assert updated.timeout == 20
    assert updated.expected_response_time_ms == 500
    assert updated.is_active is False


def test_update_monitor_clears_expected_response_time_ms_when_explicitly_set():
    manager, _ = _manager()
    created = _create(manager, expected_response_time_ms=500)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, expected_response_time_ms_set=True))
    assert updated.expected_response_time_ms is None


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


def test_update_monitor_url_change_revalidates_profile_and_rejects_mismatch():
    profile = _profile("p-old", "http://old.example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
    created = _create(manager, url="http://old.example.com", auth_profile_id="p-old")

    with pytest.raises(ValidationError):
        asyncio.run(manager.update_monitor(created.id, None, "http://new.example.com", None, None, None, None))


def test_update_monitor_url_and_profile_change_together_succeeds():
    profile_old = _profile("p-old", "http://old.example.com/login")
    profile_new = _profile("p-new", "http://new.example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile_old, profile_new]))
    created = _create(manager, url="http://old.example.com", auth_profile_id="p-old")

    updated = asyncio.run(manager.update_monitor(created.id, None, "http://new.example.com", None, None, None, None, auth_profile_id="p-new", auth_profile_id_set=True))
    assert updated.url == "http://new.example.com"
    assert updated.auth_profile_id == "p-new"


def test_update_monitor_sets_auth_profile_id():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
    created = _create(manager)

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, auth_profile_id="p1", auth_profile_id_set=True))
    assert updated.auth_profile_id == "p1"


def test_update_monitor_clears_auth_profile_id_when_matching_profile_exists():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
    created = _create(manager, auth_profile_id="p1")

    updated = asyncio.run(manager.update_monitor(created.id, None, None, None, None, None, None, auth_profile_id=None, auth_profile_id_set=True))
    assert updated.auth_profile_id is None


def test_update_monitor_rejects_unknown_auth_profile():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
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


def test_delete_monitor_invalid_id_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor("not-a-valid-id"))


def test_update_monitoring_result_success_and_invalid_id():
    manager, _ = _manager()
    created = _create(manager)

    updated = asyncio.run(manager.update_monitoring_result(created.id, MonitorStatus.UP, 200, 42, NOW))
    assert updated is True

    not_updated = asyncio.run(manager.update_monitoring_result("not-a-valid-id", MonitorStatus.UP, 200, 42, NOW))
    assert not_updated is False


def test_store_feeders_success_and_invalid_id():
    manager, collection = _manager()
    created = _create(manager)
    feeders = [OrionFeederStatus(key="f1", name="Feeder One", status=MonitorStatus.UP)]

    updated = asyncio.run(manager.store_feeders(created.id, feeders))
    assert updated is True
    assert collection.documents[0]["feeders"][0]["key"] == "f1"

    not_updated = asyncio.run(manager.store_feeders("not-a-valid-id", feeders))
    assert not_updated is False


def test_validated_url_strips_whitespace_and_trailing_slash():
    manager, _ = _manager()
    result = asyncio.run(manager._validated_url("  http://example.com/path/  "))
    assert result == "http://example.com/path"


def test_validate_profile_returns_none_when_service_missing():
    manager, _ = _manager(auth_profile_service=None)
    assert asyncio.run(manager._validate_profile("http://example.com", "whatever")) is None


def test_validate_profile_with_id_missing_raises_not_found():
    manager, _ = _manager(auth_profile_service=_auth_profile_service([]))
    with pytest.raises(NotFoundError):
        asyncio.run(manager._validate_profile("http://example.com", "ghost"))


def test_validate_profile_with_id_mismatch_raises_validation_error():
    profile = _profile("p1", "http://other.example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
    with pytest.raises(ValidationError):
        asyncio.run(manager._validate_profile("http://example.com", "p1"))


def test_validate_profile_with_id_match_returns_none():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
    assert asyncio.run(manager._validate_profile("http://example.com", "p1")) is None


def test_validate_profile_without_id_no_match_raises_validation_error():
    manager, _ = _manager(auth_profile_service=_auth_profile_service([]))
    with pytest.raises(ValidationError):
        asyncio.run(manager._validate_profile("http://example.com", None))


def test_validate_profile_without_id_match_returns_none():
    profile = _profile("p1", "http://example.com/login")
    manager, _ = _manager(auth_profile_service=_auth_profile_service([profile]))
    assert asyncio.run(manager._validate_profile("http://example.com", None)) is None
