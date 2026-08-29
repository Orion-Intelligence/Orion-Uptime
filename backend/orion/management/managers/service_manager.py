import asyncio
import logging
import os
import signal
from contextlib import suppress
from datetime import UTC, datetime
from typing import NamedTuple

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.constants.constant import Intervals
from orion.api.interactive.api_monitor_manager.api_monitor_manager import ApiMonitorManager
from orion.api.interactive.auth_manager.auth_manager import password_service
from orion.api.interactive.email_integration_manager.email_integration_manager import EmailIntegrationManager
from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.api.interactive.incident_manager.incident_manager import IncidentManager
from orion.api.interactive.insight_manager.insight_manager import DashboardManager
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.api.interactive.orion_login_manager.orion_token_manager import AccessTokenCookieManager
from orion.api.interactive.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from orion.api.interactive.slack_integration_manager.slack_integration_manager import SlackIntegrationManager
from orion.api.interactive.status_page_manager.status_page_manager import StatusPageManager
from orion.api.interactive.user_account_manager.user_account_manager import UserManager
from orion.management.jobs.monitoring_controller.checkers.checker_factory import CheckerFactory
from orion.management.jobs.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from orion.management.jobs.monitoring_controller.monitor_state_manager.monitor_state_manager import MonitorStateManager
from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager
from orion.management.jobs.monitoring_controller.scheduler import MonitorScheduler
from orion.services.mongo_manager.mongo_controller import db_manager
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError

logger = logging.getLogger("orion.uptime")



class Services(NamedTuple):
    auth_profile_service: AuthProfileManager
    http_monitor_service: HttpMonitorManager
    api_monitor_manager: ApiMonitorManager
    ping_monitor_service: PingMonitorManager
    heartbeat_monitor_service: HeartbeatMonitorManager
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

    async def init_services(self) -> Services:
        await db_manager.connect()
        self.services = await self.build_services(db_manager.engine)
        if await self.services.user_service.default_admin_password_in_use(os.environ["DEFAULT_ADMIN_USERNAME"], os.environ["DEFAULT_ADMIN_PASSWORD"]):
            logger.warning("The default administrator account still uses DEFAULT_ADMIN_PASSWORD from the environment; change it from the Users page.")
        realtime_broker.configure(self.build_realtime_snapshot)
        scheduler_state.scheduler = MonitorScheduler(monitor_service=self.services.monitor_service, on_fatal=lambda exc: terminate_process(f"The monitor scheduler failed: {exc!r}."))
        self.scheduler_task = asyncio.create_task(scheduler_state.scheduler.start())
        self.watchdog_task = asyncio.create_task(scheduler_watchdog(scheduler_state.scheduler))
        return self.services

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
        auth_token_state.token_manager = None
        await db_manager.disconnect()
        self.services = None

    @staticmethod
    async def build_services(engine) -> Services:
        auth_profile_service = AuthProfileManager(engine)
        await auth_profile_service.create_indexes()
        auth_token_state.token_manager = AccessTokenCookieManager(auth_profile_service)
        checker_factory = CheckerFactory(token_manager=auth_token_state.token_manager)
        http_monitor_service = HttpMonitorManager(engine)
        api_monitor_manager = ApiMonitorManager(engine, auth_profile_service)
        ping_monitor_service = PingMonitorManager(engine)
        heartbeat_monitor_service = HeartbeatMonitorManager(engine)
        incident_service = IncidentManager(engine)
        monitor_result_service = MonitorResultManager(engine)
        monitor_service = MonitorManager(http_monitor_service=http_monitor_service, api_monitor_manager=api_monitor_manager, ping_monitor_service=ping_monitor_service, heartbeat_monitor_service=heartbeat_monitor_service, incident_service=incident_service, monitor_result_service=monitor_result_service, monitor_state_service=MonitorStateManager(engine), checker_factory=checker_factory)
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
            user_service=UserManager(engine, password_service),
            checker_factory=checker_factory,
            monitor_service=monitor_service,
            dashboard_service=dashboard_service,
            status_page_service=StatusPageManager(engine, monitor_service, dashboard_service),
            slack_integration_service=slack_integration_service,
            email_integration_service=email_integration_service,
        )

    @staticmethod
    async def changed_monitor_details(dashboard_service: DashboardManager, changed) -> dict:
        details = {}
        for kind, entity_id in changed:
            if kind != "monitor" or entity_id is None:
                continue
            with suppress(NotFoundError):
                details[entity_id] = await dashboard_service.get_monitor_detail(entity_id)
        return details

    @staticmethod
    def viewer_resources(overviews) -> dict:
        resources = {"HTTP": [], "API": [], "ping": [], "heartbeat": [], "auth_profiles": [], "users": [], "status_pages": [], "slack_integrations": [], "email_integrations": []}
        for overview in overviews:
            if overview.monitor_type not in resources:
                continue
            resources[overview.monitor_type].append({"id": overview.id, "name": overview.name, "monitor_type": overview.monitor_type, "status": overview.status, "is_active": overview.is_active, "created_at": overview.created_at, "last_checked_at": overview.last_checked_at})
        return resources

    @staticmethod
    async def admin_resources(services: Services) -> dict:
        http_monitors, api_monitors, ping_monitors, heartbeat_monitors, auth_profiles, users, status_pages, slack_integrations, email_integrations = await asyncio.gather(
            services.http_monitor_service.list_monitors(), services.api_monitor_manager.list_monitors(), services.ping_monitor_service.list_monitors(), services.heartbeat_monitor_service.list_monitors(), services.auth_profile_service.list_profiles(), services.user_service.list_users(), services.status_page_service.list_pages(), services.slack_integration_service.list_integrations(), services.email_integration_service.list_integrations()
        )
        return {"HTTP": http_monitors, "API": api_monitors, "ping": ping_monitors, "heartbeat": heartbeat_monitors, "auth_profiles": auth_profiles, "users": users, "status_pages": status_pages, "slack_integrations": slack_integrations, "email_integrations": email_integrations}

    async def build_realtime_snapshot(self, changed, include_admin):
        services = self.services
        if services is None:
            raise RuntimeError("Services are not initialised.")
        dashboard_service = services.dashboard_service
        summary, incidents, activity, overviews = await asyncio.gather(dashboard_service.get_summary(), dashboard_service.get_recent_incidents(), dashboard_service.get_recent_activity(), dashboard_service.get_monitor_overviews())
        common = {"generated_at": datetime.now(UTC), "summary": summary, "incidents": incidents, "activity": activity, "overviews": overviews, "changed_monitor_details": await self.changed_monitor_details(dashboard_service, changed), "resources": self.viewer_resources(overviews)}
        admin = common
        if include_admin:
            admin = {**common, "resources": await self.admin_resources(services)}
        return common, admin
