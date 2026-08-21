from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.service.mongo_db.shared_models.db_monitoring_controller_model import BaseMonitorModel, MonitorStatus, MonitorType


class APIMonitorModel(BaseMonitorModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    monitor_type: MonitorType = MonitorType.API
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    request_body: dict | None = None
    expected_status_code: int
    expected_json: dict | None = None
    expected_response_time_ms: int | None = None
    expected_headers: dict[str, str] | None = None
    expected_content_type: str | None = None
    auth_profile_id: str | None = None

class CreateApiMonitorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=500)
    expected_response_time_ms: int | None = None
    method: str = Field(default="GET", max_length=10)
    headers: dict[str, str] = Field(default_factory=dict)
    request_body: dict | None = None
    expected_status_code: int = Field(ge=100, le=599)
    expected_json: dict | None = None
    check_interval: int = Field(ge=10, le=86400)
    timeout: int = Field(default=10, gt=0)
    expected_headers: dict[str, str] | None = None
    expected_content_type: str | None = None
    auth_profile_id: str | None = None

class UpdateApiMonitorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    expected_response_time_ms: int | None = None
    method: str | None = Field(default=None, max_length=10)
    headers: dict[str, str] | None = None
    request_body: dict | None = None
    expected_status_code: int | None = Field(default=None, ge=100, le=599)
    expected_json: dict | None = None
    check_interval: int | None = Field(default=None, ge=10, le=86400)
    timeout: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    expected_headers: dict[str, str] | None = None
    expected_content_type: str | None = None
    auth_profile_id: str | None = None

class ApiMonitorResponse(BaseModel):
    id: str
    name: str
    url: str
    method: str
    headers: dict[str, str]
    request_body: dict | None
    expected_status_code: int
    expected_json: dict | None
    check_interval: int
    timeout: int
    is_active: bool
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
    last_status_code: int | None
    last_response_time_ms: int | None
    status: MonitorStatus
    expected_response_time_ms: int | None
    expected_headers: dict[str, str] | None
    expected_content_type: str | None
    auth_profile_id: str | None = None
