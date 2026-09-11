from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.shared_models.exceptions import NotFoundError
from tests.fake_model.fakes import FakeCollection

NOW = datetime.now(UTC)


class _HeartbeatCollection(FakeCollection):
    """FakeCollection does not apply `$inc`; receive_heartbeat relies on it to bump heartbeat_count."""

    async def update_one(self, query, update):
        for document in self.documents:
            if self._matches(document, query):
                document.update(update.get("$set", {}))
                for key, amount in update.get("$inc", {}).items():
                    document[key] = document.get(key, 0) + amount
                return SimpleNamespace(matched_count=1, modified_count=1)
        return SimpleNamespace(matched_count=0, modified_count=0)


_UNSET = object()


def _monitor_service(process_heartbeat=None):
    async def default_process_heartbeat(_monitor):
        return None

    return SimpleNamespace(process_heartbeat=process_heartbeat or default_process_heartbeat)


def _manager(monitor_service=_UNSET):
    collection = _HeartbeatCollection()
    engine = SimpleNamespace(database={Collections.HEARTBEAT_MONITORS: collection})
    manager = HeartbeatMonitorManager(engine, _monitor_service() if monitor_service is _UNSET else monitor_service)
    return manager, collection


def _create(manager, name="Nightly Backup", expected_heartbeat_interval=300, grace_period=60, created_by=None):
    return asyncio.run(manager.create_monitor(name, expected_heartbeat_interval, grace_period, created_by))


def _stored_id(collection):
    return str(collection.documents[0]["_id"])


def test_create_monitor_returns_token_and_persists_document():
    manager, collection = _manager()
    response = _create(manager, name="Backup Job", created_by="alice")

    assert response.heartbeat_token
    assert len(collection.documents) == 1
    document = collection.documents[0]
    assert document["name"] == "Backup Job"
    assert document["created_by"] == "alice"
    assert document["is_active"] is True
    assert document["status"] == MonitorStatus.UNKNOWN
    assert document["heartbeat_token_hash"] == hashlib.sha256(response.heartbeat_token.encode()).hexdigest()
    assert document["token_expires_at"] == document["last_token_rotated_at"] + timedelta(days=90)


def test_list_monitors_maps_response():
    manager, _ = _manager()
    _create(manager, name="First")
    _create(manager, name="Second")

    listed = asyncio.run(manager.list_monitors())
    assert {monitor.name for monitor in listed} == {"First", "Second"}
    assert listed[0].status == MonitorStatus.UNKNOWN.value
    assert listed[0].last_heartbeat_at is None


def test_get_monitor_returns_response():
    manager, collection = _manager()
    _create(manager, name="Job")
    monitor_id = _stored_id(collection)

    fetched = asyncio.run(manager.get_monitor(monitor_id))
    assert fetched.id == monitor_id
    assert fetched.name == "Job"


def test_get_monitor_raises_not_found_for_missing_or_invalid_id():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_monitor(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_monitor("not-a-valid-id"))


def test_update_monitor_changes_fields():
    manager, collection = _manager()
    _create(manager, name="Old Name", expected_heartbeat_interval=300, grace_period=60)
    monitor_id = _stored_id(collection)

    updated = asyncio.run(manager.update_monitor(monitor_id, name="New Name", expected_heartbeat_interval=120, grace_period=30, is_active=False))
    assert updated.name == "New Name"
    assert updated.expected_heartbeat_interval == 120
    assert updated.grace_period == 30
    assert updated.is_active is False


def test_update_monitor_raises_not_found_for_missing_monitor():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(str(ObjectId()), name="New Name"))


def test_update_monitor_partial_update_leaves_other_fields_untouched():
    manager, collection = _manager()
    _create(manager, name="Old Name", expected_heartbeat_interval=300, grace_period=60)
    monitor_id = _stored_id(collection)

    updated = asyncio.run(manager.update_monitor(monitor_id, is_active=False))
    assert updated.name == "Old Name"
    assert updated.expected_heartbeat_interval == 300
    assert updated.grace_period == 60
    assert updated.is_active is False


def test_update_monitor_partial_update_only_interval_leaves_is_active_untouched():
    manager, collection = _manager()
    _create(manager, name="Old Name", expected_heartbeat_interval=300, grace_period=60)
    monitor_id = _stored_id(collection)

    updated = asyncio.run(manager.update_monitor(monitor_id, expected_heartbeat_interval=120))
    assert updated.expected_heartbeat_interval == 120
    assert updated.is_active is True


def test_update_monitor_raises_not_found_when_monitor_disappears_after_update():
    class _DisappearingCollection(_HeartbeatCollection):
        async def update_one(self, query, update):
            result = await super().update_one(query, update)
            self.documents.clear()
            return result

    collection = _DisappearingCollection()
    engine = SimpleNamespace(database={Collections.HEARTBEAT_MONITORS: collection})
    manager = HeartbeatMonitorManager(engine, _monitor_service())
    asyncio.run(manager.create_monitor("Doomed", 300, 60))
    monitor_id = str(collection.documents[0]["_id"])

    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_monitor(monitor_id, name="New Name"))


