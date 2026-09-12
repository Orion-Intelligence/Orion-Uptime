from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from bson import ObjectId

from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.constants.constant import Collections
from orion.services.encryption_manager.secrets import secret_box
from orion.services.mongo_manager.shared_model.db_slack_integration_model import CreateSlackIntegrationRequest, SlackIntegrationModel
from tests.model.fakes import FakeCollection, FakeHttpClient, FakeMonitorService

WEBHOOK_URL = "https://hooks.slack.com/services/T000/B000/SECRET"


def _slack_manager(monitors=None):
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.SLACK_INTEGRATIONS: collection})
    return SlackIntegrationManager(engine, FakeMonitorService(monitors), client=FakeHttpClient()), collection


def _create_slack(manager, name="Orion", webhook_url=WEBHOOK_URL, monitor_ids=None):
    return asyncio.run(manager.create_integration(CreateSlackIntegrationRequest(name=name, webhook_url=webhook_url, monitor_ids=monitor_ids or [])))


def _slack_integration_document(monitor_id="monitor-1", webhook_url=WEBHOOK_URL):
    now = datetime.now(UTC)
    integration = SlackIntegrationModel(name="Ops", name_key="ops", webhook_url=webhook_url, monitor_ids=[monitor_id], created_at=now, updated_at=now)
    document = integration.model_dump(exclude={"id", "webhook_url"})
    document["webhook_url_encrypted"] = secret_box.encrypt_mapping({"webhook_url": integration.webhook_url})
    document["_id"] = ObjectId()
    return document
