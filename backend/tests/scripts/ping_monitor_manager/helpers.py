from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from orion.constants.constant import Collections
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _manager(*, collection=None):
    collection = collection if collection is not None else FakeCollection()
    engine = SimpleNamespace(database={Collections.PING_MONITORS: collection})
    manager = PingMonitorManager(engine)
    return manager, collection


def _create(manager, *, name="Host", host="example.com", check_interval=60, timeout=10, expected_response_time_ms=None, created_by=None):
    return asyncio.run(manager.create_monitor(name, host, check_interval, timeout, expected_response_time_ms, created_by))