def test_update_monitor_restarts_worker_when_scheduler_present(monkeypatch):
    stopped, started = [], []

    async def stop_worker(monitor_id):
        stopped.append(monitor_id)

    async def start_worker(monitor):
        started.append(monitor.id)

    fake_scheduler = SimpleNamespace(stop_worker=stop_worker, start_worker=start_worker)
    monkeypatch.setattr(scheduler_state, "scheduler", fake_scheduler)

    manager, collection = _manager()
    created = _create(manager)
    monitor_id = _stored_id(collection)
    asyncio.run(manager.receive_heartbeat(created.heartbeat_token))

    updated = asyncio.run(manager.update_monitor(monitor_id, is_active=True))
    assert updated.is_active is True
    assert stopped == [monitor_id]
    assert monitor_id in started


def test_update_monitor_skips_restart_when_deactivated_with_scheduler_present(monkeypatch):
    stopped, started = [], []

    async def stop_worker(monitor_id):
        stopped.append(monitor_id)

    async def start_worker(monitor):
        started.append(monitor.id)

    monkeypatch.setattr(scheduler_state, "scheduler", SimpleNamespace(stop_worker=stop_worker, start_worker=start_worker))

    manager, collection = _manager()
    created = _create(manager)
    monitor_id = _stored_id(collection)
    asyncio.run(manager.receive_heartbeat(created.heartbeat_token))
    started.clear()

    updated = asyncio.run(manager.update_monitor(monitor_id, is_active=False))
    assert updated.is_active is False
    assert stopped == [monitor_id]
    assert started == []


def test_delete_monitor_removes_document():
    manager, collection = _manager()
    _create(manager)
    monitor_id = _stored_id(collection)

    asyncio.run(manager.delete_monitor(monitor_id))
    assert collection.documents == []


def test_delete_monitor_raises_not_found_for_missing_or_invalid_id():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor("not-a-valid-id"))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_monitor(str(ObjectId())))


def test_regenerate_token_issues_new_token_and_updates_hash():
    manager, collection = _manager()
    first = _create(manager)
    monitor_id = _stored_id(collection)

    regenerated = asyncio.run(manager.regenerate_token(monitor_id))
    assert regenerated.heartbeat_token != first.heartbeat_token
    document = collection.documents[0]
    assert document["heartbeat_token_hash"] == hashlib.sha256(regenerated.heartbeat_token.encode()).hexdigest()


def test_regenerate_token_raises_not_found_for_missing_monitor():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.regenerate_token(str(ObjectId())))


def test_receive_heartbeat_updates_monitor_and_calls_monitor_service():
    calls = []

    async def process_heartbeat(monitor):
        calls.append(monitor.id)

    manager, collection = _manager(_monitor_service(process_heartbeat))
    created = _create(manager)

    response = asyncio.run(manager.receive_heartbeat(created.heartbeat_token))
    assert response.message == "Heartbeat received."
    assert response.expected_next_heartbeat_in == 300
    assert response.token_rotation_required is False
    document = collection.documents[0]
    assert document["heartbeat_count"] == 1
    assert document["last_heartbeat_at"] is not None
    assert len(calls) == 1


def test_receive_heartbeat_raises_not_found_for_unknown_token():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.receive_heartbeat("unknown-token"))


def test_receive_heartbeat_raises_not_found_for_inactive_monitor():
    manager, collection = _manager()
    created = _create(manager)
    collection.documents[0]["is_active"] = False

    with pytest.raises(NotFoundError):
        asyncio.run(manager.receive_heartbeat(created.heartbeat_token))


def test_receive_heartbeat_raises_not_found_for_expired_token():
    manager, collection = _manager()
    created = _create(manager)
    collection.documents[0]["token_expires_at"] = NOW - timedelta(days=1)

    with pytest.raises(NotFoundError):
        asyncio.run(manager.receive_heartbeat(created.heartbeat_token))


def test_update_monitoring_result_updates_status_for_valid_id():
    manager, collection = _manager()
    _create(manager)
    monitor_id = _stored_id(collection)

    updated = asyncio.run(manager.update_monitoring_result(monitor_id, MonitorStatus.UP, 200, 42, NOW))
    assert updated is True
    assert collection.documents[0]["status"] == MonitorStatus.UP


def test_update_monitoring_result_returns_false_for_invalid_id():
    manager, _ = _manager()
    updated = asyncio.run(manager.update_monitoring_result("not-a-valid-id", MonitorStatus.UP, 200, 42, NOW))
    assert updated is False


def test_receive_heartbeat_starts_worker_when_scheduler_present(monkeypatch):
    started = []

    async def start_worker(monitor):
        started.append(monitor.id)

    monkeypatch.setattr(scheduler_state, "scheduler", SimpleNamespace(start_worker=start_worker))

    manager, _ = _manager()
    created = _create(manager)
    asyncio.run(manager.receive_heartbeat(created.heartbeat_token))
    assert len(started) == 1


def test_get_monitor_service_falls_back_to_scheduler(monkeypatch):
    calls = []

    async def process_heartbeat(monitor):
        calls.append(monitor.id)

    async def start_worker(_monitor):
        return None

    fake_scheduler = SimpleNamespace(monitor_service=SimpleNamespace(process_heartbeat=process_heartbeat), start_worker=start_worker)
    monkeypatch.setattr(scheduler_state, "scheduler", fake_scheduler)

    manager, _ = _manager(monitor_service=None)
    created = _create(manager)
    asyncio.run(manager.receive_heartbeat(created.heartbeat_token))
    assert len(calls) == 1


def test_get_monitor_service_raises_runtime_error_without_service_or_scheduler():
    manager, _ = _manager(monitor_service=None)
    created = _create(manager)
    with pytest.raises(RuntimeError):
        asyncio.run(manager.receive_heartbeat(created.heartbeat_token))
