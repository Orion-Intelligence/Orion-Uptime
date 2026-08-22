from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from urllib.parse import urlparse

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.constants.constant import Collections, Messages
from orion.helper_manager.target_policy import validate_target_host
from orion.management.jobs.monitoring_controller.monitor_repository import MonitorRepository
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_ping_monitor_model import PingMonitorModel, PingMonitorResponse
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError


class PingMonitorManager(MonitorRepository):
    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.PING_MONITORS]

    async def create_monitor(self, name: str, host: str, check_interval: int, timeout: int, expected_response_time_ms: int | None, created_by: str | None = None) -> PingMonitorResponse:
        now = datetime.now(UTC)
        monitor = PingMonitorModel(name=name, host=await self._validated_host(host), monitor_type=MonitorType.PING, check_interval=check_interval, timeout=timeout, expected_response_time_ms=expected_response_time_ms, created_by=created_by, is_active=True, status=MonitorStatus.UNKNOWN, created_at=now, updated_at=now)
        document = monitor.model_dump(exclude_none=True)
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        monitor.id = str(result.inserted_id)

        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)
        return PingMonitorResponse(**monitor.model_dump())

    async def get_monitor_model(self, monitor_id: str) -> PingMonitorModel | None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return None
        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        document = with_string_id(document)
        return PingMonitorModel(**document)

    async def list_monitor_models(self) -> list[PingMonitorModel]:
        monitors = []
        async for document in self.collection.find():
            monitors.append(PingMonitorModel(**with_string_id(document)))
        return monitors

    async def get_monitor(self, monitor_id: str) -> PingMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        return PingMonitorResponse(**monitor.model_dump())

    async def list_monitors(self) -> list[PingMonitorResponse]:
        return [PingMonitorResponse(**monitor.model_dump()) for monitor in await self.list_monitor_models()]

    async def update_monitor(self, monitor_id: str, name: str | None = None, host: str | None = None, check_interval: int | None = None, timeout: int | None = None, expected_response_time_ms: int | None = None, is_active: bool | None = None) -> PingMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if name is not None:
            monitor.name = name
        if host is not None:
            monitor.host = await self._validated_host(host)
        if check_interval is not None:
            monitor.check_interval = check_interval
        if timeout is not None:
            monitor.timeout = timeout
        if expected_response_time_ms is not None:
            monitor.expected_response_time_ms = expected_response_time_ms
        if is_active is not None:
            monitor.is_active = is_active
        monitor.updated_at = datetime.now(UTC)

        document = monitor.model_dump()
        document.pop("id", None)
        await self.collection.replace_one({"_id": ObjectId(monitor_id)}, document)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
            if monitor.is_active:
                await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)
        return PingMonitorResponse(**monitor.model_dump())

    async def delete_monitor(self, monitor_id: str) -> None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND) from None
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
        result = await self.collection.delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.monitor_service.delete_monitor_history(monitor_id)
        realtime_broker.notify("monitor", monitor_id)

    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return False
        result = await self.collection.update_one({"_id": object_id}, {"$set": {"status": status, "last_response_time_ms": response_time_ms, "last_checked_at": checked_at}})
        return result.modified_count > 0

    async def _validated_host(self, host: str) -> str:
        normalized = self._normalize_host(host)
        await validate_target_host(normalized)
        return normalized

    @staticmethod
    def _normalize_host(host: str) -> str:
        host = host.strip()
        if "://" in host:
            hostname = urlparse(host).hostname
            if hostname:
                host = hostname
        host = host.rstrip("/")
        if ":" in host:
            try:
                ipaddress.ip_address(host)
            except ValueError:
                host = host.split(":")[0]
        return host.lower()
