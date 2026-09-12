from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.email_integration_manager.email_integration_manager import EmailIntegrationManager
from orion.constants.constant import Collections
from orion.services.email_template_manager import EmailTemplateManager
from orion.services.mongo_manager.shared_model.db_email_integration_model import CreateEmailIntegrationRequest, EmailIntegrationModel, UpdateEmailIntegrationRequest
from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.shared_models.exceptions import NotFoundError, ValidationError
from tests.fake_model.fakes import FakeCollection, FakeMonitorService


def _manager(monitors=None):
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.EMAIL_INTEGRATIONS: collection})
    return EmailIntegrationManager(engine, FakeMonitorService(monitors)), collection


def _create(manager, name="On-call", email="alerts@example.com", monitor_ids=None):
    return asyncio.run(manager.create_integration(CreateEmailIntegrationRequest(name=name, email=email, monitor_ids=monitor_ids or [])))


@pytest.fixture(autouse=True)
def initialized_email_templates():
    template_manager = EmailTemplateManager.get_instance()
    template_manager.clear()
    template_manager.initialize()
    yield
    template_manager.clear()


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


def test_email_alerts_only_send_for_down_and_recovery_transitions(monkeypatch):
    async def run_immediately(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", run_immediately)
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
    assert "Root cause: Received HTTP 503." in sent_messages[0].get_body(preferencelist=("plain",)).get_content()
    assert "Status code: 503" in sent_messages[0].get_body(preferencelist=("plain",)).get_content()
    assert "Resolved: Ongoing" in sent_messages[0].get_body(preferencelist=("plain",)).get_content()
    assert "Public API is RECOVERED" in sent_messages[1]["Subject"]
    assert EmailIntegrationManager._timestamp(incident.resolved_at) in sent_messages[1].get_body(preferencelist=("plain",)).get_content()


def test_ping_email_omits_http_status_code():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.EMAIL_INTEGRATIONS: collection})
    manager = EmailIntegrationManager(engine, FakeMonitorService())
    now = datetime.now(UTC)
    integration = EmailIntegrationModel(id="integration-id", name="Network", name_key="network", email="network@example.com", monitor_ids=["monitor-id"], created_at=now, updated_at=now)
    monitor = SimpleNamespace(name="Gateway", monitor_type=MonitorType.PING)
    incident = IncidentModel(id="incident-id", monitor_id="monitor-id", monitor_type=MonitorType.PING, started_at=now, reason="The host did not reply.")

    message = manager._build_message(integration, monitor, is_down=True, result=SimpleNamespace(response_time_ms=None), incident=incident)

    assert "Status code:" not in message.get_body(preferencelist=("plain",)).get_content()


def test_list_and_get_email_integrations():
    manager, _ = _manager()
    created = _create(manager, name="Primary")

    listed = asyncio.run(manager.list_integrations())
    fetched = asyncio.run(manager.get_integration(created.id))

    assert [item.name for item in listed] == ["Primary"]
    assert fetched.id == created.id
    assert fetched.email == "alerts@example.com"


def test_get_email_integration_missing_or_invalid_id_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_integration(str(ObjectId())))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.get_integration("not-a-valid-object-id"))


def test_update_email_integration_changes_name_and_email():
    manager, _ = _manager()
    created = _create(manager, name="On-call")

    updated = asyncio.run(manager.update_integration(created.id, UpdateEmailIntegrationRequest(name="Renamed", email="ops@example.com")))

    assert updated.name == "Renamed"
    assert updated.email == "ops@example.com"


def test_update_email_integration_rejects_explicit_null_fields():
    manager, _ = _manager()
    created = _create(manager)
    with pytest.raises(ValidationError):
        asyncio.run(manager.update_integration(created.id, UpdateEmailIntegrationRequest(monitor_ids=None)))


def test_update_email_integration_missing_raises_not_found():
    manager, _ = _manager()
    with pytest.raises(NotFoundError):
        asyncio.run(manager.update_integration(str(ObjectId()), UpdateEmailIntegrationRequest(name="Nope")))


