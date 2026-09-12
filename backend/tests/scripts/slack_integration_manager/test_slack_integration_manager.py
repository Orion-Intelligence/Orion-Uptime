from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from bson import ObjectId

from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.constants.constant import Collections
from orion.services.encryption_manager.secrets import secret_box
from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_slack_integration_model import CreateSlackIntegrationRequest, UpdateSlackIntegrationRequest
from orion.shared_models.exceptions import NotFoundError, ValidationError
from tests.model.fakes import FakeCollection, FakeHttpClient, FakeMonitorService
from tests.scripts.slack_integration_manager.fakes import RecordingSlackClient
from tests.scripts.slack_integration_manager.fixtures import slack_crypto
from tests.scripts.slack_integration_manager.helpers import WEBHOOK_URL, _create_slack, _slack_integration_document, _slack_manager


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


@pytest.mark.usefixtures("slack_crypto")
def test_list_and_get_slack_integrations():
    manager, _ = _slack_manager()
    created = _create_slack(manager, name="Primary")

    listed = asyncio.run(manager.list_integrations())
    fetched = asyncio.run(manager.get_integration(created.id))

    assert [item.name for item in listed] == ["Primary"]
    assert fetched.id == created.id
    assert fetched.webhook_url == WEBHOOK_URL


@pytest.mark.usefixtures("slack_crypto")
def test_get_slack_integration_missing_or_invalid_id_raises_not_found():
    manager, _ = _slack_manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_integration(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_integration("not-a-valid-object-id"))


@pytest.mark.usefixtures("slack_crypto")
def test_update_slack_integration_changes_name_and_webhook():
    manager, _ = _slack_manager()
    created = _create_slack(manager, name="Orion")
    new_webhook = "https://hooks.slack.com/services/T111/B111/OTHER"

    updated = asyncio.run(manager.update_integration(created.id, UpdateSlackIntegrationRequest(name="Renamed", webhook_url=new_webhook)))

    assert updated.name == "Renamed"
    assert updated.webhook_url == new_webhook


@pytest.mark.usefixtures("slack_crypto")
def test_update_slack_integration_rejects_explicit_null_fields():
    manager, _ = _slack_manager()
    created = _create_slack(manager)
    with pytest.raises(ValidationError):
        asyncio.run(manager.update_integration(created.id, UpdateSlackIntegrationRequest(monitor_ids=None)))


@pytest.mark.usefixtures("slack_crypto")
def test_update_slack_integration_missing_raises_not_found():
    manager, _ = _slack_manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_integration(str(ObjectId()), UpdateSlackIntegrationRequest(name="Nope")))


@pytest.mark.usefixtures("slack_crypto")
def test_delete_slack_integration_and_missing_cases():
    manager, _ = _slack_manager()
    created = _create_slack(manager)

    asyncio.run(manager.delete_integration(created.id))

    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_integration(created.id))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_integration("not-a-valid-object-id"))


@pytest.mark.usefixtures("slack_crypto")
def test_create_slack_validates_monitor_ids():
    manager, _ = _slack_manager()
    with pytest.raises(ValidationError):
        _create_slack(manager, monitor_ids=["unknown-monitor"])

    manager_with_monitor, _ = _slack_manager(monitors=[SimpleNamespace(id="monitor-1")])
    created = _create_slack(manager_with_monitor, monitor_ids=["monitor-1", "monitor-1"])
    assert created.monitor_ids == ["monitor-1"]


@pytest.mark.usefixtures("slack_crypto")
def test_notify_transition_posts_to_slack_webhook_on_down_transition():
    collection = FakeCollection()
    collection.documents.append(_slack_integration_document())
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    client = RecordingSlackClient()
    manager = SlackIntegrationManager(engine, FakeMonitorService(), client=client)
    monitor = SimpleNamespace(name="Public website", monitor_type=MonitorType.HTTP, persisted_id="monitor-1")
    incident = IncidentModel(id="incident-id", monitor_id="monitor-1", monitor_type=MonitorType.HTTP, started_at=datetime.now(UTC), reason="Received HTTP 503 Service Unavailable.", status_code=503)
    result = SimpleNamespace(status_code=503, response_time_ms=120)
    state_result = SimpleNamespace(transition=MonitorTransition.DOWN, previous_status=MonitorStatus.UP)

    asyncio.run(manager.notify_transition(monitor, result, state_result, incident))

    assert len(client.calls) == 1
    url, payload = client.calls[0]
    assert url == WEBHOOK_URL
    assert "Public website is DOWN" in payload["text"]


