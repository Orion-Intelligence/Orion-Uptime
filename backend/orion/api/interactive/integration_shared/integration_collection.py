from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from orion.constants.constant import Limits
from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorTransition
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.realtime_manager.realtime import realtime_broker
from orion.shared_models.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable

    from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager, MonitorModel
    from orion.services.mongo_manager.shared_model.db_monitor_state_model import MonitorStateResult



class IntegrationCollectionMixin:
    collection: Any
    monitor_service: MonitorManager
    not_found_message: str
    realtime_channel: str

    @staticmethod
    def _object_id(value: str) -> ObjectId | None:
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return None

    @staticmethod
    def _transition_direction(state_result: MonitorStateResult) -> bool | None:
        if state_result.transition == MonitorTransition.DOWN:
            return True
        if state_result.transition == MonitorTransition.UP and state_result.previous_status == MonitorStatus.DOWN:
            return False
        return None

    async def _integrations_for_transition(self, monitor: MonitorModel, state_result: MonitorStateResult, load: Callable[[dict], object | None]) -> tuple[bool, list] | None:
        direction = self._transition_direction(state_result)
        if direction is None:
            return None
        integrations = []
        async for document in self.collection.find({"monitor_ids": monitor.persisted_id}):
            loaded = load(document)
            if loaded is not None:
                integrations.append(loaded)
        if not integrations:
            return None
        return direction, integrations

    async def _apply_update(self, object_id: ObjectId, update_data: dict, requested_name: str | None) -> None:
        if requested_name is not None:
            suffix = 0
            while True:
                name = await self._unique_name(requested_name, exclude_id=object_id, suffix=suffix)
                named_update = {**update_data, "name": name, "name_key": self._name_key(name), "updated_at": datetime.now(UTC)}
                try:
                    await self.collection.update_one({"_id": object_id}, {"$set": named_update})
                    break
                except DuplicateKeyError:
                    suffix += 1
        elif update_data:
            update_data["updated_at"] = datetime.now(UTC)
            await self.collection.update_one({"_id": object_id}, {"$set": update_data})

    async def delete_integration(self, integration_id: str) -> None:
        object_id = self._object_id(integration_id)
        if object_id is None:
            raise NotFoundError(self.not_found_message)
        result = await self.collection.delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise NotFoundError(self.not_found_message)
        realtime_broker.notify(self.realtime_channel, integration_id)

    async def _validated_monitor_ids(self, monitor_ids: list[str]) -> list[str]:
        unique_ids = list(dict.fromkeys(monitor_ids))
        available_ids = {monitor.id for monitor in await self.monitor_service.list_monitors() if monitor.id is not None}
        missing = [monitor_id for monitor_id in unique_ids if monitor_id not in available_ids]
        if missing:
            raise ValidationError(f"Unknown monitor IDs: {', '.join(missing)}")
        return unique_ids

    async def _unique_name(self, base_name: str, exclude_id: ObjectId | None = None, suffix: int = 0) -> str:
        while True:
            candidate = self._candidate_name(base_name, suffix)
            query: dict = {"name_key": self._name_key(candidate)}
            if exclude_id is not None:
                query["_id"] = {"$ne": exclude_id}
            if await self.collection.find_one(query, {"_id": 1}) is None:
                return candidate
            suffix += 1

    @staticmethod
    def _candidate_name(base_name: str, suffix: int) -> str:
        suffix_text = "" if suffix == 0 else str(suffix)
        return f"{base_name[: Limits.INTEGRATION_NAME_MAX_LENGTH - len(suffix_text)]}{suffix_text}"

    @staticmethod
    def _name_key(name: str) -> str:
        return name.casefold()
