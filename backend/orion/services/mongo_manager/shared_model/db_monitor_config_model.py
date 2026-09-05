from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType


class MonitorConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["orion-monitor-config"] = "orion-monitor-config"
    version: Literal[1] = 1
    monitor_id: str | None = None
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class HttpMonitorConfig(MonitorConfigBase):
    monitor_type: Literal[MonitorType.HTTP]
    url: str = Field(max_length=500)
    check_interval: int = Field(ge=10, le=86400)
    timeout: int = Field(gt=0)
    expected_status_code: int = Field(ge=100, le=599)
    expected_response_time_ms: int | None = Field(default=None, ge=0)
    auth_profile_id: str | None = None
    auth_profile_name: str | None = Field(default=None, min_length=1, max_length=100)


class ApiMonitorConfig(MonitorConfigBase):
    monitor_type: Literal[MonitorType.API]
    url: str = Field(max_length=500)
    method: str = Field(default="GET", max_length=10)
    headers: dict[str, str] = Field(default_factory=dict)
    request_body: dict | None = None
    expected_status_code: int = Field(ge=100, le=599)
    expected_json: dict | None = None
    check_interval: int = Field(ge=10, le=86400)
    timeout: int = Field(default=10, gt=0)
    expected_response_time_ms: int | None = Field(default=None, ge=0)
    expected_headers: dict[str, str] | None = None
    expected_content_type: str | None = None
    auth_profile_id: str | None = None
    auth_profile_name: str | None = Field(default=None, min_length=1, max_length=100)


class PingMonitorConfig(MonitorConfigBase):
    monitor_type: Literal[MonitorType.PING]
    host: str = Field(min_length=1, max_length=255)
    check_interval: int = Field(ge=10, le=86400)
    timeout: int = Field(ge=1, le=300)
    expected_response_time_ms: int | None = Field(default=None, ge=0)


class HeartbeatMonitorConfig(MonitorConfigBase):
    monitor_type: Literal[MonitorType.HEARTBEAT]
    expected_heartbeat_interval: int = Field(gt=0)
    grace_period: int = Field(ge=0)


MonitorConfigDocument = Annotated[HttpMonitorConfig | ApiMonitorConfig | PingMonitorConfig | HeartbeatMonitorConfig, Field(discriminator="monitor_type")]


class MonitorImportResult(BaseModel):
    action: Literal["created", "updated"]
    monitor_id: str
    monitor_type: MonitorType
    name: str
    heartbeat_token: str | None = None
