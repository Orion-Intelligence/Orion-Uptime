from fastapi import APIRouter, Depends, Query
from odmantic import AIOEngine

from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.api.interactive.system_log_manager.system_log_manager import SystemLogManager
from orion.constants.constant import OrionIntelligence
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_system_log_model import SystemLogPageResponse
from orion.shared_models.responses import SuccessResponse, success_response


def get_system_log_service(engine: AIOEngine = Depends(get_engine)) -> SystemLogManager:
    return SystemLogManager(AuthProfileManager(engine))


router = APIRouter(prefix="/system-logs", tags=["System Logs"], dependencies=[Depends(require_admin())])


@router.get("", response_model=SuccessResponse[SystemLogPageResponse])
async def list_system_logs(
    date: str | None = Query(default=None),
    log_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=OrionIntelligence.SYSTEM_LOGS_DEFAULT_LIMIT, ge=1, le=OrionIntelligence.SYSTEM_LOGS_MAX_LIMIT),
    service: SystemLogManager = Depends(get_system_log_service),
):
    try:
        return success_response(message="System logs retrieved successfully.", data=await service.get_logs(date=date, log_type=log_type, date_from=date_from, date_to=date_to, page=page, limit=limit))
    finally:
        await service.close()
