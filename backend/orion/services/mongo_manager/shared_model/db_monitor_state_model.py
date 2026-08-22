from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.persisted_model import PersistedModel


class MonitorTransition(StrEnum):
    NONE = "none"
    DOWN = "down"
    UP = "up"


class MonitorStateModel(PersistedModel):
    monitor_id: str
    monitor_type: MonitorType
    status: MonitorStatus = MonitorStatus.UNKNOWN
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_checked_at: datetime | None = None
    last_status_code: int | None = None
    last_response_time_ms: int | None = None


class MonitorStateResult(BaseModel):
    state: MonitorStateModel
    previous_status: MonitorStatus
    current_status: MonitorStatus
    transition: MonitorTransition
