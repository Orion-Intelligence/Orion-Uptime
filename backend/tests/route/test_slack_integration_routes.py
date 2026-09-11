from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_slack_integration_model import SlackIntegrationResponse
from routes import slack_integration_routes
from tests.fake_model.fakes import FakeService

NOW = datetime.now(UTC)


def _integration(integration_id="slack-1"):
    return SlackIntegrationResponse(id=integration_id, name="Alerts", monitor_ids=[], monitor_count=0, created_at=NOW, updated_at=NOW, webhook_url="https://hooks.slack.com/services/T/B/X")


def _use(override, **returns):
    override(slack_integration_routes.get_slack_integration_service, lambda: FakeService(**returns))


def test_create_integration(client, override, as_admin):
    _use(override, create_integration=_integration())
    response = client.post("/api/integrations/slack", json={"name": "Alerts", "webhook_url": "https://hooks.slack.com/services/T/B/X", "monitor_ids": []})
    assert response.status_code == 201
    assert response.json()["data"]["id"] == "slack-1"


def test_list_integrations(client, override, as_admin):
    _use(override, list_integrations=[])
    response = client.get("/api/integrations/slack")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_get_integration(client, override, as_admin):
    _use(override, get_integration=_integration())
    response = client.get("/api/integrations/slack/slack-1")
    assert response.status_code == 200


def test_update_integration(client, override, as_admin):
    _use(override, update_integration=_integration())
    response = client.put("/api/integrations/slack/slack-1", json={"name": "renamed"})
    assert response.status_code == 200


def test_delete_integration(client, override, as_admin):
    _use(override, delete_integration=None)
    response = client.delete("/api/integrations/slack/slack-1")
    assert response.status_code == 200


def test_service_unavailable_returns_422(client, as_admin):
    response = client.get("/api/integrations/slack")
    assert response.status_code == 422
