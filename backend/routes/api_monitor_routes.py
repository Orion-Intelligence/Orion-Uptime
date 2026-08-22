from fastapi import APIRouter, Depends, status
from odmantic import AIOEngine

from orion.api.interactive.api_monitor_manager.api_monitor_manager import ApiMonitorManager
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_api_monitor_model import ApiMonitorResponse, CreateApiMonitorRequest, UpdateApiMonitorRequest
from orion.shared_models.responses import ApiResponse


def get_api_monitor_service(engine: AIOEngine = Depends(get_engine)) -> ApiMonitorManager:
    return ApiMonitorManager(engine, AuthProfileManager(engine))


router = APIRouter(prefix="/API_monitors", tags=["API Monitors"], dependencies=[Depends(require_admin())])


@router.post("/create", response_model=ApiResponse[ApiMonitorResponse], status_code=status.HTTP_201_CREATED)
async def create_monitor(request: CreateApiMonitorRequest, service: ApiMonitorManager = Depends(get_api_monitor_service)):
    return ApiResponse(success=True, message="API monitor created successfully.", data=await service.create_monitor(request=request))


@router.get("/list_all", response_model=ApiResponse[list[ApiMonitorResponse]])
async def list_monitors(service: ApiMonitorManager = Depends(get_api_monitor_service)):
    return ApiResponse(success=True, message="API monitors retrieved successfully.", data=await service.list_monitors())


@router.get("/{monitor_id}", response_model=ApiResponse[ApiMonitorResponse])
async def get_monitor(monitor_id: str, service: ApiMonitorManager = Depends(get_api_monitor_service)):
    return ApiResponse(success=True, message="API monitor retrieved successfully.", data=await service.get_monitor(monitor_id))


@router.put("/{monitor_id}", response_model=ApiResponse[ApiMonitorResponse])
async def update_monitor(monitor_id: str, request: UpdateApiMonitorRequest, service: ApiMonitorManager = Depends(get_api_monitor_service)):
    return ApiResponse(success=True, message="API monitor updated successfully.", data=await service.update_monitor(monitor_id, request))


@router.delete("/{monitor_id}", response_model=ApiResponse[None])
async def delete_monitor(monitor_id: str, service: ApiMonitorManager = Depends(get_api_monitor_service)):
    await service.delete_monitor(monitor_id)

    return ApiResponse(success=True, message="Deleted successfully.")
