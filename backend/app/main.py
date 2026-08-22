import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import NamedTuple

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

import app.modules.monitoring_controller.scheduler as scheduler_state
import app.modules.orion_login_manager.orion_token_manager as auth_token_state
from app.core.exception_handlers import register_exception_handlers
from app.core.security_headers import register_security_headers
from app.modules.api_monitor_manager.api_monitor_manager import API_monitorManager
from app.modules.auth_manager.auth_manager import password_service
from app.modules.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from app.modules.http_monitor_manager.http_monitor_manager import HTTP_monitorManager
from app.modules.incident_manager.incident_manager import IncidentManager
from app.modules.insight_manager.insight_manager import DashboardManager
from app.modules.monitoring_controller.checkers.checker_factory import CheckerFactory
from app.modules.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from app.modules.monitoring_controller.monitor_state_manager.monitor_state_manager import MonitorStateManager
from app.modules.monitoring_controller.monitoring_controller import MonitorManager
from app.modules.monitoring_controller.scheduler import SCHEDULER_STALL_SECONDS, MonitorScheduler
from app.modules.orion_login_manager.orion_login_manager import AuthProfileManager
from app.modules.orion_login_manager.orion_token_manager import AccessTokenCookieManager
from app.modules.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from app.modules.status_page_manager.status_page_manager import StatusPageManager
from app.modules.user_account_manager.user_account_manager import UserManager
from app.routes.api_monitor_routes import router as api_monitor_router
from app.routes.auth_routes import router as auth_router
from app.routes.frontend_routes import router as frontend_router
from app.routes.heartbeat_monitor_routes import router as heartbeat_router
from app.routes.http_monitor_routes import router as HTTP_monitor_router
from app.routes.insight_routes import router as dashboard_router
from app.routes.orion_login_routes import router as auth_profiles_router
from app.routes.ping_monitor_routes import router as ping_router
from app.routes.realtime_routes import router as realtime_router
from app.routes.status_page_routes import router as status_page_router
from app.routes.user_account_routes import router as users_router
from app.service.authorization import development_environment
from app.service.exceptions import NotFoundError
from app.service.mongo_db.mongo_controller import db_manager
from app.service.realtime import realtime_broker

logger = logging.getLogger("orion.uptime")

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(HTTP_monitor_router)
api_router.include_router(dashboard_router)
api_router.include_router(api_monitor_router)
api_router.include_router(ping_router)
api_router.include_router(heartbeat_router)
api_router.include_router(auth_profiles_router)
api_router.include_router(realtime_router)
api_router.include_router(status_page_router)

WATCHDOG_INTERVAL_SECONDS = 30


def terminate_process(reason: str) -> None:
    logger.critical("%s Terminating so the container restarts.", reason)
    os.kill(os.getpid(), signal.SIGTERM)


async def scheduler_watchdog(scheduler: MonitorScheduler, interval: float = WATCHDOG_INTERVAL_SECONDS) -> None:
    while True:
        await asyncio.sleep(interval)
        if scheduler.running and scheduler.last_reconcile_at is not None and not scheduler.is_healthy(SCHEDULER_STALL_SECONDS * 2):
            terminate_process(f"The monitor scheduler has not reconciled for more than {SCHEDULER_STALL_SECONDS * 2} seconds.")
            return


@api_router.get("/health", include_in_schema=False)
async def health():
    scheduler = scheduler_state.scheduler
    healthy = scheduler is not None and scheduler.is_healthy()
    body = {
        "status": "ok" if healthy else "degraded",
        "scheduler": None if scheduler is None else scheduler.status(),
    }
    return JSONResponse(body, status_code=200 if healthy else 503)

class Services(NamedTuple):
    auth_profile_service: AuthProfileManager
    http_monitor_service: HTTP_monitorManager
    api_monitor_manager: API_monitorManager
    ping_monitor_service: PingMonitorManager
    heartbeat_monitor_service: HeartbeatMonitorManager
    user_service: UserManager
    checker_factory: CheckerFactory
    monitor_service: MonitorManager
    dashboard_service: DashboardManager
    status_page_service: StatusPageManager


