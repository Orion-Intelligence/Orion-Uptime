from datetime import datetime

from pydantic import BaseModel, Field

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import BaseMonitorModel, MonitorStatus, MonitorType


class PingMonitorModel(BaseMonitorModel):
    host: str
    monitor_type: MonitorType = MonitorType.PING
    expected_response_time_ms: int | None = None


class CreatePingMonitorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    expected_response_time_ms: int | None = None
    check_interval: int = Field(ge=10, le=86400)
    timeout: int = Field(ge=1, le=300)


class UpdatePingMonitorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    expected_response_time_ms: int | None = None
    check_interval: int | None = Field(default=None, ge=10, le=86400)
    timeout: int | None = Field(default=None, ge=1, le=300)
    is_active: bool | None = None


class PingMonitorResponse(BaseModel):
    id: str
    name: str
    host: str
    check_interval: int
    timeout: int
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
    last_response_time_ms: int | None
    status: MonitorStatus
    expected_response_time_ms: int | None
