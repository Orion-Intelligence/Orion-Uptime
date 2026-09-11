from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orion.api.interactive.insight_manager.insight_manager import DashboardManager
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.shared_models.exceptions import NotFoundError

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


def test_get_summary_counts_and_defaults_uptime_to_zero_without_history():
    monitors = [_monitor("m1", status=MonitorStatus.UP), _monitor("m2", is_active=False, status=MonitorStatus.DOWN), _monitor("m3", status=MonitorStatus.UNKNOWN)]
    latest_results = [SimpleNamespace(monitor_id="m1", is_slow=True), SimpleNamespace(monitor_id="m2", is_slow=True), SimpleNamespace(monitor_id="ghost", is_slow=True)]
    manager = _manager(monitors=monitors, latest_results=latest_results, average_response_time=123.4, open_incidents=2)

    summary = asyncio.run(manager.get_summary())

    assert summary.total_monitors == 3
    assert summary.active_monitors == 2
    assert summary.inactive_monitors == 1
    assert summary.monitors_up == 1
    assert summary.monitors_down == 1
    assert summary.monitors_unknown == 1
    assert summary.slow_monitors == 1
    assert summary.open_incidents == 2
    assert summary.average_response_time_ms == 123.4
    assert summary.overall_uptime_percentage == 0.0


def test_get_recent_incidents_maps_monitor_names_and_falls_back_to_unknown():
    monitors = [_monitor("m1", name="API")]
    incidents = [
        _incident(id="i1", monitor_id="m1", started_at=NOW - timedelta(hours=2), resolved_at=NOW - timedelta(hours=1), duration_seconds=3600, reason="Timeout", status_code=500),
        _incident(id="i2", monitor_id="ghost", started_at=NOW - timedelta(hours=3), resolved_at=None, duration_seconds=None, reason="Connection refused"),
    ]
    manager = _manager(monitors=monitors, recent_incidents=incidents)

    results = asyncio.run(manager.get_recent_incidents())

    assert [item.monitor_name for item in results] == ["API", "Unknown"]
    assert results[0].id == "i1"
    assert results[0].status_code == 500
    assert results[1].resolved_at is None


def test_get_monitor_overviews_computes_uptime_and_current_uptime():
    created_at = NOW - timedelta(days=10)
    updated_at = NOW - timedelta(days=1)
    monitor = _monitor("m1", status=MonitorStatus.UP, is_active=False, created_at=created_at, updated_at=updated_at)
    first_check_at = NOW - timedelta(days=6)
    incident = _incident(id="i1", monitor_id="m1", started_at=NOW - timedelta(days=3), resolved_at=NOW - timedelta(days=3) + timedelta(hours=2), duration_seconds=7200)

    manager = _manager(monitors=[monitor], first_check_times={"m1": first_check_at}, incidents_by_monitor={"m1": [incident]})

    overviews = asyncio.run(manager.get_monitor_overviews())

    assert len(overviews) == 1
    overview = overviews[0]
    assert overview.measurement_seconds == 5 * 24 * 3600
    assert overview.downtime_seconds == 7200
    assert overview.uptime_percentage == pytest.approx(98.33, abs=0.01)
    assert overview.current_uptime_seconds == 2 * 24 * 3600 - 2 * 3600
    assert overview.latest_downtime_seconds == 7200


def test_get_monitor_overviews_skips_monitors_without_id_and_unknown_status():
    monitor_with_no_id = _monitor(None)
    unknown_monitor = _monitor("m2", status=MonitorStatus.UNKNOWN)
    manager = _manager(monitors=[monitor_with_no_id, unknown_monitor], first_check_times={"m2": NOW - timedelta(days=1)})

    overviews = asyncio.run(manager.get_monitor_overviews())

    assert len(overviews) == 1
    assert overviews[0].id == "m2"
    assert overviews[0].uptime_percentage is None
    assert overviews[0].current_uptime_seconds == 0


def test_get_monitor_detail_builds_incident_history_and_filters_unpersisted():
    monitor = _monitor("m1", status=MonitorStatus.UP, is_active=False, created_at=NOW - timedelta(days=10), updated_at=NOW - timedelta(days=1))
    resolved_incident = _incident(id="i1", monitor_id="m1", started_at=NOW - timedelta(days=2), resolved_at=NOW - timedelta(days=2) + timedelta(hours=1), duration_seconds=3600, is_resolved=True)
    unpersisted_incident = _incident(id=None, monitor_id="m1", started_at=NOW - timedelta(days=1), duration_seconds=0)
    manager = _manager(monitors=[monitor], first_check_times={"m1": NOW - timedelta(days=5)}, incidents_by_monitor={"m1": [resolved_incident, unpersisted_incident]})

    detail = asyncio.run(manager.get_monitor_detail("m1"))

    assert detail.id == "m1"
    assert len(detail.incidents) == 1
    assert detail.incidents[0].id == "i1"
    assert detail.incidents[0].status == "resolved"


