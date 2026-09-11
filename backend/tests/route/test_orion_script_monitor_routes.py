from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionScriptMonitorResponse
from routes import orion_script_monitor_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _monitor(monitor_id="script-1"):
    return OrionScriptMonitorResponse(id=monitor_id, name="Feed", url="https://example.com", check_interval=300, timeout=30, is_active=True, created_at=NOW, updated_at=NOW, last_checked_at=None, last_response_time_ms=None, status=MonitorStatus.UP, expected_response_time_ms=None)


def _use(override, **returns):
    override(orion_script_monitor_routes.get_orion_script_service, lambda: FakeService(**returns))


def test_create_monitor(client, override, as_admin):
    _use(override, create_monitor=_monitor())
    response = client.post("/api/orion-script-monitors/create", json={"name": "Feed", "url": "https://example.com"})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == "script-1"


def test_list_monitors(client, override, as_admin):
    _use(override, list_monitors=[])
    response = client.get("/api/orion-script-monitors/list_all")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_monitor(client, override, as_admin):
    _use(override, get_monitor=_monitor())
    response = client.get("/api/orion-script-monitors/script-1/get_one")
    assert response.status_code == 200


def test_update_monitor(client, override, as_admin):
    _use(override, update_monitor=_monitor())
    response = client.put("/api/orion-script-monitors/script-1/update", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_monitor(client, override, as_admin):
    _use(override, delete_monitor=None)
    response = client.delete("/api/orion-script-monitors/script-1/delete")
    assert response.status_code == 200
