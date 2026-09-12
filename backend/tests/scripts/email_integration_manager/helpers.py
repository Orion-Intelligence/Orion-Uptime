from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.email_integration_manager.email_integration_manager import EmailIntegrationManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_email_integration_model import CreateEmailIntegrationRequest, EmailIntegrationModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from tests.model.fakes import FakeCollection, FakeMonitorService


def _manager(monitors=None):
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.EMAIL_INTEGRATIONS: collection})
    return EmailIntegrationManager(engine, FakeMonitorService(monitors)), collection


def _create(manager, name="On-call", email="alerts@example.com", monitor_ids=None):
    return asyncio.run(manager.create_integration(CreateEmailIntegrationRequest(name=name, email=email, monitor_ids=monitor_ids or [])))


def _smtp_message(manager):
    now = datetime.now(UTC)
    integration = EmailIntegrationModel(name="On-call", name_key="on-call", email="alerts@example.com", monitor_ids=[], created_at=now, updated_at=now)
    monitor = SimpleNamespace(name="Public API", monitor_type=MonitorType.API)
    result = SimpleNamespace(status_code=503, response_time_ms=120)
    return integration, manager._build_message(integration, monitor, is_down=True, result=result, incident=None)