def test_get_monitor_detail_raises_when_monitor_missing():
    manager = _manager(monitors=[])
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_monitor_detail("ghost"))


def test_get_recent_activity_maps_monitor_names_and_falls_back_to_unknown():
    monitors = [_monitor("m1", name="Website")]
    results = [
        SimpleNamespace(monitor_id="m1", status=MonitorStatus.UP, status_code=200, response_time_ms=120, checked_at=NOW, is_slow=False),
        SimpleNamespace(monitor_id="ghost", status=MonitorStatus.DOWN, status_code=500, response_time_ms=None, checked_at=NOW, is_slow=True),
    ]
    manager = _manager(monitors=monitors, latest_results=results)

    activity = asyncio.run(manager.get_recent_activity())

    assert [item.monitor_name for item in activity] == ["Website", "Unknown"]
    assert activity[0].status == MonitorStatus.UP
    assert activity[1].is_slow is True


def test_get_response_history_returns_points_for_existing_monitor():
    history = [SimpleNamespace(checked_at=NOW, response_time_ms=100), SimpleNamespace(checked_at=NOW - timedelta(hours=1), response_time_ms=150)]
    manager = _manager(get_monitor=SimpleNamespace(id="m1"), response_history=history)

    response = asyncio.run(manager.get_response_history("m1", 7))

    assert response.monitor_id == "m1"
    assert [point.response_time_ms for point in response.points] == [100, 150]


def test_get_response_history_raises_when_monitor_missing():
    manager = _manager(get_monitor=None)
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_response_history("ghost", 7))


def test_get_uptime_computes_percentage_and_counts():
    manager = _manager(get_monitor=SimpleNamespace(id="m1"), statistics={"total": 20, "successful": 18}, slow_checks=3)

    uptime = asyncio.run(manager.get_uptime("m1", 7))

    assert uptime.uptime_percentage == 90.0
    assert uptime.total_checks == 20
    assert uptime.successful_checks == 18
    assert uptime.failed_checks == 2
    assert uptime.slow_checks == 3


def test_get_uptime_defaults_to_zero_percentage_with_no_checks():
    manager = _manager(get_monitor=SimpleNamespace(id="m1"), statistics={"total": 0, "successful": 0})

    uptime = asyncio.run(manager.get_uptime("m1", 7))

    assert uptime.uptime_percentage == 0.0
    assert uptime.failed_checks == 0


def test_get_uptime_raises_when_monitor_missing():
    manager = _manager(get_monitor=None)
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_uptime("ghost", 7))


def test_get_status_history_returns_history_for_existing_monitor():
    history = [SimpleNamespace(checked_at=NOW, status=MonitorStatus.UP), SimpleNamespace(checked_at=NOW - timedelta(hours=1), status=MonitorStatus.DOWN)]
    manager = _manager(get_monitor=SimpleNamespace(id="m1"), status_history=history)

    response = asyncio.run(manager.get_status_history("m1", 7))

    assert response.monitor_id == "m1"
    assert [point.status for point in response.history] == [MonitorStatus.UP, MonitorStatus.DOWN]


def test_get_status_history_raises_when_monitor_missing():
    manager = _manager(get_monitor=None)
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_status_history("ghost", 7))


def test_duration_and_overlap_helpers():
    started_at = NOW - timedelta(hours=2)
    ended_at = NOW
    assert DashboardManager._duration_seconds(started_at, ended_at) == 7200
    assert DashboardManager._duration_seconds(ended_at, started_at) == 0

    naive = datetime(2024, 1, 1, 0, 0, 0)
    assert DashboardManager._as_utc(naive).tzinfo == UTC
    assert DashboardManager._as_utc(NOW).tzinfo == UTC

    period_start = NOW - timedelta(hours=1)
    period_end = NOW
    assert DashboardManager._incident_overlap_seconds(NOW - timedelta(hours=2), None, period_start, period_end) == 3600.0
    assert DashboardManager._incident_overlap_seconds(NOW - timedelta(hours=5), NOW - timedelta(hours=4), period_start, period_end) == 0.0
