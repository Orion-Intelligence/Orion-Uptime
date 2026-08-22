from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.constants.constant import Collections, Messages
from orion.management.jobs.monitoring_controller.monitor_repository import MonitorRepository
from orion.services.mongo_manager.documents import with_string_id
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel, HeartbeatMonitorResponse, HeartbeatResponse, HeartbeatTokenResponse, RegenerateHeartbeatTokenResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError

if TYPE_CHECKING:
    from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager


class HeartbeatMonitorManager(MonitorRepository):
    def __init__(self, engine: AIOEngine, monitor_service: MonitorManager | None = None):
        self.collection = engine.database[Collections.HEARTBEAT_MONITORS]
        self.monitor_service = monitor_service

    async def create_monitor(self, name: str, expected_heartbeat_interval: int, grace_period: int, created_by: str | None = None) -> HeartbeatTokenResponse:
        token = uuid.uuid4().hex
        now = datetime.now(UTC)
        monitor = HeartbeatMonitorModel(
            name=name, monitor_type=MonitorType.HEARTBEAT, heartbeat_token_hash=hashlib.sha256(token.encode()).hexdigest(), expected_heartbeat_interval=expected_heartbeat_interval, grace_period=grace_period, created_by=created_by, is_active=True, status=MonitorStatus.UNKNOWN, last_token_rotated_at=now, token_expires_at=now + timedelta(days=90), created_at=now, updated_at=now
        )
        document = monitor.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(document)
        monitor.id = str(result.inserted_id)
        monitor.heartbeat_token = token
        realtime_broker.notify("monitor", monitor.id)
        return HeartbeatTokenResponse(heartbeat_token=monitor.heartbeat_token)

    async def get_monitor_model(self, monitor_id: str) -> HeartbeatMonitorModel | None:
        try:
            object_id = ObjectId(monitor_id)
        except (InvalidId, TypeError):
            return None
        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        document = with_string_id(document)
        return HeartbeatMonitorModel(**document)

    async def list_monitor_models(self) -> list[HeartbeatMonitorModel]:
        monitors = []
        async for document in self.collection.find().sort("created_at", -1):
            monitors.append(HeartbeatMonitorModel(**with_string_id(document)))
        return monitors

    async def get_monitor(self, monitor_id: str) -> HeartbeatMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        return HeartbeatMonitorResponse(
            id=monitor.persisted_id, name=monitor.name, expected_heartbeat_interval=monitor.expected_heartbeat_interval, grace_period=monitor.grace_period, status=monitor.status.value, is_active=monitor.is_active, last_heartbeat_at=monitor.last_heartbeat_at.isoformat() if monitor.last_heartbeat_at else None, created_at=monitor.created_at.isoformat(), updated_at=monitor.updated_at.isoformat()
        )

    async def list_monitors(self) -> list[HeartbeatMonitorResponse]:
        return [
            HeartbeatMonitorResponse(
                id=monitor.persisted_id, name=monitor.name, expected_heartbeat_interval=monitor.expected_heartbeat_interval, grace_period=monitor.grace_period, status=monitor.status.value, is_active=monitor.is_active, last_heartbeat_at=monitor.last_heartbeat_at.isoformat() if monitor.last_heartbeat_at else None, created_at=monitor.created_at.isoformat(), updated_at=monitor.updated_at.isoformat()
            )
            for monitor in await self.list_monitor_models()
        ]

    async def update_monitor(self, monitor_id: str, name: str | None = None, expected_heartbeat_interval: int | None = None, grace_period: int | None = None, is_active: bool | None = None) -> HeartbeatMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if name is not None:
            monitor.name = name
        if expected_heartbeat_interval is not None:
            monitor.expected_heartbeat_interval = expected_heartbeat_interval
        if grace_period is not None:
            monitor.grace_period = grace_period
        if is_active is not None:
            monitor.is_active = is_active
        monitor.updated_at = datetime.now(UTC)

        update_data = monitor.model_dump(by_alias=True, exclude={"id"})
        await self.collection.update_one({"_id": ObjectId(monitor_id)}, {"$set": update_data, "$unset": {"check_interval": ""}})
        updated = await self.get_monitor_model(monitor_id)
        if updated is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
            if updated.is_active and updated.last_heartbeat_at is not None:
                await scheduler_state.scheduler.start_worker(updated)
        realtime_broker.notify("monitor", updated.id)
        return HeartbeatMonitorResponse(
            id=updated.persisted_id, name=updated.name, expected_heartbeat_interval=updated.expected_heartbeat_interval, grace_period=updated.grace_period, status=updated.status.value, is_active=updated.is_active, last_heartbeat_at=updated.last_heartbeat_at.isoformat() if updated.last_heartbeat_at else None, created_at=updated.created_at.isoformat(), updated_at=updated.updated_at.isoformat()
        )

    async def delete_monitor(self, monitor_id: str) -> None:
        try:
            object_id = ObjectId(monitor_id)
        except (InvalidId, TypeError):
            raise NotFoundError(Messages.MONITOR_NOT_FOUND) from None
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
        result = await self.collection.delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.monitor_service.delete_monitor_history(monitor_id)
        realtime_broker.notify("monitor", monitor_id)

    async def regenerate_token(self, monitor_id: str) -> RegenerateHeartbeatTokenResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)
        new_token = uuid.uuid4().hex
        now = datetime.now(UTC)
        monitor.heartbeat_token_hash = hashlib.sha256(new_token.encode()).hexdigest()
        monitor.last_token_rotated_at = now
        monitor.token_expires_at = now + timedelta(days=90)
        monitor.updated_at = now

        update_data = monitor.model_dump(by_alias=True, exclude={"id"})
        await self.collection.update_one({"_id": ObjectId(monitor_id)}, {"$set": update_data, "$unset": {"check_interval": ""}})
        monitor.heartbeat_token = new_token
        realtime_broker.notify("monitor", monitor.id)
        return RegenerateHeartbeatTokenResponse(heartbeat_token=monitor.heartbeat_token)

    async def receive_heartbeat(self, token: str) -> HeartbeatResponse:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        document = await self.collection.find_one({"heartbeat_token_hash": token_hash})
        if document is None:
            raise NotFoundError("Invalid heartbeat token.")
        monitor = HeartbeatMonitorModel(**with_string_id(document))
        now = datetime.now(UTC)
        if not monitor.is_active:
            raise NotFoundError("Invalid heartbeat token.")
        if monitor.token_expires_at is not None and now > monitor.token_expires_at:
            raise NotFoundError("Invalid heartbeat token.")

        await self.collection.update_one({"_id": ObjectId(monitor.id)}, {"$set": {"last_heartbeat_at": now, "updated_at": now}, "$inc": {"heartbeat_count": 1}})
        await self._get_monitor_service().process_heartbeat(monitor)
        updated = await self.get_monitor_model(monitor.persisted_id)
        if updated is not None and scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.start_worker(updated)
        return HeartbeatResponse(message=Messages.HEARTBEAT_RECEIVED, expected_next_heartbeat_in=monitor.expected_heartbeat_interval, server_time=now, token_rotation_required=False)

    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool:
        try:
            object_id = ObjectId(monitor_id)
        except (InvalidId, TypeError):
            return False
        result = await self.collection.update_one({"_id": object_id}, {"$set": {"status": status, "last_checked_at": checked_at, "updated_at": datetime.now(UTC)}})
        return result.modified_count > 0

    def _get_monitor_service(self) -> MonitorManager:
        if self.monitor_service is not None:
            return self.monitor_service
        if scheduler_state.scheduler is None:
            raise RuntimeError("The monitor scheduler has not been initialized.")
        return scheduler_state.scheduler.monitor_service
