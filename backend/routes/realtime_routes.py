from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from jwt import PyJWTError

from configs.app_dependency import app_dependency
from orion.constants.constant import Intervals
from orion.services.auth.authorization import require_viewer
from orion.services.mongo_manager.shared_model.db_user_account_model import CurrentUserResponse, UserRole
from orion.services.realtime_manager.realtime import RealtimeUpdate, realtime_broker

router = APIRouter(prefix="/events", tags=["Real-time Updates"])


def _snapshot_event(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(jsonable_encoder(snapshot), separators=(",", ":"))
    return f"id: {snapshot['revision']}\nevent: snapshot\ndata: {payload}\n\n"


def _connection_lifetime(request: Request, response: Response) -> float:
    load_dotenv()
    configured_seconds = int(os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"]) * 60
    if response.headers.get("X-Access-Token-Refreshed") == "true":
        return float(configured_seconds)

    token = request.cookies.get("access_token")
    if token is None:
        return float(configured_seconds)
    try:
        expires_at = float(app_dependency.decode_token(token)["exp"])
    except (PyJWTError, KeyError, TypeError, ValueError):
        return float(configured_seconds)
    return max(1.0, min(float(configured_seconds), expires_at - time.time()))


@router.get("")
async def stream_events(request: Request, response: Response, current_user: CurrentUserResponse = Depends(require_viewer())):
    is_admin = current_user.role == UserRole.ADMIN
    connection_lifetime = _connection_lifetime(request, response)
    queue = realtime_broker.subscribe(is_admin)
    try:
        initial = await realtime_broker.get_snapshot(is_admin)
    except Exception:
        realtime_broker.unsubscribe(queue)
        raise

    async def events():
        reauthenticate_at = time.monotonic() + connection_lifetime
        try:
            yield "retry: 1000\n\n"
            yield _snapshot_event(initial)
            while not await request.is_disconnected():
                remaining = reauthenticate_at - time.monotonic()
                if remaining <= 0:
                    yield "event: reauthenticate\ndata: {}\n\n"
                    return
                try:
                    update: RealtimeUpdate = await asyncio.wait_for(queue.get(), timeout=min(Intervals.KEEP_ALIVE_SECONDS, remaining))
                except TimeoutError:
                    if time.monotonic() >= reauthenticate_at:
                        yield "event: reauthenticate\ndata: {}\n\n"
                        return
                    yield ": keep-alive\n\n"
                    continue

                if any(kind == "user" and entity_id == current_user.id for kind, entity_id in update.changed):
                    return
                snapshot = update.admin_snapshot if is_admin else update.common_snapshot
                yield _snapshot_event(snapshot)
        finally:
            realtime_broker.unsubscribe(queue)

    stream_response = StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
    for key, value in response.raw_headers:
        if key.lower() in {b"set-cookie", b"x-access-token-refreshed"}:
            stream_response.raw_headers.append((key, value))
    return stream_response
