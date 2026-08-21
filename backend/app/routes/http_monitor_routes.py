from fastapi import APIRouter, Depends
from odmantic import AIOEngine

from app.modules.http_monitor_manager.http_monitor_manager import HTTP_monitorManager
from app.service.authorization import require_admin
from app.service.constants import Messages
from app.service.mongo_db.mongo_controller import get_engine
from app.service.mongo_db.shared_models.db_http_monitor_model import CreateHTTP_monitorRequest, HTTP_monitorResponse, UpdateHTTP_monitorRequest
from app.service.responses import SuccessResponse, success_response


def get_HTTP_monitor_service(engine: AIOEngine = Depends(get_engine)) -> HTTP_monitorManager:
    return HTTP_monitorManager(engine)

router = APIRouter(prefix="/HTTP_monitors", tags=["HTTP_monitors"], dependencies=[Depends(require_admin())])

@router.post("/create", response_model=SuccessResponse[HTTP_monitorResponse])
async def create_HTTP_monitor(request: CreateHTTP_monitorRequest, service: HTTP_monitorManager = Depends(get_HTTP_monitor_service)):
    return success_response(
        message=Messages.monitor_CREATED,
        data=await service.create_monitor(
            name=request.name,
            url=request.url,
            check_interval=request.check_interval,
            timeout=request.timeout,
            expected_status_code=request.expected_status_code,
            expected_response_time_ms=request.expected_response_time_ms,
        ),
    )

@router.get("/list_all", response_model=SuccessResponse[list[HTTP_monitorResponse]])
async def list_monitors(service: HTTP_monitorManager = Depends(get_HTTP_monitor_service)):
    return success_response(
        message=Messages.monitor_FETCHED,
        data=await service.list_monitors(),
    )

@router.get("/{HTTP_monitor_id}/get_one", response_model=SuccessResponse[HTTP_monitorResponse])
async def get_HTTP_monitor(HTTP_monitor_id: str, service: HTTP_monitorManager = Depends(get_HTTP_monitor_service)):
    return success_response(
        message=Messages.monitor_FETCHED,
        data=await service.get_monitor(HTTP_monitor_id),
    )

@router.put("/{HTTP_monitor_id}/update", response_model=SuccessResponse[HTTP_monitorResponse])
async def update_HTTP_monitor(HTTP_monitor_id: str, request: UpdateHTTP_monitorRequest, service: HTTP_monitorManager = Depends(get_HTTP_monitor_service)):
    return success_response(
        message=Messages.monitor_UPDATED,
        data=await service.update_monitor(
            HTTP_monitor_id=HTTP_monitor_id,
            name=request.name,
            url=request.url,
            check_interval=request.check_interval,
            timeout=request.timeout,
            expected_status_code=request.expected_status_code,
            expected_response_time_ms=request.expected_response_time_ms,
            is_active=request.is_active,
        ),
    )

@router.delete("/{HTTP_monitor_id}/delete", response_model=SuccessResponse[None])
async def delete_HTTP_monitor(HTTP_monitor_id: str, service: HTTP_monitorManager = Depends(get_HTTP_monitor_service)):
    await service.delete_monitor(HTTP_monitor_id)

    return success_response(
        message=Messages.monitor_DELETED,
        data=None,
    )
