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
from html import escape
from string import Template
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
            EmailIntegrationManager._html_body(
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

    @staticmethod
    def _html_body(*, monitor_name: str, monitor_type: MonitorType, is_down: bool, root_cause: str, status_code: int | None, response_time_ms: int | float | None, incident_started: str, resolved: str) -> str:
        state = "DOWN" if is_down else "RECOVERED"
        heading = "Monitor is down" if is_down else "Monitor recovered"
        summary = "Orion detected an availability incident that needs attention." if is_down else "Orion confirmed that the monitor is responding again."
        badge = "Incident open" if is_down else "Incident resolved"
        accent = "#f97066" if is_down else "#34d399"
        status_background = "#fff2f0" if is_down else "#effbf6"
        status_color = "#b42318" if is_down else "#16825f"
        icon = "!" if is_down else "&#10003;"
        details = [
            ("Monitor", monitor_name),
            ("State", state),
            ("Type", monitor_type.value),
        ]
        if monitor_type in (MonitorType.HTTP, MonitorType.API):
            details.append(("Status code", str(status_code) if status_code is not None else "No response"))
        if response_time_ms is not None:
            details.append(("Response time", f"{response_time_ms} ms"))
        details.extend([("Incident started", incident_started), ("Resolved", resolved)])
        detail_rows = "".join(
            f'<tr><td class="detail-label text-slate-500" style="width:42%;padding:12px 16px;border-bottom:1px solid #e3ebf3;color:#5f738f;font-size:12px;font-weight:500;vertical-align:top;">{escape(label)}</td><td class="detail-value text-slate-900" style="padding:12px 16px;border-bottom:1px solid #e3ebf3;color:#142033;font-size:13px;font-weight:600;line-height:1.5;vertical-align:top;word-break:break-word;">{escape(value)}</td></tr>'
            for label, value in details
        )

        return Template(
            """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <meta name="supported-color-schemes" content="light">
    <title>Orion Uptime monitor alert</title>
    <style>
      /* Tailwind utility styles are inlined below for email-client compatibility. */
      body { margin: 0; padding: 0; width: 100% !important; background: #f5f8fc; }
      table { border-spacing: 0; border-collapse: collapse; }
      img { border: 0; display: block; }
      @media only screen and (max-width: 620px) {
        .email-shell { width: 100% !important; border-radius: 0 !important; }
        .email-padding { padding-left: 20px !important; padding-right: 20px !important; }
        .detail-label, .detail-value { display: block !important; width: auto !important; }
        .detail-label { padding-bottom: 3px !important; border-bottom: 0 !important; }
        .detail-value { padding-top: 3px !important; }
      }
    </style>
  </head>
  <body class="bg-slate-50 font-sans text-slate-900" style="margin:0;padding:0;background-color:#f5f8fc;color:#142033;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">$preheader</div>
    <table role="presentation" width="100%" style="width:100%;background-color:#f5f8fc;">
      <tr>
        <td align="center" style="padding:34px 12px;">
          <table role="presentation" width="600" class="email-shell mx-auto max-w-xl overflow-hidden rounded-2xl bg-white" style="width:600px;max-width:600px;overflow:hidden;border:1px solid #d7e2ef;border-radius:16px;background-color:#ffffff;box-shadow:0 10px 30px rgba(30,64,105,0.08);">
            <tr>
              <td class="email-padding bg-slate-900" style="padding:22px 30px;background-color:#172235;">
                <table role="presentation" width="100%">
                  <tr>
                    <td style="vertical-align:middle;">
                      <table role="presentation">
                        <tr>
                          <td style="vertical-align:middle;"><span style="display:inline-block;width:11px;height:11px;border:3px solid #57a5eb;border-radius:999px;"></span></td>
                          <td style="padding-left:10px;color:#ffffff;font-size:17px;font-weight:700;letter-spacing:-0.02em;vertical-align:middle;">Orion Uptime</td>
                        </tr>
                      </table>
                    </td>
                    <td align="right" style="color:#a0b8d1;font-size:10px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;vertical-align:middle;">Monitor alert</td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td class="email-padding" style="padding:30px;">
                <table role="presentation" width="100%" class="rounded-xl" style="width:100%;border:1px solid $status_border;border-radius:12px;background-color:$status_background;">
                  <tr>
                    <td style="padding:20px;">
                      <table role="presentation" width="100%">
                        <tr>
                          <td width="44" style="width:44px;vertical-align:top;">
                            <span style="display:inline-block;width:36px;height:36px;border-radius:999px;background-color:$accent;color:#ffffff;font-size:20px;font-weight:700;line-height:36px;text-align:center;">$icon</span>
                          </td>
                          <td style="padding-left:4px;vertical-align:top;">
                            <span class="inline-flex rounded-full px-2 py-1 text-xs font-semibold" style="display:inline-block;padding:4px 9px;border-radius:999px;background-color:$badge_background;color:$status_color;font-size:10px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;">$badge</span>
                            <h1 class="text-2xl font-semibold tracking-tight" style="margin:10px 0 6px;color:#142033;font-size:24px;line-height:1.2;font-weight:650;letter-spacing:-0.025em;">$heading</h1>
                            <p class="text-sm text-slate-600" style="margin:0;color:#5f738f;font-size:13px;line-height:1.6;">$summary</p>
                          </td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>

                <p class="text-xs font-semibold uppercase text-blue-600" style="margin:26px 0 9px;color:#1176d4;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">Monitor details</p>
                <table role="presentation" width="100%" class="overflow-hidden rounded-xl border border-slate-200 bg-white" style="width:100%;overflow:hidden;border:1px solid #d7e2ef;border-radius:12px;background-color:#ffffff;">
                  $detail_rows
                </table>

                <p class="text-xs font-semibold uppercase text-blue-600" style="margin:26px 0 9px;color:#1176d4;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">Root cause</p>
                <p style="margin:0;font-size:13px;line-height:1.65;word-break:break-word;">$root_cause</p>
              </td>
            </tr>
            <tr>
              <td class="email-padding" style="padding:18px 30px;border-top:1px solid #d7e2ef;background-color:#f9fbff;color:#71869c;font-size:11px;line-height:1.6;text-align:center;">
                This notification was sent by <strong style="color:#344054;font-weight:600;">Orion Uptime</strong>.<br>
                Alerts are sent only when an assigned monitor changes state.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
        ).substitute(
            preheader=escape(f"{monitor_name} is {state}"),
            status_border="#fecaca" if is_down else "#bbf7d0",
            status_background=status_background,
            accent=accent,
            icon=icon,
            badge_background="#fee2e2" if is_down else "#dcfce7",
            status_color=status_color,
            badge=badge,
            heading=heading,
            summary=summary,
            detail_rows=detail_rows,
            root_cause=escape(root_cause),
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
