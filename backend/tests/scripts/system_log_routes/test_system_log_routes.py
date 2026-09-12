from __future__ import annotations

from orion.services.mongo_manager.shared_model.db_system_log_model import SystemLogEntry, SystemLogPageResponse
from routes import system_log_routes
from tests.model.fakes import FakeService


def _use(override, page):
    override(system_log_routes.get_system_log_service, lambda: FakeService(get_logs=page, close=None))


def test_list_system_logs(client, override, as_admin):
    _use(override, SystemLogPageResponse(logs=[SystemLogEntry(type="info", message="started")], total=1))
    response = client.get("/api/system-logs")
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1


def test_list_system_logs_with_filters(client, override, as_admin):
    _use(override, SystemLogPageResponse())
    response = client.get("/api/system-logs?log_type=error&date_from=2026-01-01&date_to=2026-01-31&page=2&limit=10")
    assert response.status_code == 200
    assert response.json()["data"]["logs"] == []
