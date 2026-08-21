from fastapi import APIRouter, Depends, Query

import app.modules.monitoring_controller.scheduler as scheduler_state
from app.modules.insight_manager.insight_manager import DashboardManager
from app.modules.monitoring_controller.monitoring_controller import MonitorManager
from app.service.authorization import require_viewer
from app.service.constants import Messages
from app.service.mongo_db.shared_models.db_insight_model import DashboardActivityResponse, DashboardIncidentResponse, DashboardSummaryResponse, MonitorDetailResponse, MonitorOverviewResponse, ResponseHistoryResponse, StatusHistoryResponse, UptimeResponse
from app.service.responses import SuccessResponse, success_response


def get_monitor_service() -> MonitorManager:
    if scheduler_state.scheduler is None:
        raise RuntimeError("The monitor scheduler has not been initialized.")
    return scheduler_state.scheduler.monitor_service


def get_dashboard_service(monitor_service: MonitorManager = Depends(get_monitor_service)) -> DashboardManager:
    return DashboardManager(
        monitor_service=monitor_service,
        monitor_result_service=monitor_service.monitor_result_service,
        incident_service=monitor_service.incident_service,
    )

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(require_viewer())])

@router.get("/summary", response_model=SuccessResponse[DashboardSummaryResponse])
async def get_summary(service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_summary(),
    )

@router.get("/incidents", response_model=SuccessResponse[list[DashboardIncidentResponse]])
async def get_dashboard_incidents(service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_recent_incidents(),
    )

@router.get("/activity", response_model=SuccessResponse[list[DashboardActivityResponse]])
async def get_dashboard_activity(service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_recent_activity(),
    )

@router.get("/monitor-overviews", response_model=SuccessResponse[list[MonitorOverviewResponse]])
async def get_monitor_overviews(service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_monitor_overviews(),
    )

@router.get("/monitors/{monitor_id}", response_model=SuccessResponse[MonitorDetailResponse])
async def get_monitor_detail(monitor_id: str, service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_monitor_detail(monitor_id),
    )

@router.get("/response-history/{monitor_id}", response_model=SuccessResponse[ResponseHistoryResponse])
async def get_response_history(monitor_id: str, days: int = Query(7, ge=1, le=365), service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_response_history(monitor_id, days)
    )

@router.get("/uptime/{monitor_id}", response_model=SuccessResponse[UptimeResponse])
async def get_uptime(monitor_id: str, days: int = Query(7, ge=1, le=365), service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_uptime(monitor_id, days)
    )

@router.get("/status-history/{monitor_id}", response_model=SuccessResponse[StatusHistoryResponse])
async def get_status_history(monitor_id: str, days: int = Query(7, ge=1, le=365), service: DashboardManager = Depends(get_dashboard_service)):
    return success_response(
        message=Messages.DASHBOARD_FETCHED,
        data=await service.get_status_history(monitor_id, days)
    )
