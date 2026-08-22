from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.service.mongo_db.shared_models.db_monitoring_controller_model import BaseMonitorModel, MonitorStatus, MonitorType


class HTTPMonitorModel(BaseMonitorModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    monitor_type: MonitorType = MonitorType.HTTP
    url: str
    expected_status_code: int
    expected_response_time_ms: int | None = None

class CreateHTTP_monitorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=500)
    expected_response_time_ms: int | None = None
    check_interval: int = Field(ge=10, le=86400)
    timeout: int = Field(gt=0)
    expected_status_code: int = Field(ge=100, le=599)

class UpdateHTTP_monitorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    expected_response_time_ms: int | None = None
    check_interval: int | None = Field(default=None, ge=10, le=86400)
    timeout: int | None = Field(default=None, gt=0)
    expected_status_code: int | None = Field(default=None, ge=100, le=599)
    is_active: bool | None = None

class HTTP_monitorResponse(BaseModel):
    id: str
    name: str
    url: str
    check_interval: int
    expected_status_code: int
    timeout: int
    is_active: bool
    created_by: str |None = None
    created_at: datetime
    updated_at: datetime
    last_checked_at: datetime | None
    last_status_code: int | None
    last_response_time_ms: int | None
    status: MonitorStatus
    expected_response_time_ms: int | None
