from fastapi import APIRouter, Depends
from odmantic import AIOEngine

from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.constants.constant import Messages
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_http_monitor_model import CreateHttpMonitorRequest, HttpMonitorResponse, UpdateHttpMonitorRequest
from orion.shared_models.responses import SuccessResponse, success_response


def get_http_monitor_service(engine: AIOEngine = Depends(get_engine)) -> HttpMonitorManager:
    return HttpMonitorManager(engine, AuthProfileManager(engine))


router = APIRouter(prefix="/HTTP_monitors", tags=["HTTP_monitors"], dependencies=[Depends(require_admin())])


@router.post("/create", response_model=SuccessResponse[HttpMonitorResponse])
async def create_http_monitor(request: CreateHttpMonitorRequest, service: HttpMonitorManager = Depends(get_http_monitor_service)):
    return success_response(message=Messages.MONITOR_CREATED, data=await service.create_monitor(name=request.name, url=request.url, check_interval=request.check_interval, timeout=request.timeout, expected_status_code=request.expected_status_code, expected_response_time_ms=request.expected_response_time_ms, auth_profile_id=request.auth_profile_id))


@router.get("/list_all", response_model=SuccessResponse[list[HttpMonitorResponse]])
async def list_monitors(service: HttpMonitorManager = Depends(get_http_monitor_service)):
    return success_response(message=Messages.MONITOR_FETCHED, data=await service.list_monitors())


@router.get("/{http_monitor_id}/get_one", response_model=SuccessResponse[HttpMonitorResponse])
async def get_http_monitor(http_monitor_id: str, service: HttpMonitorManager = Depends(get_http_monitor_service)):
    return success_response(message=Messages.MONITOR_FETCHED, data=await service.get_monitor(http_monitor_id))


@router.put("/{http_monitor_id}/update", response_model=SuccessResponse[HttpMonitorResponse])
async def update_http_monitor(http_monitor_id: str, request: UpdateHttpMonitorRequest, service: HttpMonitorManager = Depends(get_http_monitor_service)):
    return success_response(message=Messages.MONITOR_UPDATED, data=await service.update_monitor(http_monitor_id=http_monitor_id, name=request.name, url=request.url, check_interval=request.check_interval, timeout=request.timeout, expected_status_code=request.expected_status_code, expected_response_time_ms=request.expected_response_time_ms, is_active=request.is_active, expected_response_time_ms_set="expected_response_time_ms" in request.model_fields_set, auth_profile_id=request.auth_profile_id, auth_profile_id_set="auth_profile_id" in request.model_fields_set))


@router.delete("/{http_monitor_id}/delete", response_model=SuccessResponse[None])
async def delete_http_monitor(http_monitor_id: str, service: HttpMonitorManager = Depends(get_http_monitor_service)):
    await service.delete_monitor(http_monitor_id)

    return success_response(message=Messages.MONITOR_DELETED, data=None)
