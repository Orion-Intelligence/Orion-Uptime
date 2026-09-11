from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from urllib.parse import urlparse

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

from orion.constants.constant import Collections, Messages
from orion.helper_manager.target_policy import validate_target_host
from orion.management.jobs.monitoring_controller.monitor_repository import MonitorRepository
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_ping_monitor_model import PingMonitorModel, PingMonitorResponse
from orion.shared_models.exceptions import NotFoundError


class PingMonitorManager(MonitorRepository):
    model_class = PingMonitorModel

    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.PING_MONITORS]

    async def create_monitor(self, name: str, host: str, check_interval: int, timeout: int, expected_response_time_ms: int | None, created_by: str | None = None) -> PingMonitorResponse:
        now = datetime.now(UTC)
        monitor = PingMonitorModel(name=name, host=await self._validated_host(host), monitor_type=MonitorType.PING, check_interval=check_interval, timeout=timeout, expected_response_time_ms=expected_response_time_ms, created_by=created_by, is_active=True, status=MonitorStatus.UNKNOWN, created_at=now, updated_at=now)
        await self._insert_and_start(monitor, monitor.model_dump(exclude_none=True))
        return PingMonitorResponse(**monitor.model_dump())

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

    async def update_monitor(self, monitor_id: str, name: str | None = None, host: str | None = None, check_interval: int | None = None, timeout: int | None = None, expected_response_time_ms: int | None = None, is_active: bool | None = None, expected_response_time_ms_set: bool = False) -> PingMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if host is not None:
            monitor.host = await self._validated_host(host)
        self._apply_common_update(monitor, name=name, check_interval=check_interval, timeout=timeout, expected_response_time_ms=expected_response_time_ms, expected_response_time_ms_set=expected_response_time_ms_set, is_active=is_active)
        await self._replace_and_reschedule(monitor)
        return PingMonitorResponse(**monitor.model_dump())

    async def delete_monitor(self, monitor_id: str) -> None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND) from None
        await self._remove_monitor(monitor_id, object_id)

    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool:
        return await self._apply_monitoring_result(monitor_id, {"status": status, "last_response_time_ms": response_time_ms, "last_checked_at": checked_at})

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
