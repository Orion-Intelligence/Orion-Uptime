from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.service.mongo_db.shared_models.db_insight_model import (
    MonitorOverviewResponse,
)
from app.service.mongo_db.shared_models.persisted_model import PersistedModel


class StatusPageModel(PersistedModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    name: str
    slug: str
    description: str = ""
    monitor_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CreateStatusPageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    monitor_ids: list[str] = Field(default_factory=list, max_length=1000)


class UpdateStatusPageRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    monitor_ids: list[str] | None = Field(default=None, max_length=1000)


class StatusPageResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    monitor_ids: list[str]
    monitor_count: int
    public_path: str
    created_at: datetime
    updated_at: datetime


class DailyUptimeResponse(BaseModel):
    date: str
    uptime_percentage: float | None


class PublicMonitorStatusResponse(MonitorOverviewResponse):
    uptime_90_days: float | None
    daily_uptime: list[DailyUptimeResponse]


class PublicUptimeStatusResponse(BaseModel):
    last_24_hours: float | None
    last_7_days: float | None
    last_30_days: float | None
    last_90_days: float | None


class PublicStatusPageResponse(BaseModel):
    name: str
    slug: str
    description: str
    overall_status: Literal["operational", "degraded", "outage", "unknown"]
    monitor_count: int
    monitors_up: int
    monitors_down: int
    monitors_unknown: int
    monitors_paused: int
    generated_at: datetime
    refresh_interval_seconds: int = 60
    uptime_status: PublicUptimeStatusResponse
    monitors: list[PublicMonitorStatusResponse]


class PublicResponseTimePoint(BaseModel):
    checked_at: datetime
    response_time_ms: float


class PublicResponseTimeMetrics(BaseModel):
    average_ms: float | None
    maximum_ms: float | None
    minimum_ms: float | None


class PublicMonitorEventResponse(BaseModel):
    event_id: str
    event_type: Literal["created", "down", "up"]
    occurred_at: datetime
    message: str
    status_code: int | None = None
    reason: str | None = None
    duration_seconds: int | None = None
    ongoing: bool = False


class PublicMonitorDetailResponse(BaseModel):
    page_name: str
    page_slug: str
    generated_at: datetime
    refresh_interval_seconds: int = 60
    monitor: PublicMonitorStatusResponse
    uptime_status: PublicUptimeStatusResponse
    response_time_points: list[PublicResponseTimePoint]
    response_time_metrics: PublicResponseTimeMetrics
    recent_events: list[PublicMonitorEventResponse]
