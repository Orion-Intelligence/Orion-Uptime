from __future__ import annotations

import re
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.constants.constant import Collections, Messages
from orion.helper_manager.target_policy import validate_target_url
from orion.management.jobs.monitoring_controller.monitor_repository import MonitorRepository
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_http_monitor_model import HTTPMonitorModel, HttpMonitorResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import ConflictError, NotFoundError


class HttpMonitorManager(MonitorRepository):
    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.HTTP_MONITORS]

    async def create_monitor(self, name: str, url: str, check_interval: int, timeout: int, expected_status_code: int, expected_response_time_ms: int | None) -> HttpMonitorResponse:
        await validate_target_url(url)
        if await self.collection.find_one({"url": url}) is not None:
            raise ConflictError(Messages.MONITOR_ALREADY_EXISTS)

        final_name = await self._unique_name(name)

        now = datetime.now(UTC)
        monitor = HTTPMonitorModel(name=final_name, url=url, check_interval=check_interval, timeout=timeout, expected_status_code=expected_status_code, status=MonitorStatus.UNKNOWN, is_active=True, created_at=now, updated_at=now, last_checked_at=None, expected_response_time_ms=expected_response_time_ms)
        document = monitor.model_dump()
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        monitor.id = str(result.inserted_id)

        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)
        return HttpMonitorResponse(**monitor.model_dump())

    async def list_monitor_models(self) -> list[HTTPMonitorModel]:
        cursor = self.collection.find().sort("created_at", -1)
        monitors = []
        async for document in cursor:
            monitors.append(HTTPMonitorModel(**with_string_id(document)))
        return monitors

    async def get_monitor_model(self, monitor_id: str) -> HTTPMonitorModel | None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return None
        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        document = with_string_id(document)
        return HTTPMonitorModel(**document)

    async def list_monitors(self) -> list[HttpMonitorResponse]:
        return [HttpMonitorResponse(**monitor.model_dump()) for monitor in await self.list_monitor_models()]

    async def get_monitor(self, http_monitor_id: str) -> HttpMonitorResponse:
        monitor = await self.get_monitor_model(http_monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        return HttpMonitorResponse(**monitor.model_dump())

    async def update_monitor(self, http_monitor_id: str, name: str | None, url: str | None, check_interval: int | None, timeout: int | None, expected_status_code: int | None, expected_response_time_ms: int | None, is_active: bool | None = None) -> HttpMonitorResponse:
        monitor = await self.get_monitor_model(http_monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        update_data = {}

        if name is not None and name != monitor.name:
            update_data["name"] = await self._unique_name(name)
        if url is not None and url != monitor.url:
            await validate_target_url(url)
            if await self.collection.find_one({"url": url, "_id": {"$ne": ObjectId(http_monitor_id)}}) is not None:
                raise ConflictError(Messages.MONITOR_ALREADY_EXISTS)
            update_data["url"] = url
        if check_interval is not None and check_interval != monitor.check_interval:
            update_data["check_interval"] = check_interval
        if timeout is not None and timeout != monitor.timeout:
            update_data["timeout"] = timeout
        if expected_status_code is not None and expected_status_code != monitor.expected_status_code:
            update_data["expected_status_code"] = expected_status_code
        if expected_response_time_ms is not None and expected_response_time_ms != monitor.expected_response_time_ms:
            update_data["expected_response_time_ms"] = expected_response_time_ms
        if is_active is not None and is_active != monitor.is_active:
            update_data["is_active"] = is_active

        if not update_data:
            return HttpMonitorResponse(**monitor.model_dump())

        update_data["updated_at"] = datetime.now(UTC)
        await self.collection.update_one({"_id": ObjectId(http_monitor_id)}, {"$set": update_data})
        updated_monitor = await self.get_monitor_model(http_monitor_id)
        if updated_monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(updated_monitor.persisted_id)
            if updated_monitor.is_active:
                await scheduler_state.scheduler.start_worker(updated_monitor)
        realtime_broker.notify("monitor", updated_monitor.id)
        return HttpMonitorResponse(**updated_monitor.model_dump())

    async def delete_monitor(self, http_monitor_id: str) -> None:
        monitor = await self.get_monitor_model(http_monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor.persisted_id)
        await self.collection.delete_one({"_id": ObjectId(monitor.id)})
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.monitor_service.delete_monitor_history(monitor.persisted_id)
        realtime_broker.notify("monitor", monitor.id)

    async def _unique_name(self, name: str) -> str:
        count = await self.collection.count_documents({"name": {"$regex": f"^{re.escape(name)}( \\d+)?$"}})
        return f"{name} {count}" if count > 0 else name

    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return False
        result = await self.collection.update_one({"_id": object_id}, {"$set": {"status": status, "last_status_code": status_code, "last_response_time_ms": response_time_ms, "last_checked_at": checked_at, "updated_at": checked_at}})
        return result.modified_count > 0
