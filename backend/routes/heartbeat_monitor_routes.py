from fastapi import APIRouter, Depends
from odmantic import AIOEngine

from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.constants.constant import Messages
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import CreateHeartbeatMonitorRequest, HeartbeatMonitorResponse, HeartbeatResponse, HeartbeatTokenResponse, RegenerateHeartbeatTokenResponse, UpdateHeartbeatMonitorRequest
from orion.shared_models.responses import SuccessResponse, success_response


def get_heartbeat_service(engine: AIOEngine = Depends(get_engine)) -> HeartbeatMonitorManager:
    return HeartbeatMonitorManager(engine)


router = APIRouter(prefix="/heartbeat-monitors", tags=["Heartbeat Monitors"])


@router.post("/create", response_model=SuccessResponse[HeartbeatTokenResponse], dependencies=[Depends(require_admin())])
async def create_monitor(request: CreateHeartbeatMonitorRequest, service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    return success_response(message=Messages.MONITOR_CREATED, data=await service.create_monitor(name=request.name, expected_heartbeat_interval=request.expected_heartbeat_interval, grace_period=request.grace_period))


@router.get("/list_all", response_model=SuccessResponse[list[HeartbeatMonitorResponse]], dependencies=[Depends(require_admin())])
async def list_monitors(service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    return success_response(message=Messages.MONITOR_FETCHED, data=await service.list_monitors())


@router.get("/{heartbeat_monitor_id}/get_one", response_model=SuccessResponse[HeartbeatMonitorResponse], dependencies=[Depends(require_admin())])
async def get_monitor(heartbeat_monitor_id: str, service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    return success_response(message=Messages.MONITOR_FETCHED, data=await service.get_monitor(heartbeat_monitor_id))


@router.put("/{heartbeat_monitor_id}/update", response_model=SuccessResponse[HeartbeatMonitorResponse], dependencies=[Depends(require_admin())])
async def update_monitor(heartbeat_monitor_id: str, request: UpdateHeartbeatMonitorRequest, service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    return success_response(message=Messages.MONITOR_UPDATED, data=await service.update_monitor(heartbeat_monitor_id, name=request.name, expected_heartbeat_interval=request.expected_heartbeat_interval, grace_period=request.grace_period, is_active=request.is_active))


@router.delete("/{heartbeat_monitor_id}/delete", response_model=SuccessResponse[None], dependencies=[Depends(require_admin())])
async def delete_monitor(heartbeat_monitor_id: str, service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    await service.delete_monitor(heartbeat_monitor_id)

    return success_response(message=Messages.MONITOR_DELETED, data=None)


@router.post("/heartbeat/{token}", response_model=SuccessResponse[HeartbeatResponse], include_in_schema=False)
async def receive_heartbeat(token: str, service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    return success_response(message=Messages.HEARTBEAT_RECEIVED, data=await service.receive_heartbeat(token))


@router.patch("/{heartbeat_monitor_id}/regenerate-token", response_model=SuccessResponse[RegenerateHeartbeatTokenResponse], dependencies=[Depends(require_admin())])
async def regenerate_heartbeat_token(heartbeat_monitor_id: str, service: HeartbeatMonitorManager = Depends(get_heartbeat_service)):
    return success_response(message="Heartbeat token regenerated successfully.", data=await service.regenerate_token(heartbeat_monitor_id))
