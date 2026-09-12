from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_insight_model import DashboardSummaryResponse, MonitorDetailResponse, ResponseHistoryResponse, StatusHistoryResponse, UptimeResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from routes import insight_routes
from tests.model.fakes import FakeService

NOW = datetime.now(UTC)


def _summary():
    return DashboardSummaryResponse(total_monitors=1, active_monitors=1, inactive_monitors=0, monitors_up=1, monitors_down=0, monitors_unknown=0, slow_monitors=0, open_incidents=0, average_response_time_ms=42.0, overall_uptime_percentage=99.9)


def _detail(monitor_id="monitor-1"):
    return MonitorDetailResponse(id=monitor_id, name="API", monitor_type="HTTP", status=MonitorStatus.UP, is_active=True, created_at=NOW, last_checked_at=None, uptime_percentage=None, current_uptime_seconds=0, latest_downtime_seconds=0, measurement_seconds=0, downtime_seconds=0, snapshot_at=NOW, incidents=[])


def _use(override, **returns):
    override(insight_routes.get_dashboard_service, lambda: FakeService(**returns))


def test_get_summary(client, override, as_viewer):
    _use(override, get_summary=_summary())
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    assert response.json()["data"]["total_monitors"] == 1


def test_get_dashboard_incidents(client, override, as_viewer):
    _use(override, get_recent_incidents=[])
    response = client.get("/api/dashboard/incidents")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_dashboard_activity(client, override, as_viewer):
    _use(override, get_recent_activity=[])
    response = client.get("/api/dashboard/activity")
    assert response.status_code == 200


def test_get_monitor_overviews(client, override, as_viewer):
    _use(override, get_monitor_overviews=[])
    response = client.get("/api/dashboard/monitor-overviews")
    assert response.status_code == 200


def test_get_monitor_detail(client, override, as_viewer):
    _use(override, get_monitor_detail=_detail())
    response = client.get("/api/dashboard/monitors/monitor-1")
    assert response.status_code == 200


def test_get_response_history(client, override, as_viewer):
    _use(override, get_response_history=ResponseHistoryResponse(monitor_id="monitor-1", points=[]))
    response = client.get("/api/dashboard/response-history/monitor-1?days=30")
    assert response.status_code == 200


def test_get_uptime(client, override, as_viewer):
    _use(override, get_uptime=UptimeResponse(monitor_id="monitor-1", uptime_percentage=99.5, total_checks=100, successful_checks=99, failed_checks=1, slow_checks=0))
    response = client.get("/api/dashboard/uptime/monitor-1")
    assert response.status_code == 200


def test_get_status_history(client, override, as_viewer):
    _use(override, get_status_history=StatusHistoryResponse(monitor_id="monitor-1", history=[]))
    response = client.get("/api/dashboard/status-history/monitor-1")
    assert response.status_code == 200
