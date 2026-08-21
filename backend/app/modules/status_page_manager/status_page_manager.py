from __future__ import annotations

import asyncio
import re
import time
from datetime import UTC, datetime, timedelta

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

from app.modules.insight_manager.insight_manager import DashboardManager
from app.modules.monitoring_controller.monitoring_controller import MonitorManager
from app.service.constants import Collections
from app.service.exceptions import NotFoundError, ValidationError
from app.service.mongo_db.documents import with_string_id
from app.service.mongo_db.shared_models.db_insight_model import MonitorOverviewResponse
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus
from app.service.mongo_db.shared_models.db_status_page_model import (
    CreateStatusPageRequest,
    DailyUptimeResponse,
    PublicMonitorDetailResponse,
    PublicMonitorEventResponse,
    PublicMonitorStatusResponse,
    PublicResponseTimeMetrics,
    PublicResponseTimePoint,
    PublicStatusPageResponse,
    PublicUptimeStatusResponse,
    StatusPageModel,
    StatusPageResponse,
    UpdateStatusPageRequest,
)
from app.service.realtime import realtime_broker


class StatusPageManager:
    _uptime_cache: dict[tuple[str, ...], tuple[float, dict]] = {}
    _detail_history_cache: dict[str, tuple[float, dict, list]] = {}
    _uptime_cache_seconds = 55
    _cache_lock = asyncio.Lock()

    def __init__(self, engine: AIOEngine, monitor_service: MonitorManager, dashboard_service: DashboardManager) -> None:
        self.collection = engine.database[Collections.STATUS_PAGES]
        self.monitor_service = monitor_service
        self.dashboard_service = dashboard_service

    async def create_page(self, request: CreateStatusPageRequest) -> StatusPageResponse:
        name = self._validated_name(request.name)
        monitor_ids = await self._validated_monitor_ids(request.monitor_ids)
        now = datetime.now(UTC)
        page = StatusPageModel(
            name=name,
            slug=await self._unique_slug(name),
            description=request.description.strip(),
            monitor_ids=monitor_ids,
            created_at=now,
            updated_at=now,
        )
        document = page.model_dump(exclude={"id"})
        result = await self.collection.insert_one(document)
        page.id = str(result.inserted_id)
        realtime_broker.notify("status_page", page.id)
        return self._response(page)

    async def list_pages(self) -> list[StatusPageResponse]:
        return [self._response(page) for page in await self.list_page_models()]

    async def list_page_models(self) -> list[StatusPageModel]:
        pages = []
        async for document in self.collection.find().sort("created_at", -1):
            pages.append(StatusPageModel(**with_string_id(document)))
        return pages

    async def get_page(self, page_id: str) -> StatusPageResponse:
        page = await self.get_page_model(page_id)
        if page is None:
            raise NotFoundError("Status page not found.")
        return self._response(page)

    async def get_page_model(self, page_id: str) -> StatusPageModel | None:
        try:
            object_id = ObjectId(page_id)
        except (InvalidId, TypeError):
            return None
        document = await self.collection.find_one({"_id": object_id})
        return self._model(document)

    async def get_page_by_slug(self, slug: str) -> StatusPageModel:
        document = await self.collection.find_one({"slug": slug})
        page = self._model(document)
        if page is None:
            raise NotFoundError("Status page not found.")
        return page

    async def update_page(self, page_id: str, request: UpdateStatusPageRequest) -> StatusPageResponse:
        page = await self.get_page_model(page_id)
        if page is None:
            raise NotFoundError("Status page not found.")

        update_data = request.model_dump(exclude_unset=True)
        if "monitor_ids" in update_data:
            if update_data["monitor_ids"] is None:
                raise ValidationError("Monitor IDs cannot be null.")
            update_data["monitor_ids"] = await self._validated_monitor_ids(
                update_data["monitor_ids"]
            )
        if "name" in update_data:
            update_data["name"] = self._validated_name(update_data["name"])
        if "description" in update_data:
            if update_data["description"] is None:
                raise ValidationError("Description cannot be null.")
            update_data["description"] = update_data["description"].strip()
        if update_data:
            update_data["updated_at"] = datetime.now(UTC)
            await self.collection.update_one(
                {"_id": ObjectId(page_id)},
                {"$set": update_data},
            )

        updated = await self.get_page_model(page_id)
        if updated is None:
            raise NotFoundError("Status page not found.")
        realtime_broker.notify("status_page", updated.id)
        return self._response(updated)

    async def delete_page(self, page_id: str) -> None:
        try:
            object_id = ObjectId(page_id)
        except (InvalidId, TypeError) as exc:
            raise NotFoundError("Status page not found.") from exc
        result = await self.collection.delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise NotFoundError("Status page not found.")
        realtime_broker.notify("status_page", page_id)

    async def get_public_page(self, slug: str) -> PublicStatusPageResponse:
        page = await self.get_page_by_slug(slug)
        overviews = await self.dashboard_service.get_monitor_overviews()
        return await self.build_public_response(page, overviews)

    async def get_public_monitor_detail(self, slug: str, monitor_id: str) -> PublicMonitorDetailResponse:
        page = await self.get_page_by_slug(slug)
        if monitor_id not in page.monitor_ids:
            raise NotFoundError("Monitor not found on this status page.")

        overview = next(
            (
                item
                for item in await self.dashboard_service.get_monitor_overviews()
                if item.id == monitor_id
            ),
            None,
        )
        if overview is None:
            raise NotFoundError("Monitor not found on this status page.")

        now = datetime.now(UTC)
        uptime_data = await self._uptime_data([monitor_id], now)
        public_monitor = self._build_public_monitors(
            [overview],
            uptime_data,
            now,
        )[0]
        response_data, incidents = await self._detail_history(monitor_id, now)
        metric_values = response_data.get("metrics", [])
        metrics = metric_values[0] if metric_values else {}

        return PublicMonitorDetailResponse(
            page_name=page.name,
            page_slug=page.slug,
            generated_at=now,
            monitor=public_monitor,
            uptime_status=self._uptime_status(uptime_data),
            response_time_points=[
                PublicResponseTimePoint(
                    checked_at=point["_id"],
                    response_time_ms=round(point["response_time_ms"], 2),
                )
                for point in response_data.get("points", [])
            ],
            response_time_metrics=PublicResponseTimeMetrics(
                average_ms=self._rounded_metric(metrics.get("average_ms")),
                maximum_ms=self._rounded_metric(metrics.get("maximum_ms")),
                minimum_ms=self._rounded_metric(metrics.get("minimum_ms")),
            ),
            recent_events=self._recent_events(overview, incidents),
        )

    async def build_public_response(self, page: StatusPageModel, overviews: list[MonitorOverviewResponse]) -> PublicStatusPageResponse:
        overview_map = {overview.id: overview for overview in overviews}
        selected = [
            overview_map[monitor_id]
            for monitor_id in page.monitor_ids
            if monitor_id in overview_map
        ]
        active = [overview for overview in selected if overview.is_active]
        monitors_up = sum(1 for overview in active if overview.status == MonitorStatus.UP)
        monitors_down = sum(1 for overview in active if overview.status == MonitorStatus.DOWN)
        monitors_unknown = sum(
            1 for overview in active if overview.status == MonitorStatus.UNKNOWN
        )
        monitors_paused = sum(1 for overview in selected if not overview.is_active)
        if not active:
            overall_status = "unknown"
        elif monitors_down:
            overall_status = "outage"
        elif monitors_unknown:
            overall_status = "degraded"
        else:
            overall_status = "operational"

        now = datetime.now(UTC)
        uptime_data = await self._uptime_data(page.monitor_ids, now)
        public_monitors = self._build_public_monitors(selected, uptime_data, now)

        return PublicStatusPageResponse(
            name=page.name,
            slug=page.slug,
            description=page.description,
            overall_status=overall_status,
            monitor_count=len(selected),
            monitors_up=monitors_up,
            monitors_down=monitors_down,
            monitors_unknown=monitors_unknown,
            monitors_paused=monitors_paused,
            generated_at=now,
            uptime_status=self._uptime_status(uptime_data),
            monitors=public_monitors,
        )

    def _build_public_monitors(self, overviews: list[MonitorOverviewResponse], uptime_data: dict, now: datetime) -> list[PublicMonitorStatusResponse]:
        daily_results = {
            (result["_id"]["monitor_id"], result["_id"]["date"]): result
            for result in uptime_data.get("daily", [])
        }
        monitor_totals = {
            result["_id"]: self._percentage(result)
            for result in uptime_data.get("monitors_90", [])
        }
        dates = [
            (now.date() - timedelta(days=offset)).isoformat()
            for offset in range(89, -1, -1)
        ]
        return [
            PublicMonitorStatusResponse(
                **overview.model_dump(),
                uptime_90_days=monitor_totals.get(overview.id),
                daily_uptime=[
                    DailyUptimeResponse(
                        date=date,
                        uptime_percentage=self._percentage(
                            daily_results.get((overview.id, date))
                        ),
                    )
                    for date in dates
                ],
            )
            for overview in overviews
        ]

    @classmethod
    def _uptime_status(cls, uptime_data: dict) -> PublicUptimeStatusResponse:
        return PublicUptimeStatusResponse(
            last_24_hours=cls._window_percentage(uptime_data, "overall_24"),
            last_7_days=cls._window_percentage(uptime_data, "overall_7"),
            last_30_days=cls._window_percentage(uptime_data, "overall_30"),
            last_90_days=cls._window_percentage(uptime_data, "overall_90"),
        )

    @staticmethod
    def _recent_events(overview, incidents) -> list[PublicMonitorEventResponse]:
        events = []
        for incident in incidents:
            status_code = incident.status_code
            if status_code is None:
                status_code_match = re.search(
                    r"(?:got|received) HTTP (\d+)",
                    incident.reason,
                )
                status_code = (
                    int(status_code_match.group(1))
                    if status_code_match
                    else None
                )
            events.append(
                PublicMonitorEventResponse(
                    event_id=f"{incident.id}:down",
                    event_type="down",
                    occurred_at=incident.started_at,
                    message="Monitor went down.",
                    status_code=status_code,
                    reason=incident.reason,
                    duration_seconds=incident.duration_seconds,
                    ongoing=incident.resolved_at is None,
                )
            )
            if incident.resolved_at is not None:
                events.append(
                    PublicMonitorEventResponse(
                        event_id=f"{incident.id}:up",
                        event_type="up",
                        occurred_at=incident.resolved_at,
                        message="Monitor recovered and became operational.",
                        duration_seconds=incident.duration_seconds,
                    )
                )
        events.sort(key=lambda event: event.occurred_at, reverse=True)
        recent_events = events[:29]
        recent_events.append(
            PublicMonitorEventResponse(
                event_id=f"{overview.id}:created",
                event_type="created",
                occurred_at=overview.created_at,
                message="Monitor was created.",
            )
        )
        return recent_events

    @staticmethod
    def _rounded_metric(value: float | None) -> float | None:
        return round(value, 2) if value is not None else None

    async def _uptime_data(self, monitor_ids: list[str], now: datetime) -> dict:
        cache_key = tuple(sorted(monitor_ids))
        cached = self._uptime_cache.get(cache_key)
        current_time = time.monotonic()
        if cached is not None and current_time - cached[0] < self._uptime_cache_seconds:
            return cached[1]

        async with self._cache_lock:
            cached = self._uptime_cache.get(cache_key)
            current_time = time.monotonic()
            if (
                cached is not None
                and current_time - cached[0] < self._uptime_cache_seconds
            ):
                return cached[1]
            uptime_data = await self.dashboard_service.monitor_result_service.get_public_uptime_breakdown(
                list(cache_key),
                now,
            )
            self._uptime_cache[cache_key] = (current_time, uptime_data)
            self._remove_expired_cache_entries(current_time)
            return uptime_data

    async def _detail_history(self, monitor_id: str, now: datetime) -> tuple[dict, list]:
        current_time = time.monotonic()
        cached = self._detail_history_cache.get(monitor_id)
        if cached is not None and current_time - cached[0] < self._uptime_cache_seconds:
            return cached[1], cached[2]

        async with self._cache_lock:
            cached = self._detail_history_cache.get(monitor_id)
            current_time = time.monotonic()
            if (
                cached is not None
                and current_time - cached[0] < self._uptime_cache_seconds
            ):
                return cached[1], cached[2]
            response_data, incidents_by_monitor = await asyncio.gather(
                self.dashboard_service.monitor_result_service.get_public_response_time(
                    monitor_id,
                    now,
                ),
                self.dashboard_service.incident_service.get_for_monitors([monitor_id]),
            )
            incidents = incidents_by_monitor.get(monitor_id, [])
            self._detail_history_cache[monitor_id] = (
                current_time,
                response_data,
                incidents,
            )
            self._remove_expired_cache_entries(current_time)
            return response_data, incidents

    @classmethod
    def _remove_expired_cache_entries(cls, current_time: float) -> None:
        if len(cls._uptime_cache) > 256:
            expired_uptime = [
                key
                for key, value in cls._uptime_cache.items()
                if current_time - value[0] >= cls._uptime_cache_seconds
            ]
            for key in expired_uptime:
                cls._uptime_cache.pop(key, None)
        if len(cls._detail_history_cache) > 256:
            expired_details = [
                key
                for key, value in cls._detail_history_cache.items()
                if current_time - value[0] >= cls._uptime_cache_seconds
            ]
            for key in expired_details:
                cls._detail_history_cache.pop(key, None)

    @staticmethod
    def _window_percentage(data: dict, key: str) -> float | None:
        values = data.get(key, [])
        if not values:
            return None
        return round(values[0]["uptime_percentage"], 2)

    @staticmethod
    def _percentage(result: dict | None) -> float | None:
        if result is None or result.get("total", 0) <= 0:
            return None
        return round(result["successful"] / result["total"] * 100, 2)

    async def _validated_monitor_ids(self, monitor_ids: list[str]) -> list[str]:
        unique_ids = list(dict.fromkeys(monitor_ids))
        available_ids = {
            monitor.id
            for monitor in await self.monitor_service.list_monitors()
            if monitor.id is not None
        }
        missing = [monitor_id for monitor_id in unique_ids if monitor_id not in available_ids]
        if missing:
            raise ValidationError(f"Unknown monitor IDs: {', '.join(missing)}")
        return unique_ids

    async def _unique_slug(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "status-page"
        slug = base
        suffix = 2
        while await self.collection.find_one({"slug": slug}) is not None:
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    @staticmethod
    def _validated_name(name: str | None) -> str:
        clean_name = name.strip() if name is not None else ""
        if not clean_name:
            raise ValidationError("Status page name is required.")
        return clean_name

    @staticmethod
    def _response(page: StatusPageModel) -> StatusPageResponse:
        if page.id is None:
            raise ValidationError("Status page ID is missing.")
        return StatusPageResponse(
            id=page.id,
            name=page.name,
            slug=page.slug,
            description=page.description,
            monitor_ids=page.monitor_ids,
            monitor_count=len(page.monitor_ids),
            public_path=f"/status/{page.slug}",
            created_at=page.created_at,
            updated_at=page.updated_at,
        )

    @staticmethod
    def _model(document: dict | None) -> StatusPageModel | None:
        if document is None:
            return None
        document = with_string_id(document)
        return StatusPageModel(**document)
