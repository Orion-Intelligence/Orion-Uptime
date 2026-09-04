from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from odmantic import AIOEngine
from pymongo.errors import DuplicateKeyError

from orion.api.interactive.integration_shared.integration_collection import IntegrationCollectionMixin
from orion.constants.constant import AllowedValues, Collections, Patterns
from orion.services.email_template_manager import EMAIL_INTEGRATION_ALERT_TEMPLATE, EmailTemplateManager
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



@dataclass(frozen=True, slots=True)
class SMTPSettings:
    host: str
    port: int
    security: str
    username: str
    password: str
    from_email: str
    from_name: str


class EmailIntegrationManager(IntegrationCollectionMixin):
    not_found_message = "Email integration not found."
    realtime_channel = "email_integration"

    def __init__(
        self,
        engine: AIOEngine,
        monitor_service: MonitorManager,
        sender: Callable[[EmailMessage], None] | None = None,
        template_manager: EmailTemplateManager | None = None,
    ) -> None:

        self.collection = engine.database[Collections.EMAIL_INTEGRATIONS]
        self.monitor_service = monitor_service
        self.sender = sender
        self.template_manager = template_manager or EmailTemplateManager.get_instance()

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

        await self._apply_update(object_id, update_data, requested_name)

        updated = await self.get_integration_model(integration_id)
        if updated is None:
            raise NotFoundError("Email integration not found.")
        realtime_broker.notify("email_integration", updated.id)
        return self._response(updated)


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

    def _build_message(self, integration: EmailIntegrationModel, monitor: MonitorModel, *, is_down: bool, result, incident: IncidentModel | None) -> EmailMessage:
        state = "DOWN" if is_down else "RECOVERED"
        root_cause = incident.reason if incident is not None else "The monitor check failed without an incident record."
        status_code = incident.status_code if incident is not None else getattr(result, "status_code", None)
        response_time_ms = getattr(result, "response_time_ms", None)
        incident_started = EmailIntegrationManager._timestamp(incident.started_at if incident is not None else None)
        resolved = EmailIntegrationManager._timestamp(incident.resolved_at if incident is not None else None, ongoing=is_down)
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
                f"Incident started: {incident_started}",
                f"Resolved: {resolved}",
                "",
                "This notification was sent by Orion Uptime.",
            ]
        )
        message = EmailMessage()
        message["To"] = integration.email
        message["Subject"] = f"[Orion Uptime] {monitor.name} is {state}"
        message.set_content("\n".join(lines))
        message.add_alternative(
            self._html_body(
                monitor_name=monitor.name,
                monitor_type=monitor.monitor_type,
                is_down=is_down,
                root_cause=root_cause,
                status_code=status_code,
                response_time_ms=response_time_ms,
                incident_started=incident_started,
                resolved=resolved,
            ),
            subtype="html",
        )
        return message

    def _html_body(self, *, monitor_name: str, monitor_type: MonitorType, is_down: bool, root_cause: str, status_code: int | None, response_time_ms: int | float | None, incident_started: str, resolved: str) -> str:
        state = "DOWN" if is_down else "RECOVERED"
        return self.template_manager.render(
            EMAIL_INTEGRATION_ALERT_TEMPLATE,
            is_down=is_down,
            monitor_name=monitor_name,
            state=state,
            monitor_type=monitor_type.value,
            show_status_code=monitor_type in (MonitorType.HTTP, MonitorType.API),
            status_code=str(status_code) if status_code is not None else "No response",
            response_time=f"{response_time_ms} ms" if response_time_ms is not None else None,
            incident_started=incident_started,
            resolved=resolved,
            root_cause=root_cause,
        )

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
        if security not in AllowedValues.SMTP_SECURITY:
            raise RuntimeError("SMTP_SECURITY must be one of: none, starttls, ssl.")
        try:
            port = int(os.environ.get("SMTP_PORT", "587"))
        except ValueError as exc:
            raise RuntimeError("SMTP_PORT must be a number.") from exc
        if port < 1 or port > 65535:
            raise RuntimeError("SMTP_PORT must be between 1 and 65535.")
        return SMTPSettings(host=host, port=port, security=security, username=username, password=os.environ.get("SMTP_PASSWORD", ""), from_email=from_email, from_name=os.environ.get("SMTP_FROM_NAME", "Orion Uptime").strip() or "Orion Uptime")

    @staticmethod
    def _validated_name(name: str | None) -> str:
        clean_name = name.strip() if name is not None else ""
        if not clean_name or "\r" in clean_name or "\n" in clean_name:
            raise ValidationError("Integration name is required and must be on one line.")
        return clean_name

    @staticmethod
    def _validated_email(email: str | None) -> str:
        clean_email = email.strip().lower() if email is not None else ""
        if len(clean_email) > 320 or Patterns.EMAIL.fullmatch(clean_email) is None:
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