async def build_services(engine) -> Services:
    auth_profile_service = AuthProfileManager(engine)
    await auth_profile_service.create_indexes()
    auth_token_state.token_manager = AccessTokenCookieManager(auth_profile_service)
    checker_factory = CheckerFactory(token_manager=auth_token_state.token_manager)
    http_monitor_service = HTTP_monitorManager(engine)
    api_monitor_manager = API_monitorManager(engine, auth_profile_service)
    ping_monitor_service = PingMonitorManager(engine)
    heartbeat_monitor_service = HeartbeatMonitorManager(engine)
    incident_service = IncidentManager(engine)
    monitor_result_service = MonitorResultManager(engine)
    monitor_service = MonitorManager(
        http_monitor_service=http_monitor_service,
        api_monitor_manager=api_monitor_manager,
        ping_monitor_service=ping_monitor_service,
        heartbeat_monitor_service=heartbeat_monitor_service,
        incident_service=incident_service,
        monitor_result_service=monitor_result_service,
        monitor_state_service=MonitorStateManager(engine),
        checker_factory=checker_factory,
    )
    heartbeat_monitor_service.monitor_service = monitor_service
    dashboard_service = DashboardManager(
        monitor_service=monitor_service,
        monitor_result_service=monitor_result_service,
        incident_service=incident_service,
    )
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
    )


async def changed_monitor_details(dashboard_service: DashboardManager, changed) -> dict:
    details = {}
    for kind, entity_id in changed:
        if kind != "monitor" or entity_id is None:
            continue
        with suppress(NotFoundError):
            details[entity_id] = await dashboard_service.get_monitor_detail(entity_id)
    return details


def viewer_resources(overviews) -> dict:
    resources = {
        "HTTP": [],
        "API": [],
        "ping": [],
        "heartbeat": [],
        "auth_profiles": [],
        "users": [],
        "status_pages": [],
    }
    for overview in overviews:
        if overview.monitor_type not in resources:
            continue
        resources[overview.monitor_type].append(
            {
                "id": overview.id,
                "name": overview.name,
                "monitor_type": overview.monitor_type,
                "status": overview.status,
                "is_active": overview.is_active,
                "created_at": overview.created_at,
                "last_checked_at": overview.last_checked_at,
            }
        )
    return resources


async def admin_resources(services: Services) -> dict:
    (
        http_monitors,
        api_monitors,
        ping_monitors,
        heartbeat_monitors,
        auth_profiles,
        users,
        status_pages,
    ) = await asyncio.gather(
        services.http_monitor_service.list_monitors(),
        services.api_monitor_manager.list_monitors(),
        services.ping_monitor_service.list_monitors(),
        services.heartbeat_monitor_service.list_monitors(),
        services.auth_profile_service.list_profiles(),
        services.user_service.list_users(),
        services.status_page_service.list_pages(),
    )
    return {
        "HTTP": http_monitors,
        "API": api_monitors,
        "ping": ping_monitors,
        "heartbeat": heartbeat_monitors,
        "auth_profiles": auth_profiles,
        "users": users,
        "status_pages": status_pages,
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db_manager.connect()
    services = await build_services(db_manager.engine)
    if await services.user_service.default_admin_password_in_use(os.environ["DEFAULT_ADMIN_USERNAME"], os.environ["DEFAULT_ADMIN_PASSWORD"]):
        logger.warning("The default administrator account still uses DEFAULT_ADMIN_PASSWORD from the environment; change it from the Users page.")

    async def build_realtime_snapshot(changed, include_admin):
        dashboard_service = services.dashboard_service
        summary, incidents, activity, overviews = await asyncio.gather(
            dashboard_service.get_summary(),
            dashboard_service.get_recent_incidents(),
            dashboard_service.get_recent_activity(),
            dashboard_service.get_monitor_overviews(),
        )
        common = {
            "generated_at": datetime.now(UTC),
            "summary": summary,
            "incidents": incidents,
            "activity": activity,
            "overviews": overviews,
            "changed_monitor_details": await changed_monitor_details(dashboard_service, changed),
            "resources": viewer_resources(overviews),
        }
        admin = common
        if include_admin:
            admin = {**common, "resources": await admin_resources(services)}
        return common, admin

    realtime_broker.configure(build_realtime_snapshot)

    scheduler_state.scheduler = MonitorScheduler(
        monitor_service=services.monitor_service,
        on_fatal=lambda exc: terminate_process(f"The monitor scheduler failed: {exc!r}."),
    )
    scheduler_task = asyncio.create_task(scheduler_state.scheduler.start())
    watchdog_task = asyncio.create_task(scheduler_watchdog(scheduler_state.scheduler))

    try:
        yield
    finally:
        watchdog_task.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog_task
        await scheduler_state.scheduler.stop()
        scheduler_task.cancel()

        with suppress(asyncio.CancelledError):
            await scheduler_task

        await services.checker_factory.close()
        await realtime_broker.shutdown()
        auth_token_state.token_manager = None
        await db_manager.disconnect()

load_dotenv()
docs_enabled = development_environment()
app = FastAPI(
    title=os.environ["APP_NAME"],
    version=os.environ["APP_VERSION"],
    lifespan=lifespan,
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

register_exception_handlers(app)
register_security_headers(app)
app.include_router(api_router)
app.include_router(frontend_router)
