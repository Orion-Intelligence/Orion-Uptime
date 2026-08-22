from datetime import UTC, datetime

from pydantic import ConfigDict

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from orion.services.mongo_manager.shared_model.persisted_model import PersistedModel


class IncidentModel(PersistedModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    monitor_id: str
    monitor_type: MonitorType
    started_at: datetime
    resolved_at: datetime | None = None
    reason: str
    status_code: int | None = None
    is_resolved: bool = False

    @property
    def duration_seconds(self) -> int:
        end = self.resolved_at or datetime.now(UTC)
        return int((end - self.started_at).total_seconds())
