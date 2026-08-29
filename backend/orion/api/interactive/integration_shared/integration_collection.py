from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bson import ObjectId

from orion.constants.constant import Limits
from orion.shared_models.exceptions import ValidationError

if TYPE_CHECKING:
    from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager



class IntegrationCollectionMixin:
    collection: Any
    monitor_service: MonitorManager

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
