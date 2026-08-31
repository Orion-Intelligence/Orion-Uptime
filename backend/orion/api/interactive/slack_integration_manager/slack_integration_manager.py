from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import InvalidToken
from odmantic import AIOEngine
from pymongo.errors import DuplicateKeyError

from orion.api.interactive.integration_shared.integration_collection import IntegrationCollectionMixin
from orion.constants.constant import AllowedValues, Collections
from orion.services.encryption_manager.secrets import secret_box
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_slack_integration_model import CreateSlackIntegrationRequest, SlackIntegrationModel, SlackIntegrationResponse, SlackIntegrationSummaryResponse, UpdateSlackIntegrationRequest
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager, MonitorModel
    from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
    from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorStateResult

logger = logging.getLogger("orion.uptime.slack")



class SlackIntegrationManager(IntegrationCollectionMixin):
    not_found_message = "Slack integration not found."
    realtime_channel = "slack_integration"

    def __init__(self, engine: AIOEngine, monitor_service: MonitorManager, client: httpx.AsyncClient | None = None) -> None:
        self.collection = engine.database[Collections.SLACK_INTEGRATIONS]
        self.monitor_service = monitor_service
        self.client = client or httpx.AsyncClient(follow_redirects=False, timeout=10)
        self._owns_client = client is None

    async def create_integration(self, request: CreateSlackIntegrationRequest) -> SlackIntegrationResponse:
        base_name = self._validated_name(request.name)
        webhook_url = self._validated_webhook_url(request.webhook_url)
        monitor_ids = await self._validated_monitor_ids(request.monitor_ids)
        now = datetime.now(UTC)
        suffix = 0

        while True:
            name = await self._unique_name(base_name, suffix=suffix)
            integration = SlackIntegrationModel(name=name, name_key=self._name_key(name), webhook_url=webhook_url, monitor_ids=monitor_ids, created_at=now, updated_at=now)
            try:
                result = await self.collection.insert_one(self._serialize(integration))
                break
            except DuplicateKeyError:
                suffix += 1

        integration.id = str(result.inserted_id)
        realtime_broker.notify("slack_integration", integration.id)
        return self._detail_response(integration)

    async def list_integrations(self) -> list[SlackIntegrationSummaryResponse]:
        integrations = []
        async for document in self.collection.find({}, {"webhook_url_encrypted": 0}).sort("created_at", -1):
            data = with_string_id(document)
            integrations.append(SlackIntegrationSummaryResponse(id=data["id"], name=data["name"], monitor_ids=data.get("monitor_ids", []), monitor_count=len(data.get("monitor_ids", [])), created_at=data["created_at"], updated_at=data["updated_at"]))
        return integrations

    async def list_integration_models(self) -> list[SlackIntegrationModel]:
        integrations = []
        async for document in self.collection.find().sort("created_at", -1):
            integrations.append(self._deserialize(document))
        return integrations

    async def get_integration(self, integration_id: str) -> SlackIntegrationResponse:
        integration = await self.get_integration_model(integration_id)
        if integration is None:
            raise NotFoundError("Slack integration not found.")
        return self._detail_response(integration)

    async def get_integration_model(self, integration_id: str) -> SlackIntegrationModel | None:
        object_id = self._object_id(integration_id)
        if object_id is None:
            return None
        document = await self.collection.find_one({"_id": object_id})
        return self._deserialize(document) if document is not None else None

    async def update_integration(self, integration_id: str, request: UpdateSlackIntegrationRequest) -> SlackIntegrationResponse:
        object_id = self._object_id(integration_id)
        integration = await self.get_integration_model(integration_id)
        if object_id is None or integration is None:
            raise NotFoundError("Slack integration not found.")

        update_data = request.model_dump(exclude_unset=True)
        invalid_null_fields = [field for field, value in update_data.items() if value is None]
        if invalid_null_fields:
            raise ValidationError(f"Slack integration fields cannot be null: {', '.join(sorted(invalid_null_fields))}.")

        requested_name = None
        if "name" in update_data:
            requested_name = self._validated_name(update_data.pop("name"))
        if "webhook_url" in update_data:
            webhook_url = self._validated_webhook_url(update_data.pop("webhook_url"))
            update_data["webhook_url_encrypted"] = secret_box.encrypt_mapping({"webhook_url": webhook_url})
        if "monitor_ids" in update_data:
            update_data["monitor_ids"] = await self._validated_monitor_ids(update_data["monitor_ids"])

        await self._apply_update(object_id, update_data, requested_name)

        updated = await self.get_integration_model(integration_id)
        if updated is None:
            raise NotFoundError("Slack integration not found.")
        realtime_broker.notify("slack_integration", updated.id)
        return self._detail_response(updated)


    async def notify_transition(self, monitor: MonitorModel, result, state_result: MonitorStateResult, incident: IncidentModel | None = None) -> None:
        is_down = state_result.transition == MonitorTransition.DOWN
        is_recovery = state_result.transition == MonitorTransition.UP and state_result.previous_status == MonitorStatus.DOWN
        if not is_down and not is_recovery:
            return

        integrations = []
        async for document in self.collection.find({"monitor_ids": monitor.persisted_id}):
            try:
                integrations.append(self._deserialize(document))
            except (InvalidToken, KeyError, RuntimeError, ValueError):
                logger.exception("A Slack integration could not be loaded for notification delivery.")
        if not integrations:
            return

        payload = self._notification_payload(monitor, is_down=is_down, result=result, incident=incident)
        await asyncio.gather(*(self._deliver(integration, payload) for integration in integrations))

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _deliver(self, integration: SlackIntegrationModel, payload: dict) -> None:
        try:
            response = await self.client.post(integration.webhook_url, json=payload)
            response.raise_for_status()
        except (httpx.HTTPError, RuntimeError, ValueError):
            logger.exception("Slack notification delivery failed for integration %s.", integration.name)

    @staticmethod
    def _validated_name(name: str | None) -> str:
        clean_name = name.strip() if name is not None else ""
        if not clean_name:
            raise ValidationError("Integration name is required.")
        return clean_name

    @staticmethod
    def _validated_webhook_url(webhook_url: str | None) -> str:
        clean_url = webhook_url.strip() if webhook_url is not None else ""
        try:
            parsed = urlsplit(clean_url)
            path_parts = [part for part in parsed.path.split("/") if part]
            valid = parsed.scheme == "https" and parsed.hostname in AllowedValues.SLACK_WEBHOOK_HOSTS and parsed.port is None and parsed.username is None and parsed.password is None and len(path_parts) == 4 and path_parts[0] == "services" and not parsed.query and not parsed.fragment
        except ValueError:
            valid = False
        if not valid:
            raise ValidationError("Enter a valid Slack incoming webhook URL from hooks.slack.com.")
        return clean_url

    @staticmethod
    def _notification_payload(monitor: MonitorModel, *, is_down: bool, result, incident: IncidentModel | None) -> dict:
        state = "DOWN" if is_down else "RECOVERED"
        icon = ":red_circle:" if is_down else ":large_green_circle:"
        root_cause = incident.reason if incident is not None else "The monitor check failed without an incident record."
        status_code = incident.status_code if incident is not None else getattr(result, "status_code", None)
        response_time_ms = getattr(result, "response_time_ms", None)
        fields = [
            f"*Type:* {monitor.monitor_type.value}",
            f"*Incident started:* {SlackIntegrationManager._slack_timestamp(incident.started_at if incident is not None else None)}",
            f"*Resolved:* {SlackIntegrationManager._slack_timestamp(incident.resolved_at if incident is not None else None, ongoing=is_down)}",
        ]
        if monitor.monitor_type in (MonitorType.HTTP, MonitorType.API):
            fields.insert(1, f"*Status code:* {status_code if status_code is not None else 'No response'}")
        if response_time_ms is not None:
            fields.append(f"*Response time:* {response_time_ms} ms")
        escaped_name = SlackIntegrationManager._escape_slack(monitor.name)
        escaped_root_cause = SlackIntegrationManager._escape_slack(root_cause[:2400])
        title = f"{icon} {escaped_name} is {state}"
        return {
            "text": f"Orion Uptime alert: {escaped_name} is {state}.",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\n*Root cause:* {escaped_root_cause}"}},
                {"type": "section", "fields": [{"type": "mrkdwn", "text": value} for value in fields]},
            ],
        }

    @staticmethod
    def _slack_timestamp(value: datetime | None, *, ongoing: bool = False) -> str:
        if value is None:
            return "Ongoing" if ongoing else "Unavailable"
        fallback = value.isoformat()
        return f"<!date^{int(value.timestamp())}^{{date_short_pretty}} at {{time}}|{fallback}>"

    @staticmethod
    def _escape_slack(value: str) -> str:
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _serialize(integration: SlackIntegrationModel) -> dict:
        document = integration.model_dump(exclude={"id", "webhook_url"})
        document["webhook_url_encrypted"] = secret_box.encrypt_mapping({"webhook_url": integration.webhook_url})
        return document

    @staticmethod
    def _deserialize(document: dict) -> SlackIntegrationModel:
        data = with_string_id(document)
        encrypted = data.pop("webhook_url_encrypted", None)
        if encrypted is None:
            raise RuntimeError("Slack integration webhook is not encrypted.")
        data["webhook_url"] = secret_box.decrypt_mapping(encrypted)["webhook_url"]
        return SlackIntegrationModel(**data)

    @staticmethod
    def _summary_response(integration: SlackIntegrationModel) -> SlackIntegrationSummaryResponse:
        return SlackIntegrationSummaryResponse(id=integration.persisted_id, name=integration.name, monitor_ids=integration.monitor_ids, monitor_count=len(integration.monitor_ids), created_at=integration.created_at, updated_at=integration.updated_at)

    @classmethod
    def _detail_response(cls, integration: SlackIntegrationModel) -> SlackIntegrationResponse:
        return SlackIntegrationResponse(**cls._summary_response(integration).model_dump(), webhook_url=integration.webhook_url)
