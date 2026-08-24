import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from configs.exception_handlers import register_exception_handlers
from orion.management.managers.service_manager import ServiceManager
from orion.middleware.security_headers import register_security_headers
from orion.services.auth.authorization import development_environment
from routes.api_monitor_routes import router as api_monitor_router
from routes.auth_routes import router as auth_router
from routes.email_integration_routes import router as email_integration_router
from routes.frontend_routes import router as frontend_router
from routes.heartbeat_monitor_routes import router as heartbeat_router
from routes.http_monitor_routes import router as http_monitor_router
from routes.insight_routes import router as dashboard_router
from routes.orion_login_routes import router as auth_profiles_router
from routes.ping_monitor_routes import router as ping_router
from routes.realtime_routes import router as realtime_router
from routes.slack_integration_routes import router as slack_integration_router
from routes.status_page_routes import router as status_page_router
from routes.user_account_routes import router as users_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(http_monitor_router)
api_router.include_router(dashboard_router)
api_router.include_router(api_monitor_router)
api_router.include_router(ping_router)
api_router.include_router(heartbeat_router)
api_router.include_router(auth_profiles_router)
api_router.include_router(realtime_router)
api_router.include_router(status_page_router)
api_router.include_router(slack_integration_router)
api_router.include_router(email_integration_router)


@api_router.get("/health", include_in_schema=False)
async def health():
    scheduler = scheduler_state.scheduler
    healthy = scheduler is not None and scheduler.is_healthy()
    body = {"status": "ok" if healthy else "degraded", "scheduler": None if scheduler is None else scheduler.status()}
    return JSONResponse(body, status_code=200 if healthy else 503)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ServiceManager.get_instance().init_services()
    try:
        yield
    finally:
        await ServiceManager.get_instance().shutdown()


load_dotenv()
docs_enabled = development_environment()
app = FastAPI(title=os.environ["APP_NAME"], version=os.environ["APP_VERSION"], lifespan=lifespan, docs_url="/docs" if docs_enabled else None, redoc_url="/redoc" if docs_enabled else None, openapi_url="/openapi.json" if docs_enabled else None)

register_exception_handlers(app)
register_security_headers(app)
app.include_router(api_router)
app.include_router(frontend_router)
