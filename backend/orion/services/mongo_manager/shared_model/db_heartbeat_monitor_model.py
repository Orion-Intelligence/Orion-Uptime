from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from orion.services.mongo_manager.shared_model.persisted_model import PersistedModel


class HeartbeatMonitorModel(PersistedModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    monitor_type: Literal[MonitorType.HEARTBEAT] = MonitorType.HEARTBEAT
    expected_heartbeat_interval: int = Field(gt=0, validation_alias=AliasChoices("expected_heartbeat_interval", "check_interval"))
    grace_period: int = Field(default=60, ge=0)
    heartbeat_token_hash: str
    is_active: bool = True
    status: MonitorStatus = MonitorStatus.UNKNOWN
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    heartbeat_count: int = Field(default=0, ge=0)
    last_token_rotated_at: datetime | None = None
    token_expires_at: datetime | None = None
    heartbeat_token: str | None = Field(default=None, exclude=True)


class CreateHeartbeatMonitorRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expected_heartbeat_interval: int = Field(..., gt=0)
    grace_period: int = Field(..., ge=0)


class UpdateHeartbeatMonitorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    expected_heartbeat_interval: int | None = Field(default=None, gt=0)
    grace_period: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class HeartbeatMonitorResponse(BaseModel):
    id: str
    name: str
    expected_heartbeat_interval: int
    grace_period: int
    status: str
    is_active: bool
    last_heartbeat_at: str | None
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class HeartbeatTokenResponse(BaseModel):
    heartbeat_token: str
    model_config = ConfigDict(from_attributes=True)


class RegenerateHeartbeatTokenResponse(BaseModel):
    heartbeat_token: str


class HeartbeatResponse(BaseModel):
    message: str
    expected_next_heartbeat_in: int
    server_time: datetime
    token_rotation_required: bool
