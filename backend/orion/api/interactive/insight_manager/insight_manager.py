import asyncio
from datetime import UTC, datetime, timedelta

from orion.api.interactive.incident_manager.incident_manager import IncidentManager
from orion.constants.constant import Messages
from orion.management.jobs.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from orion.management.jobs.monitoring_controller.monitoring_controller import MonitorManager
from orion.services.mongo_manager.shared_model.db_insight_model import DashboardActivityResponse, DashboardIncidentResponse, DashboardSummaryResponse, MonitorDetailResponse, MonitorIncidentResponse, MonitorOverviewResponse, ResponseHistoryPoint, ResponseHistoryResponse, StatusHistoryPoint, StatusHistoryResponse, UptimeResponse
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.shared_models.exceptions import NotFoundError


class DashboardManager:
    def __init__(self, monitor_service: MonitorManager, monitor_result_service: MonitorResultManager, incident_service: IncidentManager):
        self.monitor_service = monitor_service
        self.monitor_result_service = monitor_result_service
        self.incident_service = incident_service

    async def get_summary(self) -> DashboardSummaryResponse:
        monitors, monitor_map = await self.monitor_service.get_monitors_with_lookup()
        total_monitors = len(monitors)
        active_monitors = sum(1 for monitor in monitors if monitor.is_active)
        inactive_monitors = total_monitors - active_monitors
        monitors_up = sum(1 for monitor in monitors if monitor.status == MonitorStatus.UP)
        monitors_down = sum(1 for monitor in monitors if monitor.status == MonitorStatus.DOWN)
        monitors_unknown = sum(1 for monitor in monitors if monitor.status == MonitorStatus.UNKNOWN)
        latest_results = await self.monitor_result_service.get_latest_per_monitor(limit=max(total_monitors, 1))
        slow_monitors = sum(1 for result in latest_results if result.is_slow and (monitor := monitor_map.get(result.monitor_id)) is not None and monitor.is_active)
        open_incidents = await self.incident_service.count_open()
        average_response_time = await self.monitor_result_service.average_response_time()
        overviews = await self.get_monitor_overviews()
        uptime_values = [overview.uptime_percentage for overview in overviews if overview.is_active and overview.uptime_percentage is not None]
        overall_uptime = round(sum(uptime_values) / len(uptime_values), 2) if uptime_values else 0.0

        return DashboardSummaryResponse(total_monitors=total_monitors, active_monitors=active_monitors, inactive_monitors=inactive_monitors, monitors_up=monitors_up, monitors_down=monitors_down, monitors_unknown=monitors_unknown, open_incidents=open_incidents, average_response_time_ms=average_response_time, overall_uptime_percentage=overall_uptime, slow_monitors=slow_monitors)

    async def get_recent_incidents(self) -> list[DashboardIncidentResponse]:
        incidents = await self.incident_service.get_recent()
        _, monitor_map = await self.monitor_service.get_monitors_with_lookup()
        results = []

        for incident in incidents:
            monitor = monitor_map.get(incident.monitor_id)

            results.append(DashboardIncidentResponse(id=incident.persisted_id, monitor_id=incident.monitor_id, monitor_name=monitor.name if monitor else "Unknown", started_at=incident.started_at, resolved_at=incident.resolved_at, duration_seconds=incident.duration_seconds, reason=incident.reason, status_code=incident.status_code))
        return results

    async def get_monitor_overviews(self) -> list[MonitorOverviewResponse]:
        monitors = await self.monitor_service.list_monitors()
        monitor_ids = [monitor.id for monitor in monitors if monitor.id is not None]
        first_check_times, incidents_by_monitor = await asyncio.gather(self.monitor_result_service.get_first_check_times(monitor_ids), self.incident_service.get_for_monitors(monitor_ids))
        now = datetime.now(UTC)
        overviews = []

        for monitor in monitors:
            if monitor.id is None:
                continue
            uptime_percentage = None
            measured_seconds = 0.0
            downtime_seconds = 0.0
            incidents = incidents_by_monitor.get(monitor.id, [])
            latest_incident = incidents[0] if incidents else None
            first_check_at = first_check_times.get(monitor.id)
            measurement_end = now if monitor.is_active else monitor.updated_at
            if monitor.status != MonitorStatus.UNKNOWN and first_check_at is not None:
                period_start = max(self._as_utc(first_check_at), now - timedelta(days=7))
                period_end = max(period_start, self._as_utc(measurement_end))
                measured_seconds = (period_end - period_start).total_seconds()
                downtime_seconds = sum(self._incident_overlap_seconds(incident.started_at, incident.resolved_at, period_start, period_end) for incident in incidents)
                uptime_percentage = round(max(0.0, 1 - downtime_seconds / measured_seconds) * 100, 2) if measured_seconds > 0 else 100.0

            current_uptime_seconds = 0
            if monitor.status == MonitorStatus.UP:
                uptime_started_at = latest_incident.resolved_at if latest_incident is not None and latest_incident.resolved_at is not None else first_check_at
                if uptime_started_at is not None:
                    current_uptime_seconds = self._duration_seconds(uptime_started_at, measurement_end)

            latest_downtime_seconds = latest_incident.duration_seconds if latest_incident is not None else 0
            overviews.append(
                MonitorOverviewResponse(
                    id=monitor.id,
                    name=monitor.name,
                    monitor_type=monitor.monitor_type.value,
                    status=monitor.status,
                    is_active=monitor.is_active,
                    created_at=monitor.created_at,
                    last_checked_at=monitor.last_checked_at,
                    uptime_percentage=uptime_percentage,
                    current_uptime_seconds=current_uptime_seconds,
                    latest_downtime_seconds=latest_downtime_seconds,
                    measurement_seconds=max(0, int(measured_seconds)),
                    downtime_seconds=max(0, int(downtime_seconds)),
                    snapshot_at=now,
                )
            )
        return overviews

    async def get_monitor_detail(self, monitor_id: str) -> MonitorDetailResponse:
        overview = next((item for item in await self.get_monitor_overviews() if item.id == monitor_id), None)
        if overview is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)

        incidents = (await self.incident_service.get_for_monitors([monitor_id])).get(monitor_id, [])
        return MonitorDetailResponse(**overview.model_dump(), incidents=[MonitorIncidentResponse(id=incident.id, status="resolved" if incident.is_resolved else "open", reason=incident.reason, status_code=incident.status_code, started_at=incident.started_at, resolved_at=incident.resolved_at, duration_seconds=incident.duration_seconds) for incident in incidents if incident.id is not None])

    @staticmethod
    def _duration_seconds(started_at: datetime, ended_at: datetime) -> int:
        return max(0, int((DashboardManager._as_utc(ended_at) - DashboardManager._as_utc(started_at)).total_seconds()))

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @staticmethod
    def _incident_overlap_seconds(started_at: datetime, resolved_at: datetime | None, period_start: datetime, period_end: datetime) -> float:
        overlap_start = max(DashboardManager._as_utc(started_at), period_start)
        overlap_end = min(DashboardManager._as_utc(resolved_at) if resolved_at is not None else period_end, period_end)
        return max(0.0, (overlap_end - overlap_start).total_seconds())

    async def get_recent_activity(self) -> list[DashboardActivityResponse]:
        results = await self.monitor_result_service.get_latest_per_monitor()
        _, monitor_map = await self.monitor_service.get_monitors_with_lookup()
        activities = []

        for result in results:
            monitor = monitor_map.get(result.monitor_id)
            activities.append(DashboardActivityResponse(monitor_id=result.monitor_id, monitor_name=monitor.name if monitor else "Unknown", status=result.status, status_code=result.status_code, response_time_ms=result.response_time_ms, checked_at=result.checked_at, is_slow=result.is_slow))
        return activities

    async def get_response_history(self, monitor_id: str, days: int) -> ResponseHistoryResponse:
        monitor = await self.monitor_service.get_monitor(monitor_id)
        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)

        history = await self.monitor_result_service.get_response_history(monitor_id=monitor_id, days=days)

        return ResponseHistoryResponse(monitor_id=monitor_id, points=[ResponseHistoryPoint(checked_at=result.checked_at, response_time_ms=result.response_time_ms) for result in history])

    async def get_uptime(self, monitor_id: str, days: int) -> UptimeResponse:
        monitor = await self.monitor_service.get_monitor(monitor_id)

        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)

        stats = await self.monitor_result_service.get_statistics(monitor_id=monitor_id, days=days)
        total = stats["total"]
        successful = stats["successful"]
        failed = total - successful
        uptime = round(successful / total * 100, 2) if total > 0 else 0.0
        slow = await self.monitor_result_service.count_slow_checks(monitor_id)

        return UptimeResponse(monitor_id=monitor_id, uptime_percentage=uptime, total_checks=total, successful_checks=successful, failed_checks=failed, slow_checks=slow)

    async def get_status_history(self, monitor_id: str, days: int) -> StatusHistoryResponse:
        monitor = await self.monitor_service.get_monitor(monitor_id)

        if monitor is None:
            raise NotFoundError(Messages.MONITOR_NOT_FOUND)

        history = await self.monitor_result_service.get_status_history(monitor_id=monitor_id, days=days)

        return StatusHistoryResponse(monitor_id=monitor_id, history=[StatusHistoryPoint(checked_at=result.checked_at, status=result.status) for result in history])
