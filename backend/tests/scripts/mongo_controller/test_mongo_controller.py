from __future__ import annotations

import asyncio

import pytest
from pymongo import ASCENDING, DESCENDING

from orion.constants.constant import Collections
from orion.services.mongo_manager import mongo_controller
from orion.services.mongo_manager.mongo_controller import DatabaseManager
from tests.scripts.mongo_controller.fakes import FakeConnectedEngine, FakeIndexEngine
from tests.scripts.mongo_controller.helpers import _manager_with_engine


def test_get_engine_raises_before_connect():
    manager = DatabaseManager()

    with pytest.raises(RuntimeError):
        manager.get_engine()


def test_engine_property_raises_when_uninitialized():
    manager = DatabaseManager()

    with pytest.raises(RuntimeError):
        _ = manager.engine


def test_get_engine_returns_engine_once_assigned():
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    assert manager.get_engine() is engine
    assert manager.engine is engine


def test_create_monitor_result_indexes_creates_expected_indexes(monkeypatch):
    monkeypatch.setenv("MONITOR_RESULT_RETENTION_DAYS", "30")
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_monitor_result_indexes())

    collection = engine.database.collections[Collections.MONITOR_RESULTS]
    assert [args for args, _kwargs in collection.created[:5]] == [
        ([("monitor_id", ASCENDING)],),
        ([("checked_at", DESCENDING)],),
        ([("monitor_id", ASCENDING), ("checked_at", DESCENDING)],),
        ([("monitor_id", ASCENDING), ("is_slow", ASCENDING)],),
        ([("monitor_id", ASCENDING), ("success", ASCENDING)],),
    ]
    ttl_args, ttl_kwargs = collection.created[5]
    assert ttl_args == ([("checked_at", ASCENDING)],)
    assert ttl_kwargs == {"name": "monitor_results_ttl", "expireAfterSeconds": 30 * 24 * 60 * 60}
    assert collection.dropped == []


def test_create_monitor_result_indexes_retries_ttl_index_after_operation_failure(monkeypatch):
    monkeypatch.setenv("MONITOR_RESULT_RETENTION_DAYS", "180")
    engine = FakeIndexEngine(fail_once_names=["monitor_results_ttl"])
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_monitor_result_indexes())

    collection = engine.database.collections[Collections.MONITOR_RESULTS]
    assert collection.dropped == ["monitor_results_ttl"]
    assert collection.created[-1][1] == {"name": "monitor_results_ttl", "expireAfterSeconds": 180 * 24 * 60 * 60}


def test_create_incident_indexes():
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_incident_indexes())

    collection = engine.database.collections[Collections.INCIDENTS]
    assert [args for args, _kwargs in collection.created] == [
        ([("monitor_id", ASCENDING), ("resolved_at", ASCENDING)],),
        ([("monitor_id", ASCENDING), ("monitor_type", ASCENDING), ("resolved_at", ASCENDING)],),
        ([("started_at", DESCENDING)],),
        ([("is_resolved", ASCENDING)],),
    ]


def test_create_heartbeat_indexes():
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_heartbeat_indexes())

    collection = engine.database.collections[Collections.HEARTBEAT_MONITORS]
    assert collection.created == [
        (("heartbeat_token_hash",), {"unique": True}),
        (("is_active",), {}),
        (("name",), {}),
    ]


def test_create_status_page_indexes():
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_status_page_indexes())

    collection = engine.database.collections[Collections.STATUS_PAGES]
    assert collection.created == [
        (("slug",), {"unique": True}),
        (("created_at",), {}),
    ]


def test_create_slack_integration_indexes():
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_slack_integration_indexes())

    collection = engine.database.collections[Collections.SLACK_INTEGRATIONS]
    assert collection.created == [
        (("name_key",), {"unique": True}),
        (("monitor_ids",), {}),
        (("created_at",), {}),
    ]


def test_create_email_integration_indexes():
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_email_integration_indexes())

    collection = engine.database.collections[Collections.EMAIL_INTEGRATIONS]
    assert collection.created == [
        (("name_key",), {"unique": True}),
        (("monitor_ids",), {}),
        (("created_at",), {}),
    ]


def test_disconnect_closes_client_and_clears_engine():
    engine = FakeConnectedEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager.disconnect())

    assert engine.client.closed is True
    assert manager._engine is None


def test_disconnect_is_noop_when_engine_is_none():
    manager = DatabaseManager()

    asyncio.run(manager.disconnect())

    assert manager._engine is None


def test_module_get_engine_delegates_to_db_manager(monkeypatch):
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)
    monkeypatch.setattr(mongo_controller, "db_manager", manager)

    result = asyncio.run(mongo_controller.get_engine())

    assert result is engine


def test_create_indexes_runs_every_helper(monkeypatch):
    monkeypatch.setenv("MONITOR_RESULT_RETENTION_DAYS", "10")
    engine = FakeIndexEngine()
    manager = _manager_with_engine(engine)

    asyncio.run(manager._create_indexes())

    assert set(engine.database.collections) == {
        Collections.MONITOR_RESULTS,
        Collections.INCIDENTS,
        Collections.HEARTBEAT_MONITORS,
        Collections.STATUS_PAGES,
        Collections.SLACK_INTEGRATIONS,
        Collections.EMAIL_INTEGRATIONS,
    }
    assert len(engine.database.collections[Collections.MONITOR_RESULTS].created) == 6
