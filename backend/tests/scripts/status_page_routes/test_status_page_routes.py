from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from orion.services.mongo_manager.shared_model.db_status_page_model import PublicStatusPageResponse, PublicUptimeStatusResponse, StatusPageResponse
from orion.shared_models.exceptions import NotFoundError
from routes import status_page_routes
from tests.model.fakes import FakeService

NOW = datetime.now(UTC)


def _page(page_id="page-1"):
    return StatusPageResponse(id=page_id, name="Public", slug="public", description="", monitor_ids=[], monitor_count=0, public_path="/status/public", created_at=NOW, updated_at=NOW)


def _public_page():
    return PublicStatusPageResponse(name="Public", slug="public", description="", overall_status="operational", monitor_count=0, monitors_up=0, monitors_down=0, monitors_unknown=0, monitors_paused=0, generated_at=NOW, uptime_status=PublicUptimeStatusResponse(last_24_hours=None, last_7_days=None, last_30_days=None, last_90_days=None), monitors=[])


def _use(override, **returns):
    override(status_page_routes.get_status_page_service, lambda: FakeService(**returns))


def test_get_public_page_is_public(client, override):
    _use(override, get_public_page=_public_page())
    response = client.get("/api/status-pages/public/public")
    assert response.status_code == 200
    assert response.json()["data"]["slug"] == "public"


def test_get_public_monitor_detail_not_found(client, override):
    _use(override, get_public_monitor_detail=NotFoundError("This public monitor is no longer available."))
    response = client.get("/api/status-pages/public/public/monitors/monitor-1")
    assert response.status_code == 404


def test_create_page(client, override, as_admin):
    _use(override, create_page=_page())
    response = client.post("/api/status-pages", json={"name": "Public", "description": "", "monitor_ids": []})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == "page-1"


def test_list_pages(client, override, as_admin):
    _use(override, list_pages=[])
    response = client.get("/api/status-pages")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_page(client, override, as_admin):
    _use(override, get_page=_page())
    response = client.get("/api/status-pages/page-1")
    assert response.status_code == 200


def test_update_page(client, override, as_admin):
    _use(override, update_page=_page())
    response = client.put("/api/status-pages/page-1", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_page(client, override, as_admin):
    _use(override, delete_page=None)
    response = client.delete("/api/status-pages/page-1")
    assert response.status_code == 200


def test_stream_public_monitor_detail_emits_snapshot(client, override, stub_stream):
    override(status_page_routes.get_status_page_service, lambda: FakeService(get_public_monitor_detail={"monitor": "monitor-1"}, get_page_by_slug=SimpleNamespace(id="page-1", persisted_id="page-1", monitor_ids=[])))
    response = client.get("/api/status-pages/public/public/monitors/monitor-1/events")
    assert response.status_code == 200
    assert "event: snapshot" in response.text


def test_stream_public_page_emits_snapshot(client, override, stub_stream):
    override(status_page_routes.get_status_page_service, lambda: FakeService(get_page_by_slug=SimpleNamespace(id="page-1", persisted_id="page-1", monitor_ids=[]), build_public_response={"name": "Public"}))
    response = client.get("/api/status-pages/public/public/events")
    assert response.status_code == 200
    assert "event: snapshot" in response.text
