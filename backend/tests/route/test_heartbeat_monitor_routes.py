from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorResponse, HeartbeatResponse, HeartbeatTokenResponse, RegenerateHeartbeatTokenResponse
from routes import heartbeat_monitor_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _monitor(monitor_id="hb-1"):
    return HeartbeatMonitorResponse(id=monitor_id, name="Cron", expected_heartbeat_interval=300, grace_period=60, status="unknown", is_active=True, last_heartbeat_at=None, created_at=NOW.isoformat(), updated_at=NOW.isoformat())


def _use(override, **returns):
    override(heartbeat_monitor_routes.get_heartbeat_service, lambda: FakeService(**returns))


def test_create_monitor(client, override, as_admin):
    _use(override, create_monitor=HeartbeatTokenResponse(heartbeat_token="secret-token"))
    response = client.post("/api/heartbeat-monitors/create", json={"name": "Cron", "expected_heartbeat_interval": 300, "grace_period": 60})
    assert response.status_code == 200
    assert response.json()["data"]["heartbeat_token"] == "secret-token"


def test_list_monitors(client, override, as_admin):
    _use(override, list_monitors=[])
    response = client.get("/api/heartbeat-monitors/list_all")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_monitor(client, override, as_admin):
    _use(override, get_monitor=_monitor())
    response = client.get("/api/heartbeat-monitors/hb-1/get_one")
    assert response.status_code == 200


def test_update_monitor(client, override, as_admin):
    _use(override, update_monitor=_monitor())
    response = client.put("/api/heartbeat-monitors/hb-1/update", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_monitor(client, override, as_admin):
    _use(override, delete_monitor=None)
    response = client.delete("/api/heartbeat-monitors/hb-1/delete")
    assert response.status_code == 200


def test_receive_heartbeat_is_public(client, override):
    _use(override, receive_heartbeat=HeartbeatResponse(message="ok", expected_next_heartbeat_in=300, server_time=NOW, token_rotation_required=False))
    response = client.post("/api/heartbeat-monitors/heartbeat/secret-token")
    assert response.status_code == 200
    assert response.json()["data"]["message"] == "ok"


def test_regenerate_token(client, override, as_admin):
    _use(override, regenerate_token=RegenerateHeartbeatTokenResponse(heartbeat_token="rotated-token"))
    response = client.patch("/api/heartbeat-monitors/hb-1/regenerate-token")
    assert response.status_code == 200
    assert response.json()["data"]["heartbeat_token"] == "rotated-token"
