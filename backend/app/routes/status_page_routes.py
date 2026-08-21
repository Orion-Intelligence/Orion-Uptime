from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from odmantic import AIOEngine

from app.modules.insight_manager.insight_manager import DashboardManager
from app.modules.monitoring_controller.monitoring_controller import MonitorManager
from app.modules.status_page_manager.status_page_manager import StatusPageManager
from app.routes.insight_routes import get_dashboard_service, get_monitor_service
from app.service.authorization import require_admin
from app.service.exceptions import NotFoundError
from app.service.mongo_db.mongo_controller import get_engine
from app.service.mongo_db.shared_models.db_status_page_model import (
    CreateStatusPageRequest,
    PublicMonitorDetailResponse,
    PublicStatusPageResponse,
    StatusPageResponse,
    UpdateStatusPageRequest,
)
from app.service.realtime import RealtimeUpdate, realtime_broker
from app.service.responses import SuccessResponse, success_response

KEEP_ALIVE_SECONDS = 15
PUBLIC_REFRESH_SECONDS = 60

router = APIRouter(prefix="/status-pages", tags=["Status Pages"])


def get_status_page_service(engine: AIOEngine = Depends(get_engine), monitor_service: MonitorManager = Depends(get_monitor_service), dashboard_service: DashboardManager = Depends(get_dashboard_service)) -> StatusPageManager:
    return StatusPageManager(engine, monitor_service, dashboard_service)


def _event(name: str, data: Any, revision: int | None = None) -> str:
    payload = json.dumps(jsonable_encoder(data), separators=(",", ":"))
    event_id = f"id: {revision}\n" if revision is not None else ""
    return f"{event_id}event: {name}\ndata: {payload}\n\n"


@router.get("/public/{slug}", response_model=SuccessResponse[PublicStatusPageResponse])
async def get_public_page(slug: str, service: StatusPageManager = Depends(get_status_page_service)):
    return success_response(
        message="Public status page retrieved successfully.",
        data=await service.get_public_page(slug),
    )


@router.get(
    "/public/{slug}/monitors/{monitor_id}",
    response_model=SuccessResponse[PublicMonitorDetailResponse],
)
async def get_public_monitor_detail(slug: str, monitor_id: str, service: StatusPageManager = Depends(get_status_page_service)):
    return success_response(
        message="Public monitor details retrieved successfully.",
        data=await service.get_public_monitor_detail(slug, monitor_id),
    )


@router.get("/public/{slug}/monitors/{monitor_id}/events")
async def stream_public_monitor_detail(slug: str, monitor_id: str, request: Request, service: StatusPageManager = Depends(get_status_page_service)):
    initial = await service.get_public_monitor_detail(slug, monitor_id)
    page = await service.get_page_by_slug(slug)
    queue = realtime_broker.subscribe(is_admin=False)

    async def events():
        last_snapshot_at = asyncio.get_running_loop().time()
        try:
            yield "retry: 1000\n\n"
            yield _event("snapshot", initial)
            while not await request.is_disconnected():
                elapsed = asyncio.get_running_loop().time() - last_snapshot_at
                timeout = min(
                    KEEP_ALIVE_SECONDS,
                    max(0.1, PUBLIC_REFRESH_SECONDS - elapsed),
                )
                try:
                    update: RealtimeUpdate = await asyncio.wait_for(
                        queue.get(),
                        timeout=timeout,
                    )
                except TimeoutError:
                    if (
                        asyncio.get_running_loop().time() - last_snapshot_at
                        >= PUBLIC_REFRESH_SECONDS
                    ):
                        try:
                            detail = await service.get_public_monitor_detail(
                                slug,
                                monitor_id,
                            )
                        except NotFoundError:
                            yield _event(
                                "deleted",
                                {"message": "This public monitor is no longer available."},
                            )
                            return
                        yield _event("snapshot", detail)
                        last_snapshot_at = asyncio.get_running_loop().time()
                        continue
                    yield ": keep-alive\n\n"
                    continue

                page_changed = any(
                    kind == "status_page" and entity_id in {page.id, None}
                    for kind, entity_id in update.changed
                )
                monitor_changed = any(
                    kind == "monitor" and entity_id == monitor_id
                    for kind, entity_id in update.changed
                )
                if not page_changed and not monitor_changed:
                    continue
                try:
                    detail = await service.get_public_monitor_detail(slug, monitor_id)
                except NotFoundError:
                    yield _event(
                        "deleted",
                        {"message": "This public monitor is no longer available."},
                    )
                    return
                yield _event("snapshot", detail, update.revision)
                last_snapshot_at = asyncio.get_running_loop().time()
        finally:
            realtime_broker.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/public/{slug}/events")
