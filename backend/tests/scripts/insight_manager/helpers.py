from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.insight_manager.insight_manager import DashboardManager
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType

NOW = datetime.now(UTC)


def _monitor(monitor_id, *, name="Monitor", monitor_type=MonitorType.HTTP, status=MonitorStatus.UP, is_active=True, created_at=NOW, last_checked_at=NOW, updated_at=NOW):
    return SimpleNamespace(id=monitor_id, name=name, monitor_type=monitor_type, status=status, is_active=is_active, created_at=created_at, last_checked_at=last_checked_at, updated_at=updated_at)


def _incident(*, id="i1", monitor_id="m1", started_at, resolved_at=None, duration_seconds=0, reason="Timeout", status_code=None, is_resolved=False):
    return SimpleNamespace(id=id, persisted_id=id, monitor_id=monitor_id, started_at=started_at, resolved_at=resolved_at, duration_seconds=duration_seconds, reason=reason, status_code=status_code, is_resolved=is_resolved)


def _manager(
    *,
    monitors=None,
    first_check_times=None,
    incidents_by_monitor=None,
    recent_incidents=None,
    latest_results=None,
    average_response_time=0.0,
    open_incidents=0,
    get_monitor=None,
    response_history=None,
    statistics=None,
    slow_checks=0,
    status_history=None,
):
    monitors = monitors if monitors is not None else []
    monitor_map = {monitor.id: monitor for monitor in monitors}

    async def get_monitors_with_lookup():
        return monitors, monitor_map

    async def list_monitors():
        return monitors

    async def get_monitor_fn(_monitor_id):
        return get_monitor

    monitor_service = SimpleNamespace(get_monitors_with_lookup=get_monitors_with_lookup, list_monitors=list_monitors, get_monitor=get_monitor_fn)

    async def get_latest_per_monitor(limit=20):
        return latest_results or []

    async def average_response_time_fn():
        return average_response_time

    async def get_first_check_times(_monitor_ids):
        return first_check_times or {}

    async def get_response_history_fn(monitor_id, days):
        return response_history or []

    async def get_statistics_fn(monitor_id, days):
        return statistics or {"total": 0, "successful": 0}

    async def count_slow_checks_fn(_monitor_id):
        return slow_checks

    async def get_status_history_fn(monitor_id, days):
        return status_history or []

    monitor_result_service = SimpleNamespace(
        get_latest_per_monitor=get_latest_per_monitor,
        average_response_time=average_response_time_fn,
        get_first_check_times=get_first_check_times,
        get_response_history=get_response_history_fn,
        get_statistics=get_statistics_fn,
        count_slow_checks=count_slow_checks_fn,
        get_status_history=get_status_history_fn,
    )

    async def count_open():
        return open_incidents

    async def get_recent():
        return recent_incidents or []

    async def get_for_monitors(_monitor_ids):
        return incidents_by_monitor or {}

    incident_service = SimpleNamespace(count_open=count_open, get_recent=get_recent, get_for_monitors=get_for_monitors)

    return DashboardManager(monitor_service, monitor_result_service, incident_service)
