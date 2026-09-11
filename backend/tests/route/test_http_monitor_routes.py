from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_http_monitor_model import HttpMonitorResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from routes import http_monitor_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _monitor(monitor_id="http-1"):
    return HttpMonitorResponse(id=monitor_id, name="API", url="https://example.com", check_interval=60, expected_status_code=200, timeout=10, is_active=True, created_at=NOW, updated_at=NOW, last_checked_at=None, last_status_code=None, last_response_time_ms=None, status=MonitorStatus.UP, expected_response_time_ms=None)


def _use(override, **returns):
    override(http_monitor_routes.get_http_monitor_service, lambda: FakeService(**returns))


def test_create_monitor(client, override, as_admin):
    _use(override, create_monitor=_monitor())
    response = client.post("/api/HTTP_monitors/create", json={"name": "API", "url": "https://example.com", "check_interval": 60, "timeout": 10, "expected_status_code": 200})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == "http-1"


def test_list_monitors(client, override, as_admin):
    _use(override, list_monitors=[])
    response = client.get("/api/HTTP_monitors/list_all")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_monitor(client, override, as_admin):
    _use(override, get_monitor=_monitor())
    response = client.get("/api/HTTP_monitors/http-1/get_one")
    assert response.status_code == 200


def test_update_monitor(client, override, as_admin):
    _use(override, update_monitor=_monitor())
    response = client.put("/api/HTTP_monitors/http-1/update", json={"name": "renamed", "expected_response_time_ms": 500})
    assert response.status_code == 200


def test_delete_monitor(client, override, as_admin):
    _use(override, delete_monitor=None)
    response = client.delete("/api/HTTP_monitors/http-1/delete")
    assert response.status_code == 200
