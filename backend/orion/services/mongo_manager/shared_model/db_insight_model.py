from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus


class DashboardSummaryResponse(BaseModel):
    total_monitors: int
    active_monitors: int
    inactive_monitors: int
    monitors_up: int
    monitors_down: int
    monitors_unknown: int
    slow_monitors: int
    open_incidents: int
    average_response_time_ms: float
    overall_uptime_percentage: float


class DashboardIncidentResponse(BaseModel):
    id: str
    monitor_id: str
    monitor_name: str
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None
    reason: str
    status_code: int | None = None


class MonitorIncidentResponse(BaseModel):
    id: str
    status: Literal["open", "resolved"]
    reason: str
    status_code: int | None = None
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int


class MonitorOverviewResponse(BaseModel):
    id: str
    name: str
    monitor_type: str
    status: MonitorStatus
    is_active: bool
    created_at: datetime
    last_checked_at: datetime | None
    uptime_percentage: float | None
    current_uptime_seconds: int
    latest_downtime_seconds: int
    measurement_seconds: int
    downtime_seconds: int
    snapshot_at: datetime


class MonitorDetailResponse(MonitorOverviewResponse):
    incidents: list[MonitorIncidentResponse]


class DashboardActivityResponse(BaseModel):
    monitor_id: str
    monitor_name: str
    status: MonitorStatus
    status_code: int | None
    response_time_ms: int | None
    is_slow: bool
    checked_at: datetime


class ResponseHistoryPoint(BaseModel):
    checked_at: datetime
    response_time_ms: int | None


class ResponseHistoryResponse(BaseModel):
    monitor_id: str
    points: list[ResponseHistoryPoint]


class UptimeResponse(BaseModel):
    monitor_id: str
    uptime_percentage: float
    total_checks: int
    successful_checks: int
    failed_checks: int
    slow_checks: int


class StatusHistoryPoint(BaseModel):
    checked_at: datetime
    status: MonitorStatus


class StatusHistoryResponse(BaseModel):
    monitor_id: str
    history: list[StatusHistoryPoint]
