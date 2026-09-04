from fastapi import APIRouter, Depends
from odmantic import AIOEngine

from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.api.interactive.orion_script_monitor_manager.orion_script_monitor_manager import OrionScriptMonitorManager
from orion.constants.constant import Messages
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import CreateOrionScriptMonitorRequest, OrionScriptMonitorResponse, UpdateOrionScriptMonitorRequest
from orion.shared_models.responses import SuccessResponse, success_response


def get_orion_script_service(engine: AIOEngine = Depends(get_engine)) -> OrionScriptMonitorManager:
    return OrionScriptMonitorManager(engine, AuthProfileManager(engine))


router = APIRouter(prefix="/orion-script-monitors", tags=["Orion Script Monitors"], dependencies=[Depends(require_admin())])


@router.post("/create", response_model=SuccessResponse[OrionScriptMonitorResponse])
async def create_orion_script_monitor(request: CreateOrionScriptMonitorRequest, service: OrionScriptMonitorManager = Depends(get_orion_script_service)):
    return success_response(message=Messages.MONITOR_CREATED, data=await service.create_monitor(name=request.name, url=request.url, check_interval=request.check_interval, timeout=request.timeout, expected_response_time_ms=request.expected_response_time_ms))


@router.get("/list_all", response_model=SuccessResponse[list[OrionScriptMonitorResponse]])
async def list_monitors(service: OrionScriptMonitorManager = Depends(get_orion_script_service)):
    return success_response(message=Messages.MONITOR_FETCHED, data=await service.list_monitors())


@router.get("/{monitor_id}/get_one", response_model=SuccessResponse[OrionScriptMonitorResponse])
async def get_orion_script_monitor(monitor_id: str, service: OrionScriptMonitorManager = Depends(get_orion_script_service)):
    return success_response(message=Messages.MONITOR_FETCHED, data=await service.get_monitor(monitor_id))


@router.put("/{monitor_id}/update", response_model=SuccessResponse[OrionScriptMonitorResponse])
async def update_orion_script_monitor(monitor_id: str, request: UpdateOrionScriptMonitorRequest, service: OrionScriptMonitorManager = Depends(get_orion_script_service)):
    return success_response(message=Messages.MONITOR_UPDATED, data=await service.update_monitor(monitor_id=monitor_id, name=request.name, url=request.url, check_interval=request.check_interval, timeout=request.timeout, expected_response_time_ms=request.expected_response_time_ms, is_active=request.is_active, expected_response_time_ms_set="expected_response_time_ms" in request.model_fields_set))


@router.delete("/{monitor_id}/delete", response_model=SuccessResponse[None])
async def delete_orion_script_monitor(monitor_id: str, service: OrionScriptMonitorManager = Depends(get_orion_script_service)):
    await service.delete_monitor(monitor_id)
    return success_response(message=Messages.MONITOR_DELETED, data=None)
