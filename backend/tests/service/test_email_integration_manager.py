from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.email_integration_manager.email_integration_manager import EmailIntegrationManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_email_integration_model import CreateEmailIntegrationRequest, EmailIntegrationModel
from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.shared_models.exceptions import ValidationError


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *_args):
        return self

    def __aiter__(self):
        self.iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeCollection:
    def __init__(self):
        self.documents = []

    async def find_one(self, query, _projection=None):
        for document in self.documents:
            if "name_key" in query and document.get("name_key") == query["name_key"]:
                return document
            if "_id" in query and document.get("_id") == query["_id"]:
                return document
        return None

    async def insert_one(self, document):
        inserted = {**document, "_id": ObjectId()}
        self.documents.append(inserted)
        return SimpleNamespace(inserted_id=inserted["_id"])

    def find(self, query=None):
        query = query or {}
        monitor_id = query.get("monitor_ids")
        documents = self.documents if monitor_id is None else [document for document in self.documents if monitor_id in document.get("monitor_ids", [])]
        return FakeCursor([document.copy() for document in documents])


class FakeMonitorService:
    async def list_monitors(self):
        return []


def test_duplicate_email_integration_names_receive_numeric_suffix():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.EMAIL_INTEGRATIONS: collection})
    manager = EmailIntegrationManager(engine, FakeMonitorService())
    request = CreateEmailIntegrationRequest(name="On-call", email="alerts@example.com")

    first = asyncio.run(manager.create_integration(request))
    second = asyncio.run(manager.create_integration(request))

    assert first.name == "On-call"
    assert second.name == "On-call1"


@pytest.mark.parametrize("email", ["", "not-an-email", "user@localhost", "user@example", "user name@example.com"])
def test_email_validation_rejects_invalid_recipients(email):
    with pytest.raises(ValidationError):
        EmailIntegrationManager._validated_email(email)


def test_email_alerts_only_send_for_down_and_recovery_transitions():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.EMAIL_INTEGRATIONS: collection})
    sent_messages = []
    manager = EmailIntegrationManager(engine, FakeMonitorService(), sender=sent_messages.append)
    now = datetime.now(UTC)
    integration = EmailIntegrationModel(name="On-call", name_key="on-call", email="alerts@example.com", monitor_ids=["monitor-id"], created_at=now, updated_at=now)
    document = integration.model_dump(exclude={"id"})
    document["_id"] = ObjectId()
    collection.documents.append(document)
    monitor = SimpleNamespace(id="monitor-id", persisted_id="monitor-id", name="Public API", monitor_type=MonitorType.API)
    incident = IncidentModel(id="incident-id", monitor_id="monitor-id", monitor_type=MonitorType.API, started_at=now, reason="Received HTTP 503.", status_code=503)
    result = SimpleNamespace(status_code=503, response_time_ms=120)

    routine = SimpleNamespace(transition=MonitorTransition.NONE, previous_status=MonitorStatus.UP)
    down = SimpleNamespace(transition=MonitorTransition.DOWN, previous_status=MonitorStatus.UP)
    recovery = SimpleNamespace(transition=MonitorTransition.UP, previous_status=MonitorStatus.DOWN)
    asyncio.run(manager.notify_transition(monitor, result, routine, incident))
    asyncio.run(manager.notify_transition(monitor, result, down, incident))
    incident.resolved_at = now + timedelta(minutes=5)
    incident.is_resolved = True
    asyncio.run(manager.notify_transition(monitor, result, recovery, incident))

    assert len(sent_messages) == 2
    assert "Public API is DOWN" in sent_messages[0]["Subject"]
    assert "Root cause: Received HTTP 503." in sent_messages[0].get_content()
    assert "Status code: 503" in sent_messages[0].get_content()
    assert "Resolved: Ongoing" in sent_messages[0].get_content()
    assert "Public API is RECOVERED" in sent_messages[1]["Subject"]
    assert incident.resolved_at.isoformat() in sent_messages[1].get_content()


def test_ping_email_omits_http_status_code():
    now = datetime.now(UTC)
    integration = EmailIntegrationModel(id="integration-id", name="Network", name_key="network", email="network@example.com", monitor_ids=["monitor-id"], created_at=now, updated_at=now)
    monitor = SimpleNamespace(name="Gateway", monitor_type=MonitorType.PING)
    incident = IncidentModel(id="incident-id", monitor_id="monitor-id", monitor_type=MonitorType.PING, started_at=now, reason="The host did not reply.")

    message = EmailIntegrationManager._build_message(integration, monitor, is_down=True, result=SimpleNamespace(response_time_ms=None), incident=incident)

    assert "Status code:" not in message.get_content()
