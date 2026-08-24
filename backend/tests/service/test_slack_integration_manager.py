from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.constants.constant import Collections
from orion.services.encryption_manager.secrets import secret_box
from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from orion.services.mongo_manager.shared_model.db_slack_integration_model import CreateSlackIntegrationRequest
from orion.shared_models.exceptions import ValidationError


class FakeCollection:
    def __init__(self):
        self.documents = []

    async def find_one(self, query, _projection=None):
        for document in self.documents:
            if document.get("name_key") == query.get("name_key"):
                return document
        return None

    async def insert_one(self, document):
        inserted = {**document, "_id": ObjectId()}
        self.documents.append(inserted)
        return SimpleNamespace(inserted_id=inserted["_id"])


class FakeMonitorService:
    async def list_monitors(self):
        return []


class FakeHttpClient:
    pass


def test_duplicate_slack_integration_names_receive_numeric_suffix(monkeypatch):
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    manager = SlackIntegrationManager(engine, FakeMonitorService(), client=FakeHttpClient())
    monkeypatch.setattr(secret_box, "encrypt_mapping", lambda values: values["webhook_url"])
    request = CreateSlackIntegrationRequest(name="Orion", webhook_url="https://hooks.slack.com/services/T000/B000/SECRET")

    first = asyncio.run(manager.create_integration(request))
    second = asyncio.run(manager.create_integration(request))

    assert first.name == "Orion"
    assert second.name == "Orion1"


@pytest.mark.parametrize(
    "webhook_url",
    [
        "http://hooks.slack.com/services/T000/B000/SECRET",
        "https://hooks.slack.com.example.com/services/T000/B000/SECRET",
        "https://example.com/services/T000/B000/SECRET",
        "https://hooks.slack.com/services/T000/B000",
    ],
)
def test_slack_webhook_validation_rejects_unsafe_urls(webhook_url):
    with pytest.raises(ValidationError):
        SlackIntegrationManager._validated_webhook_url(webhook_url)


def test_slack_webhook_validation_accepts_standard_and_gov_urls():
    standard = "https://hooks.slack.com/services/T000/B000/SECRET"
    government = "https://hooks.slack-gov.com/services/T000/B000/SECRET"

    assert SlackIntegrationManager._validated_webhook_url(standard) == standard
    assert SlackIntegrationManager._validated_webhook_url(government) == government


def test_recovery_payload_contains_http_incident_details():
    started_at = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    resolved_at = started_at + timedelta(minutes=5)
    incident = IncidentModel(id="incident-id", monitor_id="monitor-id", monitor_type=MonitorType.HTTP, started_at=started_at, resolved_at=resolved_at, reason="Received HTTP 503 Service Unavailable.", status_code=503, is_resolved=True)
    monitor = SimpleNamespace(name="Public website", monitor_type=MonitorType.HTTP)
    result = SimpleNamespace(status_code=200, response_time_ms=85)

    payload = SlackIntegrationManager._notification_payload(monitor, is_down=False, result=result, incident=incident)
    main_text = payload["blocks"][0]["text"]["text"]
    fields = [field["text"] for field in payload["blocks"][1]["fields"]]

    assert "*Root cause:* Received HTTP 503 Service Unavailable." in main_text
    assert "*Status code:* 503" in fields
    assert any(str(int(started_at.timestamp())) in field for field in fields if "Incident started" in field)
    assert any(str(int(resolved_at.timestamp())) in field for field in fields if "Resolved" in field)


def test_ping_outage_payload_omits_status_code_and_is_ongoing():
    started_at = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    incident = IncidentModel(id="incident-id", monitor_id="monitor-id", monitor_type=MonitorType.PING, started_at=started_at, reason="The host did not reply.")
    monitor = SimpleNamespace(name="Gateway", monitor_type=MonitorType.PING)

    payload = SlackIntegrationManager._notification_payload(monitor, is_down=True, result=SimpleNamespace(response_time_ms=None), incident=incident)
    fields = [field["text"] for field in payload["blocks"][1]["fields"]]

    assert not any("Status code" in field for field in fields)
    assert "*Resolved:* Ongoing" in fields
