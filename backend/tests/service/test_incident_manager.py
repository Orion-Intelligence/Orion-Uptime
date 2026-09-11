from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.incident_manager.incident_manager import IncidentManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from tests.fake_model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.INCIDENTS: collection})
    manager = IncidentManager(engine)
    return manager, collection


def test_open_incident_creates_new_incident_when_none_active():
    manager, collection = _manager()

    incident = asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Connection refused", status_code=None))

    assert incident.id is not None
    assert incident.is_resolved is False
    assert incident.resolved_at is None
    assert len(collection.documents) == 1
    assert collection.documents[0]["monitor_id"] == "m1"


def test_open_incident_returns_existing_active_incident_without_duplicating():
    manager, collection = _manager()

    first = asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Connection refused"))
    second = asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Different reason", status_code=503))

    assert second.id == first.id
    assert second.reason == first.reason
    assert len(collection.documents) == 1


def test_resolve_incident_marks_active_incident_resolved():
    manager, collection = _manager()
    incident = asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Timeout"))

    resolved = asyncio.run(manager.resolve_incident("m1", MonitorType.HTTP))

    assert resolved is not None
    assert resolved.id == incident.id
    assert resolved.is_resolved is True
    assert resolved.resolved_at is not None
    assert collection.documents[0]["is_resolved"] is True


def test_resolve_incident_returns_none_when_no_active_incident():
    manager, _ = _manager()
    assert asyncio.run(manager.resolve_incident("ghost", MonitorType.HTTP)) is None


def test_resolve_incident_returns_none_when_incident_id_is_invalid():
    manager, collection = _manager()
    collection.documents.append({"_id": "not-a-valid-object-id", "monitor_id": "m1", "monitor_type": MonitorType.HTTP, "started_at": NOW, "resolved_at": None, "is_resolved": False, "reason": "Timeout", "status_code": None})

    assert asyncio.run(manager.resolve_incident("m1", MonitorType.HTTP)) is None


def test_get_active_incident_returns_none_when_absent():
    manager, _ = _manager()
    assert asyncio.run(manager.get_active_incident("m1", MonitorType.HTTP)) is None


def test_get_active_incident_returns_model_when_present():
    manager, _ = _manager()
    created = asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Timeout", status_code=504))

    active = asyncio.run(manager.get_active_incident("m1", MonitorType.HTTP))

    assert active.id == created.id
    assert active.status_code == 504


def test_count_open_counts_only_unresolved():
    manager, _ = _manager()
    asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Timeout"))
    asyncio.run(manager.open_incident("m2", MonitorType.HTTP, "Timeout"))
    incident = asyncio.run(manager.open_incident("m3", MonitorType.HTTP, "Timeout"))
    asyncio.run(manager.resolve_incident("m3", MonitorType.HTTP))

    assert asyncio.run(manager.count_open()) == 2
    assert incident.reason == "Timeout"


def test_get_recent_returns_incidents_up_to_limit():
    manager, _ = _manager()
    for index in range(3):
        asyncio.run(manager.open_incident(f"m{index}", MonitorType.HTTP, "Timeout"))

    all_recent = asyncio.run(manager.get_recent())
    limited = asyncio.run(manager.get_recent(limit=2))

    assert len(all_recent) == 3
    assert len(limited) == 2


def test_get_for_monitors_groups_by_monitor_and_handles_empty_input():
    manager, _ = _manager()
    asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Timeout"))
    asyncio.run(manager.open_incident("m2", MonitorType.HTTP, "Connection refused"))

    grouped = asyncio.run(manager.get_for_monitors(["m1", "m2", "ghost"]))
    empty = asyncio.run(manager.get_for_monitors([]))

    assert set(grouped.keys()) == {"m1", "m2"}
    assert grouped["m1"][0].reason == "Timeout"
    assert empty == {}


def test_delete_for_monitor_removes_only_matching_documents():
    manager, collection = _manager()
    asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Timeout"))
    asyncio.run(manager.open_incident("m2", MonitorType.HTTP, "Timeout"))

    asyncio.run(manager.delete_for_monitor("m1"))

    assert len(collection.documents) == 1
    assert collection.documents[0]["monitor_id"] == "m2"


def test_resolve_incident_returns_none_when_update_reports_no_match():
    manager, collection = _manager()
    asyncio.run(manager.open_incident("m1", MonitorType.HTTP, "Timeout"))

    async def update_one_no_match(_query, _update):
        return SimpleNamespace(matched_count=0, modified_count=0)

    collection.update_one = update_one_no_match

    resolved = asyncio.run(manager.resolve_incident("m1", MonitorType.HTTP))

    assert resolved is None
