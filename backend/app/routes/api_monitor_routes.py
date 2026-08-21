from fastapi import APIRouter, Depends, status
from odmantic import AIOEngine

from app.modules.api_monitor_manager.api_monitor_manager import API_monitorManager
from app.modules.orion_login_manager.orion_login_manager import AuthProfileManager
from app.service.authorization import require_admin
from app.service.mongo_db.mongo_controller import get_engine
from app.service.mongo_db.shared_models.db_api_monitor_model import ApiMonitorResponse, CreateApiMonitorRequest, UpdateApiMonitorRequest
from app.service.responses import ApiResponse


def get_API_monitor_service(engine: AIOEngine = Depends(get_engine)) -> API_monitorManager:
    return API_monitorManager(engine, AuthProfileManager(engine))

router = APIRouter(prefix="/API_monitors", tags=["API Monitors"], dependencies=[Depends(require_admin())])

@router.post("/create", response_model=ApiResponse[ApiMonitorResponse], status_code=status.HTTP_201_CREATED)
async def create_monitor(request: CreateApiMonitorRequest, service: API_monitorManager = Depends(get_API_monitor_service)):
    return ApiResponse(
        success=True,
        message="API monitor created successfully.",
        data=await service.create_monitor(request=request),
    )

@router.get("/list_all", response_model=ApiResponse[list[ApiMonitorResponse]])
async def list_monitors(service: API_monitorManager = Depends(get_API_monitor_service)):
    return ApiResponse(
        success=True,
        message="API monitors retrieved successfully.",
        data=await service.list_monitors(),
    )

@router.get("/{monitor_id}", response_model=ApiResponse[ApiMonitorResponse])
async def get_monitor(monitor_id: str, service: API_monitorManager = Depends(get_API_monitor_service)):
    return ApiResponse(
        success=True,
        message="API monitor retrieved successfully.",
        data=await service.get_monitor(monitor_id),
    )

@router.put("/{monitor_id}", response_model=ApiResponse[ApiMonitorResponse])
async def update_monitor(monitor_id: str, request: UpdateApiMonitorRequest, service: API_monitorManager = Depends(get_API_monitor_service)):
    return ApiResponse(
        success=True,
        message="API monitor updated successfully.",
        data=await service.update_monitor(monitor_id, request),
    )

@router.delete("/{monitor_id}", response_model=ApiResponse[None])
async def delete_monitor(monitor_id: str, service: API_monitorManager = Depends(get_API_monitor_service)):
    await service.delete_monitor(monitor_id)

    return ApiResponse(
        success=True,
        message="Deleted successfully."
    )
