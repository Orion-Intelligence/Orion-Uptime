from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.constants.constant import Collections
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)

_UNSET = object()


def _monitor_service(process_heartbeat=None):
    async def default_process_heartbeat(_monitor):
        return None

    return SimpleNamespace(process_heartbeat=process_heartbeat or default_process_heartbeat)


def _manager(monitor_service=_UNSET):
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.HEARTBEAT_MONITORS: collection})
    manager = HeartbeatMonitorManager(engine, _monitor_service() if monitor_service is _UNSET else monitor_service)
    return manager, collection


def _create(manager, name="Nightly Backup", expected_heartbeat_interval=300, grace_period=60, created_by=None):
    return asyncio.run(manager.create_monitor(name, expected_heartbeat_interval, grace_period, created_by))


def _stored_id(collection):
    return str(collection.documents[0]["_id"])
