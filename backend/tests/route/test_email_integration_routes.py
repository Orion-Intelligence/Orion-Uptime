from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_email_integration_model import EmailIntegrationResponse
from routes import email_integration_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _integration(integration_id="email-1"):
    return EmailIntegrationResponse(id=integration_id, name="On-call", email="alerts@example.com", monitor_ids=[], monitor_count=0, created_at=NOW, updated_at=NOW)


def _use(override, **returns):
    override(email_integration_routes.get_email_integration_service, lambda: FakeService(**returns))


def test_create_integration(client, override, as_admin):
    _use(override, create_integration=_integration())
    response = client.post("/api/integrations/email", json={"name": "On-call", "email": "alerts@example.com", "monitor_ids": []})
    assert response.status_code == 201
    assert response.json()["data"]["id"] == "email-1"


def test_list_integrations(client, override, as_admin):
    _use(override, list_integrations=[])
    response = client.get("/api/integrations/email")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_integration(client, override, as_admin):
    _use(override, get_integration=_integration())
    response = client.get("/api/integrations/email/email-1")
    assert response.status_code == 200


def test_update_integration(client, override, as_admin):
    _use(override, update_integration=_integration())
    response = client.put("/api/integrations/email/email-1", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_integration(client, override, as_admin):
    _use(override, delete_integration=None)
    response = client.delete("/api/integrations/email/email-1")
    assert response.status_code == 200


def test_service_unavailable_returns_422(client, as_admin):
    response = client.get("/api/integrations/email")
    assert response.status_code == 422
