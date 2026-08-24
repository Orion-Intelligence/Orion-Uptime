from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from bson import ObjectId

from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.constants.constant import Collections
from orion.services.encryption_manager.secrets import secret_box
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
