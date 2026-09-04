from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.constants.constant import Collections, Messages
from orion.helper_manager.target_policy import validate_target_url
from orion.management.jobs.monitoring_controller.checkers.orion_script_checker import OrionScriptChecker
from orion.management.jobs.monitoring_controller.monitor_repository import MonitorRepository
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionFeederStatus, OrionScriptMonitorModel, OrionScriptMonitorResponse
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import ConflictError, NotFoundError, ValidationError


class OrionScriptMonitorManager(MonitorRepository):
    def __init__(self, engine: AIOEngine, auth_profile_service: AuthProfileManager | None = None):
        self.collection = engine.database[Collections.ORION_SCRIPT_MONITORS]
        self.auth_profile_service = auth_profile_service

    async def create_monitor(self, name: str, url: str, check_interval: int, timeout: int, expected_response_time_ms: int | None, created_by: str | None = None) -> OrionScriptMonitorResponse:
        url = await self._validated_url(url)
        if await self.collection.find_one({"url": url}) is not None:
            raise ConflictError(Messages.MONITOR_ALREADY_EXISTS)

        now = datetime.now(UTC)
        monitor = OrionScriptMonitorModel(name=name, url=url, monitor_type=MonitorType.ORION_SCRIPT, check_interval=check_interval, timeout=timeout, expected_response_time_ms=expected_response_time_ms, created_by=created_by, is_active=True, status=MonitorStatus.UNKNOWN, created_at=now, updated_at=now)
        document = monitor.model_dump()
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        monitor.id = str(result.inserted_id)

        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)
        return OrionScriptMonitorResponse(**monitor.model_dump())

    async def get_monitor_model(self, monitor_id: str) -> OrionScriptMonitorModel | None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return None
        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        return OrionScriptMonitorModel(**with_string_id(document))

    async def list_monitor_models(self) -> list[OrionScriptMonitorModel]:
        monitors = []
        async for document in self.collection.find():
            monitors.append(OrionScriptMonitorModel(**with_string_id(document)))
        return monitors

    async def get_monitor(self, monitor_id: str) -> OrionScriptMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        return OrionScriptMonitorResponse(**monitor.model_dump())

    async def list_monitors(self) -> list[OrionScriptMonitorResponse]:
        return [OrionScriptMonitorResponse(**monitor.model_dump()) for monitor in await self.list_monitor_models()]

    async def update_monitor(self, monitor_id: str, name: str | None = None, url: str | None = None, check_interval: int | None = None, timeout: int | None = None, expected_response_time_ms: int | None = None, is_active: bool | None = None, expected_response_time_ms_set: bool = False) -> OrionScriptMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if name is not None:
            monitor.name = name
        if url is not None:
            url = await self._validated_url(url)
            if await self.collection.find_one({"url": url, "_id": {"$ne": ObjectId(monitor_id)}}) is not None:
                raise ConflictError(Messages.MONITOR_ALREADY_EXISTS)
            monitor.url = url
        if check_interval is not None:
            monitor.check_interval = check_interval
        if timeout is not None:
            monitor.timeout = timeout
        if expected_response_time_ms_set or expected_response_time_ms is not None:
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
        return OrionScriptMonitorResponse(**monitor.model_dump())

    async def delete_monitor(self, monitor_id: str) -> None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND) from None
        await self._remove_monitor(monitor_id, object_id)

    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool:
        return await self._apply_monitoring_result(monitor_id, {"status": status, "last_status_code": status_code, "last_response_time_ms": response_time_ms, "last_checked_at": checked_at})

    async def store_feeders(self, monitor_id: str, feeders: list[OrionFeederStatus]) -> bool:
        return await self._apply_monitoring_result(monitor_id, {"feeders": [feeder.model_dump() for feeder in feeders]})

    async def _validated_url(self, url: str) -> str:
        url = url.strip().rstrip("/")
        await validate_target_url(url)
        if self.auth_profile_service is not None and OrionScriptChecker.find_profile(await self.auth_profile_service.list_profile_models(), url) is None:
            raise ValidationError("No auth profile logs into this Orion Intelligence instance. Create an auth profile whose login URL is on the same origin first.")
        return url
