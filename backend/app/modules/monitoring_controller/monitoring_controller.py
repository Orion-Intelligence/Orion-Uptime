from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING

from app.modules.incident_manager.incident_manager import IncidentManager
from app.modules.monitoring_controller.checkers.checker_factory import CheckerFactory
from app.modules.monitoring_controller.monitor_repository import MonitorRepository
from app.modules.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from app.modules.monitoring_controller.monitor_state_manager.monitor_state_manager import MonitorStateManager
from app.service.constants import Collections
from app.service.mongo_db.shared_models.db_heartbeat_monitor_model import HeartbeatMonitorModel
from app.service.mongo_db.shared_models.db_monitor_state_model import MonitorTransition
from app.service.mongo_db.shared_models.db_monitoring_controller_model import BaseMonitorModel, HealthCheckResponse, MonitorStatus, MonitorType
from app.service.realtime import realtime_broker

if TYPE_CHECKING:
    from app.modules.api_monitor_manager.api_monitor_manager import API_monitorManager
    from app.modules.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
    from app.modules.http_monitor_manager.http_monitor_manager import HTTP_monitorManager
    from app.modules.ping_monitor_manager.ping_monitor_manager import PingMonitorManager

HTTP_STATUS_DESCRIPTION_FALLBACKS = {
    102: "The server received the request and is still processing it",
    103: "The server returned preliminary headers before the final response",
    207: "The response contains separate statuses for multiple operations",
    208: "The resource was already reported earlier in the same response",
    226: "The response represents the result of one or more instance manipulations",
    422: "The server understood the request but could not process its content",
    423: "The requested resource is locked",
    424: "The request failed because an operation it depended on also failed",
    425: "The server rejected the request because replaying it could be unsafe",
    426: "The server requires the client to switch to a different protocol",
    506: "The server has a circular content-negotiation configuration",
    507: "The server has insufficient storage to complete the request",
    508: "The server detected an infinite loop while processing the request",
    510: "The request requires additional extensions before it can be completed",
}

MonitorModel = BaseMonitorModel | HeartbeatMonitorModel
CHECK_DEADLINE_GRACE_SECONDS = 10

logger = logging.getLogger("orion.uptime.monitoring")

