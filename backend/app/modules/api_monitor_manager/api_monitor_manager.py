from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

import app.modules.monitoring_controller.scheduler as scheduler_state
from app.modules.monitoring_controller.monitor_repository import MonitorRepository
from app.modules.orion_login_manager.orion_login_manager import AuthProfileManager
from app.service.constants import Collections, Messages
from app.service.exceptions import ConflictError, NotFoundError
from app.service.mongo_db.documents import with_string_id
from app.service.mongo_db.shared_models.db_api_monitor_model import APIMonitorModel, ApiMonitorResponse, CreateApiMonitorRequest, UpdateApiMonitorRequest
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus
from app.service.realtime import realtime_broker
from app.service.target_policy import validate_target_url


class API_monitorManager(MonitorRepository):
    def __init__(self, engine: AIOEngine, auth_profile_service: AuthProfileManager | None = None):
        self.collection = engine.database[Collections.API_MONITORS]
        self.auth_profile_service = auth_profile_service

    async def create_monitor(self, request: CreateApiMonitorRequest, created_by: str | None = None) -> ApiMonitorResponse:
        if await self.collection.find_one({"name": request.name}) is not None:
            raise ConflictError("API monitor with this name already exists.")
        await validate_target_url(request.url)
        if await self.collection.find_one({"url": request.url}) is not None:
            raise ConflictError("API monitor for this URL already exists.")

        await self._validate_auth_profile(request.auth_profile_id)
        now = datetime.now(UTC)
        monitor = APIMonitorModel(
            name=request.name,
            url=request.url,
            method=request.method,
            headers=request.headers,
            request_body=request.request_body,
            expected_status_code=request.expected_status_code,
            expected_response_time_ms=request.expected_response_time_ms,
            expected_json=request.expected_json,
            check_interval=request.check_interval,
            timeout=request.timeout,
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            last_checked_at=None,
            last_status_code=None,
            last_response_time_ms=None,
            expected_headers=request.expected_headers,
            expected_content_type=request.expected_content_type,
            auth_profile_id=request.auth_profile_id,
        )
        document = monitor.model_dump()
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        monitor.id = str(result.inserted_id)

        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.start_worker(monitor)
        realtime_broker.notify("monitor", monitor.id)
        return ApiMonitorResponse(
            id=monitor.id,
            name=monitor.name,
            url=monitor.url,
            method=monitor.method,
            headers=monitor.headers,
            request_body=monitor.request_body,
            expected_status_code=monitor.expected_status_code,
            expected_json=monitor.expected_json,
            check_interval=monitor.check_interval,
            timeout=monitor.timeout,
            is_active=monitor.is_active,
            created_by=monitor.created_by,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            last_checked_at=monitor.last_checked_at,
            last_status_code=monitor.last_status_code,
            last_response_time_ms=monitor.last_response_time_ms,
            status=monitor.status,
            expected_response_time_ms=monitor.expected_response_time_ms,
            expected_headers=monitor.expected_headers,
            expected_content_type=monitor.expected_content_type,
            auth_profile_id=monitor.auth_profile_id,
        )

    async def get_monitor_model(self, monitor_id: str) -> APIMonitorModel | None:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return None
        document = await self.collection.find_one({"_id": object_id})
        if document is None:
            return None
        document = with_string_id(document)
        return APIMonitorModel(**document)

    async def list_monitor_models(self) -> list[APIMonitorModel]:
        cursor = self.collection.find().sort("created_at", -1)
        monitors = []
        async for document in cursor:
            monitors.append(APIMonitorModel(**with_string_id(document)))
        return monitors

    async def get_monitor(self, monitor_id: str) -> ApiMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.monitor_NOT_FOUND)
        return ApiMonitorResponse(
            id=monitor.persisted_id,
            name=monitor.name,
            url=monitor.url,
            method=monitor.method,
            headers=monitor.headers,
            request_body=monitor.request_body,
            expected_status_code=monitor.expected_status_code,
            expected_json=monitor.expected_json,
            check_interval=monitor.check_interval,
            timeout=monitor.timeout,
            is_active=monitor.is_active,
            created_by=monitor.created_by,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            last_checked_at=monitor.last_checked_at,
            last_status_code=monitor.last_status_code,
            last_response_time_ms=monitor.last_response_time_ms,
            status=monitor.status,
            expected_response_time_ms=monitor.expected_response_time_ms,
            expected_headers=monitor.expected_headers,
            expected_content_type=monitor.expected_content_type,
            auth_profile_id=monitor.auth_profile_id,
        )

    async def list_monitors(self) -> list[ApiMonitorResponse]:
        monitors = await self.list_monitor_models()
        return [
            ApiMonitorResponse(
                id=monitor.persisted_id,
                name=monitor.name,
                url=monitor.url,
                method=monitor.method,
                headers=monitor.headers,
                request_body=monitor.request_body,
                expected_status_code=monitor.expected_status_code,
                expected_json=monitor.expected_json,
                check_interval=monitor.check_interval,
                timeout=monitor.timeout,
                is_active=monitor.is_active,
                created_by=monitor.created_by,
                created_at=monitor.created_at,
                updated_at=monitor.updated_at,
                last_checked_at=monitor.last_checked_at,
                last_status_code=monitor.last_status_code,
                last_response_time_ms=monitor.last_response_time_ms,
                status=monitor.status,
                expected_response_time_ms=monitor.expected_response_time_ms,
                expected_headers=monitor.expected_headers,
                expected_content_type=monitor.expected_content_type,
                auth_profile_id=monitor.auth_profile_id,
            )
            for monitor in monitors
        ]

    async def update_monitor(self, monitor_id: str, request: UpdateApiMonitorRequest) -> ApiMonitorResponse:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.monitor_NOT_FOUND)

        update_data = request.model_dump(exclude_unset=True)
        other_monitors = {"_id": {"$ne": ObjectId(monitor_id)}}
        if "name" in update_data and await self.collection.find_one({"name": update_data["name"], **other_monitors}) is not None:
            raise ConflictError("API monitor with this name already exists.")
        if "url" in update_data:
            await validate_target_url(update_data["url"])
        if "url" in update_data and await self.collection.find_one({"url": update_data["url"], **other_monitors}) is not None:
            raise ConflictError("API monitor for this URL already exists.")
        if "auth_profile_id" in update_data:
            await self._validate_auth_profile(update_data["auth_profile_id"])

        update_data["updated_at"] = datetime.now(UTC)
        result = await self.collection.update_one(
            {"_id": ObjectId(monitor_id)},
            {"$set": update_data},
        )
        if result.matched_count == 0:
            raise NotFoundError(Messages.monitor_NOT_FOUND)
        updated_monitor = await self.get_monitor_model(monitor_id)
        if updated_monitor is None:
            raise NotFoundError(Messages.monitor_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
            if updated_monitor.is_active:
                await scheduler_state.scheduler.start_worker(updated_monitor)
        realtime_broker.notify("monitor", updated_monitor.id)
        return ApiMonitorResponse(
            id=updated_monitor.persisted_id,
            name=updated_monitor.name,
            url=updated_monitor.url,
            method=updated_monitor.method,
            headers=updated_monitor.headers,
            request_body=updated_monitor.request_body,
            expected_status_code=updated_monitor.expected_status_code,
            expected_json=updated_monitor.expected_json,
            check_interval=updated_monitor.check_interval,
            timeout=updated_monitor.timeout,
            is_active=updated_monitor.is_active,
            created_by=updated_monitor.created_by,
            created_at=updated_monitor.created_at,
            updated_at=updated_monitor.updated_at,
            last_checked_at=updated_monitor.last_checked_at,
            last_status_code=updated_monitor.last_status_code,
            last_response_time_ms=updated_monitor.last_response_time_ms,
            status=updated_monitor.status,
            expected_response_time_ms=updated_monitor.expected_response_time_ms,
            expected_headers=updated_monitor.expected_headers,
            expected_content_type=updated_monitor.expected_content_type,
            auth_profile_id=updated_monitor.auth_profile_id,
        )

    async def delete_monitor(self, monitor_id: str) -> None:
        monitor = await self.get_monitor_model(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.monitor_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.stop_worker(monitor_id)
        result = await self.collection.delete_one({"_id": ObjectId(monitor_id)})
        if result.deleted_count == 0:
            raise NotFoundError(Messages.monitor_NOT_FOUND)
        if scheduler_state.scheduler is not None:
            await scheduler_state.scheduler.monitor_service.delete_monitor_history(monitor_id)
        realtime_broker.notify("monitor", monitor_id)

    async def update_monitoring_result(self, monitor_id: str, status: MonitorStatus, status_code: int | None, response_time_ms: int | None, checked_at: datetime) -> bool:
        try:
            object_id = ObjectId(monitor_id)
        except InvalidId:
            return False
        result = await self.collection.update_one(
            {"_id": object_id},
            {
                "$set": {
                    "status": status,
                    "last_status_code": status_code,
                    "last_response_time_ms": response_time_ms,
                    "last_checked_at": checked_at,
                    "updated_at": checked_at,
                }
            },
        )
        return result.modified_count > 0

    async def _validate_auth_profile(self, profile_id: str | None) -> None:
        if profile_id is None:
            return
        if self.auth_profile_service is None:
            raise NotFoundError("Auth profile validation is unavailable.")
        if await self.auth_profile_service.get_profile_model(profile_id) is None:
            raise NotFoundError("Auth profile not found.")