@pytest.mark.usefixtures("slack_crypto")
def test_notify_transition_posts_to_slack_webhook_on_recovery():
    collection = FakeCollection()
    collection.documents.append(_slack_integration_document())
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    client = RecordingSlackClient()
    manager = SlackIntegrationManager(engine, FakeMonitorService(), client=client)
    monitor = SimpleNamespace(name="Public website", monitor_type=MonitorType.HTTP, persisted_id="monitor-1")
    started_at = datetime.now(UTC)
    incident = IncidentModel(id="incident-id", monitor_id="monitor-1", monitor_type=MonitorType.HTTP, started_at=started_at, resolved_at=started_at + timedelta(minutes=5), reason="Received HTTP 503 Service Unavailable.", status_code=503, is_resolved=True)
    result = SimpleNamespace(status_code=200, response_time_ms=85)
    state_result = SimpleNamespace(transition=MonitorTransition.UP, previous_status=MonitorStatus.DOWN)

    asyncio.run(manager.notify_transition(monitor, result, state_result, incident))

    assert len(client.calls) == 1
    url, payload = client.calls[0]
    assert url == WEBHOOK_URL
    assert "Public website is RECOVERED" in payload["text"]


@pytest.mark.usefixtures("slack_crypto")
def test_notify_transition_swallows_slack_delivery_failures(caplog):
    collection = FakeCollection()
    collection.documents.append(_slack_integration_document())
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    client = RecordingSlackClient(error=httpx.HTTPError("boom"))
    manager = SlackIntegrationManager(engine, FakeMonitorService(), client=client)
    monitor = SimpleNamespace(name="Public website", monitor_type=MonitorType.HTTP, persisted_id="monitor-1")
    incident = IncidentModel(id="incident-id", monitor_id="monitor-1", monitor_type=MonitorType.HTTP, started_at=datetime.now(UTC), reason="Received HTTP 503.", status_code=503)
    result = SimpleNamespace(status_code=503, response_time_ms=120)
    state_result = SimpleNamespace(transition=MonitorTransition.DOWN, previous_status=MonitorStatus.UP)

    with caplog.at_level(logging.ERROR, logger="orion.uptime.slack"):
        asyncio.run(manager.notify_transition(monitor, result, state_result, incident))

    assert len(client.calls) == 1
    assert "Slack notification delivery failed" in caplog.text


def test_notify_transition_skips_integrations_that_fail_to_load():
    collection = FakeCollection()
    now = datetime.now(UTC)
    collection.documents.append({"name": "Ops", "name_key": "ops", "monitor_ids": ["monitor-1"], "created_at": now, "updated_at": now, "_id": ObjectId()})
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    client = RecordingSlackClient()
    manager = SlackIntegrationManager(engine, FakeMonitorService(), client=client)
    monitor = SimpleNamespace(name="Public website", monitor_type=MonitorType.HTTP, persisted_id="monitor-1")
    result = SimpleNamespace(status_code=503, response_time_ms=120)
    state_result = SimpleNamespace(transition=MonitorTransition.DOWN, previous_status=MonitorStatus.UP)

    asyncio.run(manager.notify_transition(monitor, result, state_result, None))

    assert client.calls == []


def test_close_closes_default_and_injected_clients():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    owned_manager = SlackIntegrationManager(engine, FakeMonitorService())
    asyncio.run(owned_manager.close())

    injected_client = RecordingSlackClient()
    injected_manager = SlackIntegrationManager(engine, FakeMonitorService(), client=injected_client)
    asyncio.run(injected_manager.close())
