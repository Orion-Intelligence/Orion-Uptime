from datetime import datetime

from pydantic import BaseModel, Field

from orion.constants.constant import OrionIntelligence
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import BaseMonitorModel, HealthCheckResponse, MonitorStatus, MonitorType


def feeder_result_id(monitor_id: str, feeder_key: str) -> str:
    return f"{monitor_id}{OrionIntelligence.FEEDER_RESULT_SEPARATOR}{feeder_key}"


class OrionFeederStatus(BaseModel):
    key: str
    name: str
    rule_key: str | None = None
    section: str | None = None
    status: MonitorStatus = MonitorStatus.UNKNOWN
    enabled: bool = True
    last_checked_at: datetime | None = None
    message: str | None = None


class OrionScriptMonitorModel(BaseMonitorModel):
    url: str
    monitor_type: MonitorType = MonitorType.ORION_SCRIPT
    expected_response_time_ms: int | None = None
    feeders: list[OrionFeederStatus] = Field(default_factory=list)


class OrionScriptCheckResponse(HealthCheckResponse):
    feeders: list[OrionFeederStatus] = Field(default_factory=list)


class CreateOrionScriptMonitorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    expected_response_time_ms: int | None = None
    check_interval: int = Field(default=300, ge=10, le=86400)
    timeout: int = Field(default=30, ge=1, le=300)


class UpdateOrionScriptMonitorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    expected_response_time_ms: int | None = None
    check_interval: int | None = Field(default=None, ge=10, le=86400)
    timeout: int | None = Field(default=None, ge=1, le=300)
    is_active: bool | None = None


class OrionScriptMonitorResponse(BaseModel):
    id: str
    name: str
    url: str
    check_interval: int
    timeout: int
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
    last_response_time_ms: int | None
    last_status_code: int | None = None
    status: MonitorStatus
    expected_response_time_ms: int | None
    feeders: list[OrionFeederStatus] = Field(default_factory=list)