async def stream_public_page(slug: str, request: Request, service: StatusPageManager = Depends(get_status_page_service)):
    page = await service.get_page_by_slug(slug)
    queue = realtime_broker.subscribe(is_admin=False)
    try:
        snapshot = await realtime_broker.get_snapshot(is_admin=False)
    except Exception:
        realtime_broker.unsubscribe(queue)
        raise

    async def events():
        nonlocal page
        last_snapshot_at = asyncio.get_running_loop().time()
        try:
            yield "retry: 1000\n\n"
            yield _event(
                "snapshot",
                await service.build_public_response(page, snapshot["overviews"]),
                snapshot["revision"],
            )
            while not await request.is_disconnected():
                elapsed = asyncio.get_running_loop().time() - last_snapshot_at
                timeout = min(
                    KEEP_ALIVE_SECONDS,
                    max(0.1, PUBLIC_REFRESH_SECONDS - elapsed),
                )
                try:
                    update: RealtimeUpdate = await asyncio.wait_for(
                        queue.get(),
                        timeout=timeout,
                    )
                except TimeoutError:
                    if (
                        asyncio.get_running_loop().time() - last_snapshot_at
                        >= PUBLIC_REFRESH_SECONDS
                    ):
                        current_snapshot = await realtime_broker.get_snapshot(
                            is_admin=False
                        )
                        yield _event(
                            "snapshot",
                            await service.build_public_response(
                                page,
                                current_snapshot["overviews"],
                            ),
                            current_snapshot["revision"],
                        )
                        last_snapshot_at = asyncio.get_running_loop().time()
                        continue
                    yield ": keep-alive\n\n"
                    continue

                status_page_changed = any(
                    kind == "status_page" and entity_id in {page.id, None}
                    for kind, entity_id in update.changed
                )
                monitor_changed = any(
                    kind == "monitor" and entity_id in page.monitor_ids
                    for kind, entity_id in update.changed
                )
                if not status_page_changed and not monitor_changed:
                    continue
                if status_page_changed:
                    updated_page = await service.get_page_model(page.persisted_id)
                    if updated_page is None:
                        yield _event("deleted", {"message": "Status page was removed."})
                        return
                    page = updated_page

                yield _event(
                    "snapshot",
                    await service.build_public_response(
                        page,
                        update.common_snapshot["overviews"],
                    ),
                    update.revision,
                )
                last_snapshot_at = asyncio.get_running_loop().time()
        finally:
            realtime_broker.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "",
    response_model=SuccessResponse[StatusPageResponse],
    dependencies=[Depends(require_admin())],
)
async def create_page(request: CreateStatusPageRequest, service: StatusPageManager = Depends(get_status_page_service)):
    return success_response(
        message="Status page created successfully.",
        data=await service.create_page(request),
    )


@router.get(
    "",
    response_model=SuccessResponse[list[StatusPageResponse]],
    dependencies=[Depends(require_admin())],
)
async def list_pages(service: StatusPageManager = Depends(get_status_page_service)):
    return success_response(
        message="Status pages retrieved successfully.",
        data=await service.list_pages(),
    )


@router.get(
    "/{page_id}",
    response_model=SuccessResponse[StatusPageResponse],
    dependencies=[Depends(require_admin())],
)
async def get_page(page_id: str, service: StatusPageManager = Depends(get_status_page_service)):
    return success_response(
        message="Status page retrieved successfully.",
        data=await service.get_page(page_id),
    )


@router.put(
    "/{page_id}",
    response_model=SuccessResponse[StatusPageResponse],
    dependencies=[Depends(require_admin())],
)
async def update_page(page_id: str, request: UpdateStatusPageRequest, service: StatusPageManager = Depends(get_status_page_service)):
    return success_response(
        message="Status page updated successfully.",
        data=await service.update_page(page_id, request),
    )


@router.delete(
    "/{page_id}",
    response_model=SuccessResponse[None],
    dependencies=[Depends(require_admin())],
)
async def delete_page(page_id: str, service: StatusPageManager = Depends(get_status_page_service)):
    await service.delete_page(page_id)
    return success_response(
        message="Status page deleted successfully.",
        data=None,
    )
