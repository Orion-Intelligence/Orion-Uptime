from fastapi import APIRouter, Depends
from odmantic import AIOEngine

from app.modules.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from app.service.authorization import require_admin
from app.service.constants import Messages
from app.service.mongo_db.mongo_controller import get_engine
from app.service.mongo_db.shared_models.db_ping_monitor_model import CreatePingMonitorRequest, PingMonitorResponse, UpdatePingMonitorRequest
from app.service.responses import SuccessResponse, success_response


def get_ping_service(engine: AIOEngine = Depends(get_engine)) -> PingMonitorManager:
    return PingMonitorManager(engine)

router = APIRouter(prefix="/ping-monitors", tags=["Ping Monitors"], dependencies=[Depends(require_admin())])

@router.post("/create", response_model=SuccessResponse[PingMonitorResponse])
async def create_ping_monitor(request: CreatePingMonitorRequest, service: PingMonitorManager = Depends(get_ping_service)):
    return success_response(
        message=Messages.monitor_CREATED,
        data=await service.create_monitor(
            name=request.name,
            host=request.host,
            check_interval=request.check_interval,
            timeout=request.timeout,
            expected_response_time_ms=request.expected_response_time_ms,
        ),
    )

@router.get("/list_all", response_model=SuccessResponse[list[PingMonitorResponse]])
async def list_monitors(service: PingMonitorManager = Depends(get_ping_service)):
    return success_response(
        message=Messages.monitor_FETCHED,
        data=await service.list_monitors(),
    )

@router.get("/{PING_monitor_id}/get_one", response_model=SuccessResponse[PingMonitorResponse])
async def get_ping_monitor(PING_monitor_id: str, service: PingMonitorManager = Depends(get_ping_service)):
    return success_response(
        message=Messages.monitor_FETCHED,
        data=await service.get_monitor(PING_monitor_id),
    )

@router.put("/{PING_monitor_id}/update", response_model=SuccessResponse[PingMonitorResponse])
async def update_ping_monitor(PING_monitor_id: str, request: UpdatePingMonitorRequest, service: PingMonitorManager = Depends(get_ping_service)):
    return success_response(
        message=Messages.monitor_UPDATED,
        data=await service.update_monitor(
            monitor_id=PING_monitor_id,
            name=request.name,
            host=request.host,
            check_interval=request.check_interval,
            timeout=request.timeout,
            expected_response_time_ms=request.expected_response_time_ms,
            is_active=request.is_active,
        ),
    )

@router.delete("/{PING_monitor_id}/delete", response_model=SuccessResponse[None])
async def delete_ping_monitor(PING_monitor_id: str, service: PingMonitorManager = Depends(get_ping_service)):
    await service.delete_monitor(PING_monitor_id)

    return success_response(
        message=Messages.monitor_DELETED,
        data=None,
    )
