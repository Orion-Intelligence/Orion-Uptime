from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

SnapshotFactory = Callable[
    [tuple[tuple[str, str | None], ...], bool],
    Awaitable[tuple[dict[str, Any], dict[str, Any]]],
]


@dataclass(frozen=True, slots=True)
class RealtimeUpdate:
    revision: int
    changed: tuple[tuple[str, str | None], ...]
    common_snapshot: dict[str, Any]
    admin_snapshot: dict[str, Any]


class RealtimeBroker:
    def __init__(self) -> None:
        self._factory: SnapshotFactory | None = None
        self._revision = 0
        self._common_snapshot: dict[str, Any] | None = None
        self._admin_snapshot: dict[str, Any] | None = None
        self._pending_changes: set[tuple[str, str | None]] = set()
        self._subscribers: dict[asyncio.Queue[RealtimeUpdate], bool] = {}
        self._refresh_task: asyncio.Task[None] | None = None
        self._build_lock = asyncio.Lock()

    def configure(self, factory: SnapshotFactory) -> None:
        self._factory = factory
        self._common_snapshot = None
        self._admin_snapshot = None

    def notify(self, kind: str, entity_id: str | None = None) -> None:
        if self._factory is None:
            return
        self._pending_changes.add((kind, entity_id))
        if not self._subscribers:
            self._common_snapshot = None
            self._admin_snapshot = None
            self._pending_changes.clear()
            return
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_pending())

    def subscribe(self, is_admin: bool) -> asyncio.Queue[RealtimeUpdate]:
        queue: asyncio.Queue[RealtimeUpdate] = asyncio.Queue(maxsize=1)
        self._subscribers[queue] = is_admin
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RealtimeUpdate]) -> None:
        self._subscribers.pop(queue, None)

    async def get_snapshot(self, is_admin: bool) -> dict[str, Any]:
        if self._common_snapshot is None or (is_admin and self._admin_snapshot is None):
            await self._rebuild((), broadcast=False, include_admin=is_admin)
        snapshot = self._admin_snapshot if is_admin else self._common_snapshot
        if snapshot is None:
            raise RuntimeError("Real-time snapshot is unavailable.")
        return snapshot

    async def shutdown(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
        self._factory = None
        self._pending_changes.clear()
        self._subscribers.clear()

    async def _refresh_pending(self) -> None:
        await asyncio.sleep(0.05)
        while self._pending_changes:
            changed = tuple(sorted(self._pending_changes, key=lambda item: (item[0], item[1] or "")))
            self._pending_changes.clear()
            with contextlib.suppress(Exception):
                await self._rebuild(
                    changed,
                    broadcast=True,
                    include_admin=any(self._subscribers.values()),
                )

    async def _rebuild(self, changed: tuple[tuple[str, str | None], ...], *, broadcast: bool, include_admin: bool) -> None:
        async with self._build_lock:
            if (
                not broadcast
                and self._common_snapshot is not None
                and (not include_admin or self._admin_snapshot is not None)
            ):
                return
            if self._factory is None:
                raise RuntimeError("Real-time snapshot factory has not been configured.")

            common, admin = await self._factory(changed, include_admin)
            self._revision += 1
            metadata = {
                "revision": self._revision,
                "changed": [
                    {"kind": kind, "entity_id": entity_id}
                    for kind, entity_id in changed
                ],
            }
            self._common_snapshot = {**common, **metadata}
            self._admin_snapshot = {**admin, **metadata} if include_admin else None

            if not broadcast:
                return

            update = RealtimeUpdate(
                revision=self._revision,
                changed=changed,
                common_snapshot=self._common_snapshot,
                admin_snapshot=self._admin_snapshot or self._common_snapshot,
            )
            for queue in tuple(self._subscribers):
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(update)


realtime_broker = RealtimeBroker()
