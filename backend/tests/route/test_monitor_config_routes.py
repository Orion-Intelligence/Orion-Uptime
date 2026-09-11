from __future__ import annotations

from orion.services.mongo_manager.shared_model.db_monitor_config_model import MonitorImportResult, PingMonitorConfig
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from routes import monitor_config_routes
from tests.fake_model.fakes import FakeService

PING_CONFIG = {"format": "orion-monitor-config", "version": 1, "monitor_type": "ping", "name": "Gateway", "host": "example.com", "check_interval": 60, "timeout": 5}


def _use(override, **returns):
    override(monitor_config_routes.get_monitor_config_service, lambda: FakeService(**returns))


def test_import_monitor(client, override, as_admin):
    _use(override, import_monitor=MonitorImportResult(action="created", monitor_id="ping-1", monitor_type=MonitorType.PING, name="Gateway"))
    response = client.post("/api/monitor-configs/import", json=PING_CONFIG)
    assert response.status_code == 200
    assert response.json()["data"]["action"] == "created"


def test_import_monitor_rejects_type_mismatch(client, override, as_admin):
    _use(override, import_monitor=MonitorImportResult(action="created", monitor_id="ping-1", monitor_type=MonitorType.PING, name="Gateway"))
    response = client.post("/api/monitor-configs/import?expected_monitor_type=HTTP", json=PING_CONFIG)
    assert response.status_code == 422


def test_export_monitor(client, override, as_admin):
    exported = PingMonitorConfig(monitor_type=MonitorType.PING, name="Gateway", host="example.com", check_interval=60, timeout=5)
    _use(override, export_monitor=exported)
    response = client.get("/api/monitor-configs/ping/ping-1")
    assert response.status_code == 200
    assert response.json()["data"]["monitor_type"] == "ping"
