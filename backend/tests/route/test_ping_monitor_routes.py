from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_ping_monitor_model import PingMonitorResponse
from routes import ping_monitor_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _monitor(monitor_id="ping-1"):
    return PingMonitorResponse(id=monitor_id, name="Gateway", host="example.com", check_interval=60, timeout=5, is_active=True, created_at=NOW, updated_at=NOW, last_checked_at=None, last_response_time_ms=None, status=MonitorStatus.UP, expected_response_time_ms=None)


def _use(override, **returns):
    override(ping_monitor_routes.get_ping_service, lambda: FakeService(**returns))


def test_create_monitor(client, override, as_admin):
    _use(override, create_monitor=_monitor())
    response = client.post("/api/ping-monitors/create", json={"name": "Gateway", "host": "example.com", "check_interval": 60, "timeout": 5})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == "ping-1"


def test_list_monitors(client, override, as_admin):
    _use(override, list_monitors=[])
    response = client.get("/api/ping-monitors/list_all")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_monitor(client, override, as_admin):
    _use(override, get_monitor=_monitor())
    response = client.get("/api/ping-monitors/ping-1/get_one")
    assert response.status_code == 200


def test_update_monitor(client, override, as_admin):
    _use(override, update_monitor=_monitor())
    response = client.put("/api/ping-monitors/ping-1/update", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_monitor(client, override, as_admin):
    _use(override, delete_monitor=None)
    response = client.delete("/api/ping-monitors/ping-1/delete")
    assert response.status_code == 200
