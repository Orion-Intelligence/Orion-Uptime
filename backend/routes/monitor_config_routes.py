from fastapi import APIRouter, Depends, Query
from odmantic import AIOEngine

from orion.api.interactive.api_monitor_manager.api_monitor_manager import ApiMonitorManager
from orion.api.interactive.heartbeat_monitor_manager.heartbeat_monitor_manager import HeartbeatMonitorManager
from orion.api.interactive.http_monitor_manager.http_monitor_manager import HttpMonitorManager
from orion.api.interactive.monitor_config_manager.monitor_config_manager import MonitorConfigManager
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.api.interactive.ping_monitor_manager.ping_monitor_manager import PingMonitorManager
from orion.services.auth.authorization import require_admin
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_monitor_config_model import MonitorConfigDocument, MonitorImportResult
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from orion.shared_models.exceptions import ValidationError
from orion.shared_models.responses import SuccessResponse, success_response


def get_monitor_config_service(engine: AIOEngine = Depends(get_engine)) -> MonitorConfigManager:
    return MonitorConfigManager(
        http_monitors=HttpMonitorManager(engine),
        api_monitors=ApiMonitorManager(engine, AuthProfileManager(engine)),
        ping_monitors=PingMonitorManager(engine),
        heartbeat_monitors=HeartbeatMonitorManager(engine),
    )


router = APIRouter(prefix="/monitor-configs", tags=["Monitor Configurations"], dependencies=[Depends(require_admin())])


@router.post("/import", response_model=SuccessResponse[MonitorImportResult])
async def import_monitor(config: MonitorConfigDocument, expected_monitor_type: MonitorType | None = Query(default=None), service: MonitorConfigManager = Depends(get_monitor_config_service)):
    if expected_monitor_type is not None and config.monitor_type != expected_monitor_type:
        raise ValidationError(f"This configuration is for a {config.monitor_type.value} monitor and cannot be imported from the {expected_monitor_type.value} monitors tab.")
    result = await service.import_monitor(config)
    return success_response(message=f"Monitor configuration {result.action} successfully.", data=result)


@router.get("/{monitor_type}/{monitor_id}", response_model=SuccessResponse[MonitorConfigDocument])
async def export_monitor(monitor_type: MonitorType, monitor_id: str, service: MonitorConfigManager = Depends(get_monitor_config_service)):
    return success_response(message="Monitor configuration exported successfully.", data=await service.export_monitor(monitor_type, monitor_id))
