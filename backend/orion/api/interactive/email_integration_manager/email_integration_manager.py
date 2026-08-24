from __future__ import annotations

import asyncio
import logging
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import TYPE_CHECKING

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from odmantic import AIOEngine
from pymongo.errors import DuplicateKeyError

from orion.constants.constant import Collections
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_email_integration_model import CreateEmailIntegrationRequest, EmailIntegrationModel, EmailIntegrationResponse, UpdateEmailIntegrationRequest
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager, MonitorModel
    from orion.services.mongo_manager.shared_model.db_incident_model import IncidentModel
    from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorStateResult

logger = logging.getLogger("orion.uptime.email")

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\.[A-Za-z]{2,63}$")
MAX_NAME_LENGTH = 100
SMTP_SECURITY_VALUES = {"none", "starttls", "ssl"}


@dataclass(frozen=True, slots=True)
class SMTPSettings:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str


class EmailIntegrationManager:
    def __init__(self, engine: AIOEngine, monitor_service: MonitorManager, sender: Callable[[EmailMessage], None] | None = None) -> None:
        self.collection = engine.database[Collections.EMAIL_INTEGRATIONS]
        self.monitor_service = monitor_service
        self.sender = sender

    async def create_integration(self, request: CreateEmailIntegrationRequest) -> EmailIntegrationResponse:
        base_name = self._validated_name(request.name)
        email = self._validated_email(request.email)
        monitor_ids = await self._validated_monitor_ids(request.monitor_ids)
        now = datetime.now(UTC)
        suffix = 0

        while True:
            name = await self._unique_name(base_name, suffix=suffix)
            integration = EmailIntegrationModel(name=name, name_key=self._name_key(name), email=email, monitor_ids=monitor_ids, created_at=now, updated_at=now)
            try:
                result = await self.collection.insert_one(integration.model_dump(exclude={"id"}))
                break
            except DuplicateKeyError:
                suffix += 1

        integration.id = str(result.inserted_id)
        realtime_broker.notify("email_integration", integration.id)
        return self._response(integration)

    async def list_integrations(self) -> list[EmailIntegrationResponse]:
        return [self._response(integration) for integration in await self.list_integration_models()]

    async def list_integration_models(self) -> list[EmailIntegrationModel]:
        integrations = []
        async for document in self.collection.find().sort("created_at", -1):
            integrations.append(EmailIntegrationModel(**with_string_id(document)))
        return integrations

    async def get_integration(self, integration_id: str) -> EmailIntegrationResponse:
        integration = await self.get_integration_model(integration_id)
        if integration is None:
            raise NotFoundError("Email integration not found.")
        return self._response(integration)

    async def get_integration_model(self, integration_id: str) -> EmailIntegrationModel | None:
        object_id = self._object_id(integration_id)
        if object_id is None:
            return None
        document = await self.collection.find_one({"_id": object_id})
        return EmailIntegrationModel(**with_string_id(document)) if document is not None else None

    async def update_integration(self, integration_id: str, request: UpdateEmailIntegrationRequest) -> EmailIntegrationResponse:
        object_id = self._object_id(integration_id)
        integration = await self.get_integration_model(integration_id)
        if object_id is None or integration is None:
            raise NotFoundError("Email integration not found.")

        update_data = request.model_dump(exclude_unset=True)
        invalid_null_fields = [field for field, value in update_data.items() if value is None]
        if invalid_null_fields:
            raise ValidationError(f"Email integration fields cannot be null: {', '.join(sorted(invalid_null_fields))}.")

        requested_name = None
        if "name" in update_data:
            requested_name = self._validated_name(update_data.pop("name"))
        if "email" in update_data:
            update_data["email"] = self._validated_email(update_data["email"])
        if "monitor_ids" in update_data:
            update_data["monitor_ids"] = await self._validated_monitor_ids(update_data["monitor_ids"])

        if requested_name is not None:
            suffix = 0
            while True:
                name = await self._unique_name(requested_name, exclude_id=object_id, suffix=suffix)
                named_update = {**update_data, "name": name, "name_key": self._name_key(name), "updated_at": datetime.now(UTC)}
                try:
                    await self.collection.update_one({"_id": object_id}, {"$set": named_update})
                    break
                except DuplicateKeyError:
                    suffix += 1
        elif update_data:
            update_data["updated_at"] = datetime.now(UTC)
            await self.collection.update_one({"_id": object_id}, {"$set": update_data})

        updated = await self.get_integration_model(integration_id)
        if updated is None:
            raise NotFoundError("Email integration not found.")
        realtime_broker.notify("email_integration", updated.id)
        return self._response(updated)

    async def delete_integration(self, integration_id: str) -> None:
        object_id = self._object_id(integration_id)
        if object_id is None:
            raise NotFoundError("Email integration not found.")
        result = await self.collection.delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise NotFoundError("Email integration not found.")
        realtime_broker.notify("email_integration", integration_id)

    async def notify_transition(self, monitor: MonitorModel, result, state_result: MonitorStateResult, incident: IncidentModel | None = None) -> None:
        is_down = state_result.transition == MonitorTransition.DOWN
        is_recovery = state_result.transition == MonitorTransition.UP and state_result.previous_status == MonitorStatus.DOWN
        if not is_down and not is_recovery:
            return

        integrations = []
        async for document in self.collection.find({"monitor_ids": monitor.persisted_id}):
            integrations.append(EmailIntegrationModel(**with_string_id(document)))
        if not integrations:
            return

        await asyncio.gather(*(asyncio.to_thread(self._deliver, integration, self._build_message(integration, monitor, is_down=is_down, result=result, incident=incident)) for integration in integrations))

    def _deliver(self, integration: EmailIntegrationModel, message: EmailMessage) -> None:
        try:
            if self.sender is not None:
                self.sender(message)
            else:
                self._send_smtp(message)
        except (OSError, RuntimeError, smtplib.SMTPException, ValueError):
            logger.exception("Email notification delivery failed for integration %s.", integration.name)

    @staticmethod
    def _build_message(integration: EmailIntegrationModel, monitor: MonitorModel, *, is_down: bool, result, incident: IncidentModel | None) -> EmailMessage:
        state = "DOWN" if is_down else "RECOVERED"
        root_cause = incident.reason if incident is not None else "The monitor check failed without an incident record."
        status_code = incident.status_code if incident is not None else getattr(result, "status_code", None)
        response_time_ms = getattr(result, "response_time_ms", None)
        lines = [
            f"Monitor: {monitor.name}",
            f"State: {state}",
            f"Type: {monitor.monitor_type.value}",
            f"Root cause: {root_cause}",
        ]
        if monitor.monitor_type in (MonitorType.HTTP, MonitorType.API):
            lines.append(f"Status code: {status_code if status_code is not None else 'No response'}")
        if response_time_ms is not None:
            lines.append(f"Response time: {response_time_ms} ms")
        lines.extend(
            [
                f"Incident started: {EmailIntegrationManager._timestamp(incident.started_at if incident is not None else None)}",
                f"Resolved: {EmailIntegrationManager._timestamp(incident.resolved_at if incident is not None else None, ongoing=is_down)}",
                "",
                "This notification was sent by Orion Uptime.",
            ]
        )
        message = EmailMessage()
        message["To"] = integration.email
        message["Subject"] = f"[Orion Uptime] {monitor.name} is {state}"
        message.set_content("\n".join(lines))
        return message

    def _send_smtp(self, message: EmailMessage) -> None:
        settings = self._smtp_settings()
        message["From"] = formataddr((settings.from_name, settings.from_email))
        message["Date"] = format_datetime(datetime.now(UTC))
        message["Message-ID"] = make_msgid(domain=settings.from_email.rsplit("@", 1)[1])
        client_type = smtplib.SMTP_SSL if settings.security == "ssl" else smtplib.SMTP
        with client_type(settings.host, settings.port, timeout=10) as client:
            client.ehlo()
            if settings.security == "starttls":
                client.starttls(context=ssl.create_default_context())
                client.ehlo()
            if settings.username:
                client.login(settings.username, settings.password)
            client.send_message(message)

    @classmethod
    def _smtp_settings(cls) -> SMTPSettings:
        load_dotenv()
        host = os.environ.get("SMTP_HOST", "").strip()
        username = os.environ.get("SMTP_USERNAME", "").strip()
        raw_from_email = os.environ.get("SMTP_FROM_EMAIL", "").strip() or username
        security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
        if not host:
            raise RuntimeError("SMTP_HOST is not configured.")
        if not raw_from_email:
            raise RuntimeError("SMTP_FROM_EMAIL or SMTP_USERNAME must be configured.")
        try:
            from_email = cls._validated_email(raw_from_email)
        except ValidationError as exc:
            raise RuntimeError("SMTP_FROM_EMAIL must be a valid email address.") from exc
        if security not in SMTP_SECURITY_VALUES:
            raise RuntimeError("SMTP_SECURITY must be one of: none, starttls, ssl.")
        try:
            port = int(os.environ.get("SMTP_PORT", "587"))
        except ValueError as exc:
            raise RuntimeError("SMTP_PORT must be a number.") from exc
        if port < 1 or port > 65535:
            raise RuntimeError("SMTP_PORT must be between 1 and 65535.")
        return SMTPSettings(host=host, port=port, security=security, username=username, password=os.environ.get("SMTP_PASSWORD", ""), from_email=from_email, from_name=os.environ.get("SMTP_FROM_NAME", "Orion Uptime").strip() or "Orion Uptime")

    async def _validated_monitor_ids(self, monitor_ids: list[str]) -> list[str]:
        unique_ids = list(dict.fromkeys(monitor_ids))
        available_ids = {monitor.id for monitor in await self.monitor_service.list_monitors() if monitor.id is not None}
        missing = [monitor_id for monitor_id in unique_ids if monitor_id not in available_ids]
        if missing:
            raise ValidationError(f"Unknown monitor IDs: {', '.join(missing)}")
        return unique_ids

    async def _unique_name(self, base_name: str, exclude_id: ObjectId | None = None, suffix: int = 0) -> str:
        while True:
            candidate = self._candidate_name(base_name, suffix)
            query: dict = {"name_key": self._name_key(candidate)}
            if exclude_id is not None:
                query["_id"] = {"$ne": exclude_id}
            if await self.collection.find_one(query, {"_id": 1}) is None:
                return candidate
            suffix += 1

    @staticmethod
    def _candidate_name(base_name: str, suffix: int) -> str:
        suffix_text = "" if suffix == 0 else str(suffix)
        return f"{base_name[: MAX_NAME_LENGTH - len(suffix_text)]}{suffix_text}"

    @staticmethod
    def _name_key(name: str) -> str:
        return name.casefold()

    @staticmethod
    def _validated_name(name: str | None) -> str:
        clean_name = name.strip() if name is not None else ""
        if not clean_name or "\r" in clean_name or "\n" in clean_name:
            raise ValidationError("Integration name is required and must be on one line.")
        return clean_name

    @staticmethod
    def _validated_email(email: str | None) -> str:
        clean_email = email.strip().lower() if email is not None else ""
        if len(clean_email) > 320 or EMAIL_PATTERN.fullmatch(clean_email) is None:
            raise ValidationError("Enter a valid recipient email address.")
        return clean_email

    @staticmethod
    def _timestamp(value: datetime | None, *, ongoing: bool = False) -> str:
        if value is None:
            return "Ongoing" if ongoing else "Unavailable"
        aware_value = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        utc_value = aware_value.astimezone(UTC)
        hour = utc_value.strftime("%I").lstrip("0") or "0"
        return f"{utc_value:%b %d, %Y}, {hour}:{utc_value:%M:%S %p UTC}"

    @staticmethod
    def _response(integration: EmailIntegrationModel) -> EmailIntegrationResponse:
        return EmailIntegrationResponse(id=integration.persisted_id, name=integration.name, email=integration.email, monitor_ids=integration.monitor_ids, monitor_count=len(integration.monitor_ids), created_at=integration.created_at, updated_at=integration.updated_at)

    @staticmethod
    def _object_id(value: str) -> ObjectId | None:
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return None
