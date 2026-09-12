from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.constants.constant import Collections
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


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
