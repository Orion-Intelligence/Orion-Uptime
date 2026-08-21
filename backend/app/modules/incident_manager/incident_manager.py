from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

from app.service.constants import Collections
from app.service.mongo_db.documents import with_string_id
from app.service.mongo_db.shared_models.db_incident_model import IncidentModel
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorType


class IncidentManager:
    def __init__(self, engine: AIOEngine):
        self.collection = engine.database[Collections.INCIDENTS]

    async def open_incident(self, monitor_id: str, monitor_type: MonitorType, reason: str, status_code: int | None = None) -> None:
        active = await self.get_active_incident(monitor_id, monitor_type)
        if active is not None:
            return

        incident = IncidentModel(
            monitor_id=monitor_id,
            monitor_type=monitor_type,
            started_at=datetime.now(UTC),
            resolved_at=None,
            is_resolved=False,
            reason=reason,
            status_code=status_code,
        )
        document = incident.model_dump()
        document.pop("id", None)
        result = await self.collection.insert_one(document)
        incident.id = str(result.inserted_id)

    async def resolve_incident(self, monitor_id: str, monitor_type: MonitorType) -> bool:
        incident = await self.get_active_incident(monitor_id, monitor_type)
        if incident is None:
            return False

        try:
            object_id = ObjectId(incident.id)
        except InvalidId:
            return False
        result = await self.collection.update_one(
            {
                "_id": object_id,
                "monitor_type": monitor_type,
                "resolved_at": None,
            },
            {
                "$set": {
                    "is_resolved": True,
                    "resolved_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count > 0

    async def get_active_incident(self, monitor_id: str, monitor_type: MonitorType) -> IncidentModel | None:
        document = await self.collection.find_one(
            {
                "monitor_id": monitor_id,
                "monitor_type": monitor_type,
                "resolved_at": None,
            }
        )
        if document is None:
            return None
        document = with_string_id(document)
        return IncidentModel(**document)

    async def count_open(self) -> int:
        return await self.collection.count_documents({"is_resolved": False})

    async def get_recent(self, limit: int = 10) -> list[IncidentModel]:
        cursor = self.collection.find().sort("started_at", -1).limit(limit)
        incidents = []
        async for document in cursor:
            incidents.append(IncidentModel(**with_string_id(document)))
        return incidents

    async def get_for_monitors(self, monitor_ids: list[str]) -> dict[str, list[IncidentModel]]:
        if not monitor_ids:
            return {}
        cursor = self.collection.find(
            {"monitor_id": {"$in": monitor_ids}}
        ).sort("started_at", -1)
        incidents: dict[str, list[IncidentModel]] = {}
        async for document in cursor:
            incident = IncidentModel(**with_string_id(document))
            incidents.setdefault(incident.monitor_id, []).append(incident)
        return incidents

    async def delete_for_monitor(self, monitor_id: str) -> None:
        await self.collection.delete_many({"monitor_id": monitor_id})