class MonitorManager:
    def __init__(self, http_monitor_service: HTTP_monitorManager, api_monitor_manager: API_monitorManager, ping_monitor_service: PingMonitorManager, heartbeat_monitor_service: HeartbeatMonitorManager, incident_service: IncidentManager, monitor_result_service: MonitorResultManager, monitor_state_service: MonitorStateManager, checker_factory: CheckerFactory):
        self.http_monitor_service = http_monitor_service
        self.api_monitor_service = api_monitor_manager
        self.ping_monitor_service = ping_monitor_service
        self.heartbeat_monitor_service = heartbeat_monitor_service
        self.incident_service = incident_service
        self.monitor_result_service = monitor_result_service
        self.monitor_state_service = monitor_state_service
        self.checker_factory = checker_factory
        self._monitor_services: dict[MonitorType, MonitorRepository] = {
            MonitorType.HTTP: http_monitor_service,
            MonitorType.API: api_monitor_manager,
            MonitorType.PING: ping_monitor_service,
            MonitorType.HEARTBEAT: heartbeat_monitor_service,
        }

    async def list_active_monitors(self):
        return [
            monitor
            for monitor in await self.list_monitors()
            if monitor.is_active
        ]

    async def check_and_update(self, monitor: MonitorModel) -> None:
        try:
            service = self._get_monitor_service(monitor.monitor_type)
            latest_monitor = await service.get_monitor_model(monitor.persisted_id)
            if latest_monitor is None:
                return

            if isinstance(latest_monitor, HeartbeatMonitorModel) and latest_monitor.last_heartbeat_at is None:
                return

            checker = self.checker_factory.get_checker(monitor.monitor_type)
            result = await self.run_check_with_deadline(checker, latest_monitor)
            checked_at = datetime.now(UTC)

            state_result = await self.monitor_state_service.process_result(
                monitor_id=monitor.persisted_id,
                monitor_type=monitor.monitor_type,
                success=result.success,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                checked_at=checked_at,
            )

            await self.monitor_result_service.record_result(
                monitor_id=monitor.persisted_id,
                monitor_type=monitor.monitor_type,
                status=state_result.current_status,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                success=state_result.current_status == MonitorStatus.UP,
                is_slow=result.is_slow,
            )

            await service.update_monitoring_result(
                monitor_id=monitor.persisted_id,
                status=state_result.current_status,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                checked_at=checked_at,
            )

            await self._handle_incident_transition(monitor, result, state_result)
            realtime_broker.notify("monitor", monitor.id)
        except Exception:
            logger.exception("Check for %s monitor %s could not be completed.", monitor.monitor_type, monitor.id)

    @staticmethod
    def check_deadline_seconds(monitor: MonitorModel) -> float:
        timeout = getattr(monitor, "timeout", None)
        if not isinstance(timeout, int | float) or timeout <= 0:
            return float(CHECK_DEADLINE_GRACE_SECONDS)
        return float(timeout) * 3 + CHECK_DEADLINE_GRACE_SECONDS

    @classmethod
    async def run_check_with_deadline(cls, checker, monitor: MonitorModel):
        deadline = cls.check_deadline_seconds(monitor)
        try:
            return await asyncio.wait_for(checker.check(monitor), timeout=deadline)
        except TimeoutError:
            logger.warning("Check for %s monitor %s exceeded its %.0fs deadline.", monitor.monitor_type, monitor.id, deadline)
            target = getattr(monitor, "url", None) or getattr(monitor, "host", None) or monitor.name
            return HealthCheckResponse(
                url=target,
                status=MonitorStatus.DOWN,
                status_code=None,
                response_time_ms=None,
                success=False,
                is_slow=False,
                error=f"The check did not complete within {deadline:.0f} seconds and was abandoned.",
                timed_out=True,
            )

    async def _handle_incident_transition(self, monitor: MonitorModel, result, state_result) -> None:
        if state_result.transition == MonitorTransition.DOWN:
            active = await self.incident_service.get_active_incident(monitor.persisted_id, monitor.monitor_type)
            if active is None:
                reason = self._build_incident_reason(monitor, result)
                await self.incident_service.open_incident(
                    monitor.persisted_id,
                    monitor.monitor_type,
                    reason,
                    getattr(result, "status_code", None),
                )

        elif state_result.transition == MonitorTransition.UP:
            await self.incident_service.resolve_incident(monitor.persisted_id, monitor.monitor_type)

    @classmethod
    def _build_incident_reason(cls, monitor: MonitorModel, result) -> str:
        if monitor.monitor_type == MonitorType.HEARTBEAT:
            return "Heartbeat was not received."

        if result is None:
            return "The monitor failed without producing a check result."

        status_code = getattr(result, "status_code", None)
        error = getattr(result, "error", None) or ""
        if getattr(result, "timed_out", False):
            return error or "The health check timed out before a response was received."

        if error:
            if status_code is not None:
                return f"Received HTTP {cls._http_status_details(status_code)}. {error}"
            return error

        expected_status_code = getattr(monitor, "expected_status_code", None)
        if (
            status_code is not None
            and expected_status_code is not None
            and status_code != expected_status_code
        ):
            return (
                f"Expected HTTP {cls._http_status_label(expected_status_code)}, "
                f"but received HTTP {cls._http_status_details(status_code)}."
            )

        if status_code is not None:
            return (
                f"Received HTTP {cls._http_status_details(status_code)}, but the "
                "configured response requirements were not satisfied."
            )
        return "The target could not be reached and returned no HTTP response."

    @staticmethod
    def _http_status_label(status_code: int) -> str:
        try:
            status = HTTPStatus(status_code)
        except ValueError:
            return str(status_code)
        return f"{status_code} {status.phrase}"

    @classmethod
    def _http_status_details(cls, status_code: int) -> str:
        label = cls._http_status_label(status_code)
        try:
            description = HTTPStatus(status_code).description.rstrip(".")
        except ValueError:
            description = "The target returned a non-standard HTTP status code"
        if not description:
            description = HTTP_STATUS_DESCRIPTION_FALLBACKS.get(
                status_code,
                "The target returned this HTTP status without a standard description",
            )
        return f"{label} — {description}"

    async def get_monitor(self, monitor_id: str, monitor_type: MonitorType | None = None) -> MonitorModel | None:
        if monitor_type is not None:
            return await self._get_monitor_service(monitor_type).get_monitor_model(monitor_id)
        for service in self._monitor_services.values():
            monitor = await service.get_monitor_model(monitor_id)
            if monitor is not None:
                return monitor
        return None

    async def get_monitors_with_lookup(self) -> tuple[list[MonitorModel], dict[str, MonitorModel]]:
        monitors = await self.list_monitors()

        return (
            monitors,
            {
                monitor.persisted_id: monitor
                for monitor in monitors
            },
        )

    async def list_monitors(self) -> list[MonitorModel]:
        http_monitors = await self.http_monitor_service.list_monitor_models()
        api_monitors = await self.api_monitor_service.list_monitor_models()
        ping_monitors = await self.ping_monitor_service.list_monitor_models()
        heartbeat_monitors = await self.heartbeat_monitor_service.list_monitor_models()
        return [
            *http_monitors,
            *api_monitors,
            *ping_monitors,
            *heartbeat_monitors,
        ]

    async def delete_monitor_history(self, monitor_id: str) -> None:
        await self.monitor_result_service.delete_for_monitor(monitor_id)
        await self.incident_service.delete_for_monitor(monitor_id)
        await self.monitor_state_service.delete_for_monitor(monitor_id)
        status_pages = self.monitor_result_service.collection.database[
            Collections.STATUS_PAGES
        ]
        result = await status_pages.update_many(
            {"monitor_ids": monitor_id},
            {
                "$pull": {"monitor_ids": monitor_id},
                "$set": {"updated_at": datetime.now(UTC)},
            },
        )
        if result.modified_count:
            realtime_broker.notify("status_page", None)

    async def process_heartbeat(self, monitor: HeartbeatMonitorModel) -> None:
        checked_at = datetime.now(UTC)
        await self.monitor_result_service.record_result(
            monitor_id=monitor.persisted_id,
            monitor_type=monitor.monitor_type,
            status=MonitorStatus.UP,
            status_code=None,
            response_time_ms=None,
            success=True,
            is_slow=False,
        )

        state_result = await self.monitor_state_service.process_result(
            monitor_id=monitor.persisted_id,
            monitor_type=monitor.monitor_type,
            success=True,
            status_code=None,
            response_time_ms=None,
            checked_at=checked_at,
        )

        await self.heartbeat_monitor_service.update_monitoring_result(
            monitor_id=monitor.persisted_id,
            status=state_result.current_status,
            status_code=None,
            response_time_ms=None,
            checked_at=checked_at,
        )

        await self._handle_incident_transition(
            monitor,
            None,
            state_result,
        )
        realtime_broker.notify("monitor", monitor.id)

    def _get_monitor_service(self, monitor_type: MonitorType) -> MonitorRepository:
        try:
            return self._monitor_services[monitor_type]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported monitor type: {monitor_type}"
            ) from exc

    @staticmethod
    def _heartbeat_timing_message(monitor: HeartbeatMonitorModel, received_at: datetime) -> str:
        if monitor.last_heartbeat_at is None:
            return (
                "first beat received; next beat expected in "
                f"{monitor.expected_heartbeat_interval} seconds"
            )

        elapsed_seconds = max(
            0.0,
            (received_at - monitor.last_heartbeat_at).total_seconds(),
        )
        difference = monitor.expected_heartbeat_interval - elapsed_seconds

        if difference > 0:
            return (
                f"beat received {difference:.2f} seconds earlier than the "
                f"expected {monitor.expected_heartbeat_interval}-second interval"
            )
        if difference < 0:
            return (
                f"beat received {abs(difference):.2f} seconds later than the "
                f"expected {monitor.expected_heartbeat_interval}-second interval"
            )
        return (
            "beat received exactly at the expected "
            f"{monitor.expected_heartbeat_interval}-second interval"
        )