def test_delete_email_integration_and_missing_cases():
    manager, _ = _manager()
    created = _create(manager)

    asyncio.run(manager.delete_integration(created.id))

    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_integration(created.id))
    with pytest.raises(NotFoundError):
        asyncio.run(manager.delete_integration("not-a-valid-object-id"))


def test_create_validates_monitor_ids():
    manager, _ = _manager()
    with pytest.raises(ValidationError):
        _create(manager, monitor_ids=["unknown-monitor"])

    manager_with_monitor, _ = _manager(monitors=[SimpleNamespace(id="monitor-1")])
    created = _create(manager_with_monitor, monitor_ids=["monitor-1", "monitor-1"])
    assert created.monitor_ids == ["monitor-1"]


def test_smtp_settings_requires_host(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "")
    with pytest.raises(RuntimeError):
        EmailIntegrationManager._smtp_settings()


def test_smtp_settings_builds_from_environment(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    settings = EmailIntegrationManager._smtp_settings()
    assert settings.host == "smtp.example.com"
    assert settings.port == 587
    assert settings.from_email == "alerts@example.com"


def test_smtp_settings_rejects_invalid_port(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_PORT", "not-a-number")
    with pytest.raises(RuntimeError):
        EmailIntegrationManager._smtp_settings()


class FakeSMTPClient:
    created: list[FakeSMTPClient] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        FakeSMTPClient.created.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append(("send_message", message))


class RaisingSMTPClient(FakeSMTPClient):
    def login(self, username, password):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")


def _smtp_message(manager):
    now = datetime.now(UTC)
    integration = EmailIntegrationModel(name="On-call", name_key="on-call", email="alerts@example.com", monitor_ids=[], created_at=now, updated_at=now)
    monitor = SimpleNamespace(name="Public API", monitor_type=MonitorType.API)
    result = SimpleNamespace(status_code=503, response_time_ms=120)
    return integration, manager._build_message(integration, monitor, is_down=True, result=result, incident=None)


def test_send_smtp_uses_starttls_and_login(monkeypatch):
    FakeSMTPClient.created.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTPClient)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SMTP_USERNAME", "bot")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    manager, _ = _manager()
    _, message = _smtp_message(manager)

    manager._send_smtp(message)

    client = FakeSMTPClient.created[-1]
    assert client.calls[0] == "ehlo"
    assert "starttls" in client.calls
    assert ("login", "bot", "secret") in client.calls
    assert any(call[0] == "send_message" for call in client.calls if isinstance(call, tuple))
    assert "alerts@example.com" in message["From"]
    assert message["Message-ID"] is not None


def test_send_smtp_uses_ssl_client_without_login(monkeypatch):
    FakeSMTPClient.created.clear()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPClient)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    manager, _ = _manager()
    _, message = _smtp_message(manager)

    manager._send_smtp(message)

    client = FakeSMTPClient.created[-1]
    assert "starttls" not in client.calls
    assert not any(call[0] == "login" for call in client.calls if isinstance(call, tuple))
    assert any(call[0] == "send_message" for call in client.calls if isinstance(call, tuple))


def test_deliver_sends_via_smtp_when_no_sender_configured(monkeypatch):
    FakeSMTPClient.created.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTPClient)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    manager, _ = _manager()
    integration, message = _smtp_message(manager)

    manager._deliver(integration, message)

    client = FakeSMTPClient.created[-1]
    assert any(call[0] == "send_message" for call in client.calls if isinstance(call, tuple))


def test_deliver_swallows_smtp_errors(monkeypatch, caplog):
    monkeypatch.setattr(smtplib, "SMTP", RaisingSMTPClient)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "alerts@example.com")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("SMTP_USERNAME", "bot")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    manager, _ = _manager()
    integration, message = _smtp_message(manager)

    with caplog.at_level(logging.ERROR, logger="orion.uptime.email"):
        manager._deliver(integration, message)

    assert "Email notification delivery failed" in caplog.text
