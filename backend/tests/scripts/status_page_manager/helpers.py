from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.status_page_manager.status_page_manager import StatusPageManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_insight_model import MonitorOverviewResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_status_page_model import CreateStatusPageRequest
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _async_return(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _overview(monitor_id, *, monitor_type="HTTP", status=MonitorStatus.UP, is_active=True):
    return MonitorOverviewResponse(id=monitor_id, name=f"Monitor {monitor_id}", monitor_type=monitor_type, status=status, is_active=is_active, created_at=NOW, last_checked_at=NOW, uptime_percentage=None, current_uptime_seconds=0, latest_downtime_seconds=0, measurement_seconds=0, downtime_seconds=0, snapshot_at=NOW)


def _dashboard(overviews, response_time=None, incidents=None):
    async def get_monitor_overviews():
        return overviews

    async def get_public_uptime_breakdown(ids, now):
        return {}

    async def get_public_response_time(monitor_id, now):
        return response_time or {"points": [], "metrics": []}

    async def get_for_monitors(ids):
        return incidents or {}

    return SimpleNamespace(
        get_monitor_overviews=get_monitor_overviews,
        monitor_result_service=SimpleNamespace(get_public_uptime_breakdown=get_public_uptime_breakdown, get_public_response_time=get_public_response_time),
        incident_service=SimpleNamespace(get_for_monitors=get_for_monitors),
    )


def _manager(monitors=None, overviews=None, response_time=None, incidents=None):
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.STATUS_PAGES: collection})
    monitor_service = SimpleNamespace(list_monitors=_async_return(monitors or []))
    return StatusPageManager(engine, monitor_service, _dashboard(overviews or [], response_time, incidents)), collection


def _create(manager, name="Public", description="", monitor_ids=None):
    return asyncio.run(manager.create_page(CreateStatusPageRequest(name=name, description=description, monitor_ids=monitor_ids or [])))
