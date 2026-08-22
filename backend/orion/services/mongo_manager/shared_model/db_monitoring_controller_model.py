from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from orion.services.mongo_manager.shared_model.persisted_model import PersistedModel


class MonitorStatus(StrEnum):
    UNKNOWN = "unknown"
    UP = "up"
    DOWN = "down"


class MonitorType(StrEnum):
    HTTP = "HTTP"
    API = "API"
    PING = "ping"
    HEARTBEAT = "heartbeat"


class BaseMonitorModel(PersistedModel):
    name: str
    monitor_type: MonitorType
    check_interval: int
    timeout: int
    is_active: bool = True
    status: MonitorStatus = MonitorStatus.UNKNOWN
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None = None
    last_response_time_ms: int | None = None
    last_status_code: int | None = None


class HealthCheckResponse(BaseModel):
    url: str
    status: MonitorStatus
    status_code: int | None
    response_time_ms: int | None
    success: bool
    is_slow: bool = False
    error: str | None = None
    timed_out: bool = False
