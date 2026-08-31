from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.constants.constant import Messages
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import BaseMonitorModel, MonitorStatus
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError


class MonitorRepository(ABC):
    collection: Any

    @abstractmethod
    async def get_monitor_model(self, monitor_id: str) -> BaseMonitorModel | HeartbeatMonitorModel | None: ...

    @abstractmethod
    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool: ...

    @staticmethod
    def _object_id(monitor_id: str) -> ObjectId | None:
        try:
            return ObjectId(monitor_id)
        except (InvalidId, TypeError):
            return None

    async def _remove_monitor(self, monitor_id: str, object_id: ObjectId) -> None:
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
        result = await self.collection.delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.monitor_service.delete_monitor_history(monitor_id)
        realtime_broker.notify("monitor", monitor_id)

    async def _apply_monitoring_result(self, monitor_id: str, changes: dict) -> bool:
        object_id = self._object_id(monitor_id)
        if object_id is None:
            return False
        result = await self.collection.update_one({"_id": object_id}, {"$set": changes})
        return result.modified_count > 0
