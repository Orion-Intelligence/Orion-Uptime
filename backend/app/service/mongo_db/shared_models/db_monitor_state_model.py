from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus, MonitorType
from app.service.mongo_db.shared_models.persisted_model import PersistedModel


class MonitorTransition(str, Enum):
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
