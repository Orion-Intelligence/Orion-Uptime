from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.constants.constant import Messages
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import BaseMonitorModel, MonitorStatus
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError


class MonitorRepository(ABC):
    collection: Any
    model_class: Any

    async def get_monitor_model(self, monitor_id: str) -> BaseMonitorModel | HeartbeatMonitorModel | None:
        object_id = self._object_id(monitor_id)
        if object_id is None:
            return None
        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        return self.model_class(**with_string_id(document))

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

    async def _insert_and_start(self, monitor: Any, document: dict) -> None:
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        monitor.id = str(result.inserted_id)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)

    async def _reschedule_and_notify(self, monitor: Any) -> None:
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor.persisted_id)
            if monitor.is_active:
                await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)

    @staticmethod
    def _apply_common_update(monitor: Any, *, name: str | None, check_interval: int | None, timeout: int | None, expected_response_time_ms: int | None, expected_response_time_ms_set: bool, is_active: bool | None) -> None:
        if name is not None:
            monitor.name = name
        if check_interval is not None:
            monitor.check_interval = check_interval
        if timeout is not None:
            monitor.timeout = timeout
        if expected_response_time_ms_set or expected_response_time_ms is not None:
            monitor.expected_response_time_ms = expected_response_time_ms
        if is_active is not None:
            monitor.is_active = is_active

    async def _replace_and_reschedule(self, monitor: Any) -> None:
        monitor.updated_at = datetime.now(UTC)
        document = monitor.model_dump()
        document.pop("id", None)
        await self.collection.replace_one({"_id": ObjectId(monitor.persisted_id)}, document)
        await self._reschedule_and_notify(monitor)

    async def _apply_update(self, monitor_id: str, update_data: dict) -> Any:
        update_data["updated_at"] = datetime.now(UTC)
        result = await self.collection.update_one({"_id": ObjectId(monitor_id)}, {"$set": update_data})
        if result.matched_count == 0:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        updated = await self.get_monitor_model(monitor_id)
        if updated is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        await self._reschedule_and_notify(updated)
        return updated
