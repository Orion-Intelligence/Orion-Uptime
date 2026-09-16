import asyncio
import logging
import os
import signal
from contextlib import suppress
from datetime import UTC, datetime
from typing import NamedTuple

from fastapi.encoders import jsonable_encoder

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.api.interactive.api_monitor_manager.api_monitor_manager import ApiMonitorManager
from orion.api.interactive.auth_manager.auth_manager import password_service
from orion.api.interactive.email_integration_manager.email_integration_manager import EmailIntegrationManager
from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.api.interactive.incident_manager.incident_manager import IncidentManager
from orion.api.interactive.insight_manager.insight_manager import DashboardManager
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager
from orion.api.interactive.orion_script_monitor_manager.orion_script_monitor_manager import OrionScriptMonitorManager
from orion.api.interactive.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.api.interactive.status_page_manager.status_page_manager import StatusPageManager
from orion.api.interactive.user_account_manager.user_account_manager import UserManager
from orion.constants.constant import Intervals
from orion.management.jobs.monitoring_controller.checkers.checker_factory import CheckerFactory
from orion.management.jobs.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from orion.management.jobs.monitoring_controller.monitor_state_manager.monitor_state_manager import MonitorStateManager
from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager
from orion.management.jobs.monitoring_controller.scheduler import MonitorScheduler
from orion.services.email_template_manager import EmailTemplateManager
from orion.services.mongo_manager.mongo_controller import db_manager
from orion.services.realtime_manager.realtime import realtime_broker
from orion.services.realtime_manager.realtime_bus import BUS_MONGO, MongoRealtimeBus, bus_mode

logger = logging.getLogger("orion.uptime")



class Services(NamedTuple):
    auth_profile_service: AuthProfileManager
    http_monitor_service: HttpMonitorManager
    api_monitor_manager: ApiMonitorManager
    ping_monitor_service: PingMonitorManager
    heartbeat_monitor_service: HeartbeatMonitorManager
    orion_script_monitor_service: OrionScriptMonitorManager
    user_service: UserManager
    checker_factory: CheckerFactory
    monitor_service: MonitorManager
    dashboard_service: DashboardManager
    status_page_service: StatusPageManager
    slack_integration_service: SlackIntegrationManager
    email_integration_service: EmailIntegrationManager


def terminate_process(reason: str) -> None:
    logger.critical("%s Terminating so the container restarts.", reason)
    os.kill(os.getpid(), signal.SIGTERM)


async def scheduler_watchdog(scheduler: MonitorScheduler, interval: float = Intervals.WATCHDOG_INTERVAL_SECONDS) -> None:
    while True:
        await asyncio.sleep(interval)
        if scheduler.running and scheduler.last_reconcile_at is not None and not scheduler.is_healthy(Intervals.SCHEDULER_STALL_SECONDS * 2):
            terminate_process(f"The monitor scheduler has not reconciled for more than {Intervals.SCHEDULER_STALL_SECONDS * 2} seconds.")
            return


