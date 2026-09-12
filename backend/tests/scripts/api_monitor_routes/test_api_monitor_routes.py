from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_api_monitor_model import ApiMonitorResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from routes import api_monitor_routes
from tests.model.fakes import FakeService

NOW = datetime.now(UTC)


def _monitor(monitor_id="api-1"):
    return ApiMonitorResponse(id=monitor_id, name="API", url="https://example.com", method="GET", headers={}, request_body=None, expected_status_code=200, expected_json=None, check_interval=60, timeout=10, is_active=True, created_at=NOW, updated_at=NOW, last_checked_at=None, last_status_code=None, last_response_time_ms=None, status=MonitorStatus.UP, expected_response_time_ms=None, expected_headers=None, expected_content_type=None)


def _use(override, **returns):
    override(api_monitor_routes.get_api_monitor_service, lambda: FakeService(**returns))


def test_create_monitor(client, override, as_admin):
    _use(override, create_monitor=_monitor())
    response = client.post("/api/API_monitors/create", json={"name": "API", "url": "https://example.com", "expected_status_code": 200, "check_interval": 60})
    assert response.status_code == 201
    assert response.json()["data"]["id"] == "api-1"


def test_list_monitors(client, override, as_admin):
    _use(override, list_monitors=[])
    response = client.get("/api/API_monitors/list_all")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_monitor(client, override, as_admin):
    _use(override, get_monitor=_monitor())
    response = client.get("/api/API_monitors/api-1")
    assert response.status_code == 200


def test_update_monitor(client, override, as_admin):
    _use(override, update_monitor=_monitor())
    response = client.put("/api/API_monitors/api-1", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_monitor(client, override, as_admin):
    _use(override, delete_monitor=None)
    response = client.delete("/api/API_monitors/api-1")
    assert response.status_code == 200
