from abc import ABC, abstractmethod
from datetime import datetime

from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import BaseMonitorModel, MonitorStatus


class MonitorRepository(ABC):
    @abstractmethod
    async def get_monitor_model(self, monitor_id: str) -> BaseMonitorModel | HeartbeatMonitorModel | None: ...

    @abstractmethod
    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool: ...