class ServiceManager:
    __instance: "ServiceManager | None" = None

    @staticmethod
    def get_instance() -> "ServiceManager":
        if ServiceManager.__instance is None:
            ServiceManager.__instance = ServiceManager()
        return ServiceManager.__instance

    def __init__(self):
        self.services: Services | None = None
        self.scheduler_task: asyncio.Task | None = None
        self.watchdog_task: asyncio.Task | None = None
        self.realtime_bus = None

    async def init_services(self) -> Services:
        EmailTemplateManager.get_instance().initialize()
        await db_manager.connect()
        self.services = await self.build_services(db_manager.engine)
        if await self.services.user_service.default_admin_password_in_use(os.environ["DEFAULT_ADMIN_USERNAME"], os.environ["DEFAULT_ADMIN_PASSWORD"]):
            logger.warning("The default administrator account still uses DEFAULT_ADMIN_PASSWORD from the environment; change it from the Users page.")
        self.realtime_bus = await self._start_realtime_bus()
        realtime_broker.configure(self.build_realtime_snapshot, bus=self.realtime_bus)
        scheduler_state.scheduler = MonitorScheduler(monitor_service=self.services.monitor_service, on_fatal=lambda exc: terminate_process(f"The monitor scheduler failed: {exc!r}."))
        if realtime_broker.is_leader:
            self.scheduler_task = asyncio.create_task(scheduler_state.scheduler.start())
            self.watchdog_task = asyncio.create_task(scheduler_watchdog(scheduler_state.scheduler))
        else:
            logger.info("This node is a real-time follower; monitor scheduling stays with the leader.")
        return self.services

    @staticmethod
    async def _start_realtime_bus():
        if bus_mode() != BUS_MONGO:
            return None
        bus = MongoRealtimeBus(db_manager.engine.database)
        await bus.start()
        logger.info("Real-time bus started in mongo mode; leader=%s", bus.is_leader)
        return bus

    async def shutdown(self) -> None:
        if self.watchdog_task is not None:
            self.watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.watchdog_task
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop()
        if self.scheduler_task is not None:
            self.scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.scheduler_task
        if self.services is not None:
            await self.services.checker_factory.close()
            await self.services.slack_integration_service.close()
        await realtime_broker.shutdown()
        if self.realtime_bus is not None:
            await self.realtime_bus.stop()
            self.realtime_bus = None
        EmailTemplateManager.get_instance().clear()
        auth_token_state.token_manager = None
        await db_manager.disconnect()
        self.services = None

    @staticmethod
    async def build_services(engine) -> Services:
        auth_profile_service = AuthProfileManager(engine)
        await auth_profile_service.create_indexes()
        auth_token_state.token_manager = AccessTokenCookieManager(auth_profile_service)
        checker_factory = CheckerFactory(token_manager=auth_token_state.token_manager)
        http_monitor_service = HttpMonitorManager(engine, auth_profile_service)
        api_monitor_manager = ApiMonitorManager(engine, auth_profile_service)
        ping_monitor_service = PingMonitorManager(engine)
        heartbeat_monitor_service = HeartbeatMonitorManager(engine)
        orion_script_monitor_service = OrionScriptMonitorManager(engine, auth_profile_service)
        incident_service = IncidentManager(engine)
        monitor_result_service = MonitorResultManager(engine)
        monitor_service = MonitorManager(http_monitor_service=http_monitor_service, api_monitor_manager=api_monitor_manager, ping_monitor_service=ping_monitor_service, heartbeat_monitor_service=heartbeat_monitor_service, incident_service=incident_service, monitor_result_service=monitor_result_service, monitor_state_service=MonitorStateManager(engine), checker_factory=checker_factory, orion_script_monitor_service=orion_script_monitor_service)
        slack_integration_service = SlackIntegrationManager(engine, monitor_service)
        email_integration_service = EmailIntegrationManager(engine, monitor_service)
        monitor_service.slack_integration_service = slack_integration_service
        monitor_service.email_integration_service = email_integration_service
        heartbeat_monitor_service.monitor_service = monitor_service
        dashboard_service = DashboardManager(monitor_service=monitor_service, monitor_result_service=monitor_result_service, incident_service=incident_service)
        return Services(
            auth_profile_service=auth_profile_service,
            http_monitor_service=http_monitor_service,
            api_monitor_manager=api_monitor_manager,
            ping_monitor_service=ping_monitor_service,
            heartbeat_monitor_service=heartbeat_monitor_service,
            orion_script_monitor_service=orion_script_monitor_service,
            user_service=UserManager(engine, password_service),
            checker_factory=checker_factory,
            monitor_service=monitor_service,
            dashboard_service=dashboard_service,
            status_page_service=StatusPageManager(engine, monitor_service, dashboard_service),
            slack_integration_service=slack_integration_service,
            email_integration_service=email_integration_service,
        )

    @staticmethod
    async def changed_monitor_details(dashboard_service: DashboardManager, changed, overviews) -> dict:
        monitor_ids = [entity_id for kind, entity_id in changed if kind == "monitor" and entity_id is not None]
        if not monitor_ids:
            return {}
        return await dashboard_service.build_monitor_details(overviews, monitor_ids)

    async def build_realtime_snapshot(self, changed):
        services = self.services
        if services is None:
            raise RuntimeError("Services are not initialised.")
        dashboard_service = services.dashboard_service
        summary, incidents, activity, overviews = await dashboard_service.collect_snapshot_sections()
        changed_details = await self.changed_monitor_details(dashboard_service, changed, overviews)
        return jsonable_encoder({"generated_at": datetime.now(UTC), "summary": summary, "incidents": incidents, "activity": activity, "overviews": overviews, "changed_monitor_details": changed_details})
