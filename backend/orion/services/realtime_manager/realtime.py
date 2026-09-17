from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from orion.constants.constant import Intervals
from orion.management.managers.resource_catalog import resource_types_for

logger = logging.getLogger("orion.uptime.realtime")

SnapshotFactory = Callable[[tuple[tuple[str, str | None], ...]], Awaitable[dict[str, Any]]]

METADATA_KEYS = ("generated_at", "revision", "changed")
VOLATILE_SECTION_KEYS: dict[str, frozenset[str]] = {"overviews": frozenset({"snapshot_at"})}


@dataclass(frozen=True, slots=True)
class RealtimeUpdate:
    revision: int
    changed: tuple[tuple[str, str | None], ...]
    snapshot: dict[str, Any]
    resource_types: tuple[str, ...]


def _comparable(section: str, value: Any) -> Any:
    volatile = VOLATILE_SECTION_KEYS.get(section)
    if not volatile or not isinstance(value, list):
        return value
    return [{key: item[key] for key in item if key not in volatile} if isinstance(item, dict) else item for item in value]


class RealtimeBroker:
    def __init__(self) -> None:
        self._factory: SnapshotFactory | None = None
        self._revision = 0
        self._snapshot: dict[str, Any] | None = None
        self._pending_changes: set[tuple[str, str | None]] = set()
        self._pending_resources: set[str] = set()
        self._subscribers: set[asyncio.Queue[RealtimeUpdate]] = set()
        self._refresh_task: asyncio.Task[None] | None = None
        self._build_lock = asyncio.Lock()
        self._bus: Any | None = None

    def configure(self, factory: SnapshotFactory, *, bus: Any | None = None) -> None:
        self._factory = factory
        self._snapshot = None
        self._bus = bus

    @property
    def is_leader(self) -> bool:
        return self._bus is None or bool(self._bus.is_leader)

    def notify(self, kind: str, entity_id: str | None = None, *, catalog: bool = True, local_only: bool = False) -> None:
        if self._factory is None:
            return
        if not local_only and not self.is_leader:
            self._spawn(self._bus.publish_change(kind, entity_id, catalog))
            return
        self._pending_changes.add((kind, entity_id))
        if catalog:
            self._pending_resources.update(resource_types_for(kind))
        if not self._subscribers:
            self._snapshot = None
            self._pending_changes.clear()
            if self._pending_resources:
                self._schedule_refresh()
            return
        self._schedule_refresh()

    @staticmethod
    def _spawn(coroutine: Awaitable[None]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            close = getattr(coroutine, "close", None)
            if close is not None:
                close()
            return
        loop.create_task(coroutine)

    def _schedule_refresh(self) -> None:
        if not self.is_leader:
            return
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_pending())

    def subscribe(self) -> asyncio.Queue[RealtimeUpdate]:
        queue: asyncio.Queue[RealtimeUpdate] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[RealtimeUpdate]) -> None:
        self._subscribers.discard(queue)

    async def get_snapshot(self) -> dict[str, Any]:
        if self._snapshot is None:
            await self._rebuild((), broadcast=False)
        if self._snapshot is None:
            raise RuntimeError("Real-time snapshot is unavailable.")
        return self._snapshot

    def deliver(self, update: RealtimeUpdate) -> None:
        if update.snapshot:
            merged = dict(self._snapshot or {})
            merged.update(update.snapshot)
            self._snapshot = merged
            self._revision = max(self._revision, update.revision)
        self._publish(update)

    async def shutdown(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._refresh_task
        self._factory = None
        self._bus = None
        self._pending_changes.clear()
        self._pending_resources.clear()
        self._subscribers.clear()

    async def _refresh_pending(self) -> None:
        await asyncio.sleep(Intervals.REALTIME_DEBOUNCE_SECONDS)
        while self._pending_changes or self._pending_resources:
            changed = tuple(sorted(self._pending_changes, key=lambda item: (item[0], item[1] or "")))
            resources = tuple(sorted(self._pending_resources))
            self._pending_changes.clear()
            self._pending_resources.clear()
            try:
                await self._rebuild(changed, broadcast=True, resource_types=resources)
            except Exception:
                self._pending_changes.update(changed)
                self._pending_resources.update(resources)
                logger.warning("Real-time snapshot rebuild failed; changes re-queued for retry.", exc_info=True)
            if self._pending_changes or self._pending_resources:
                await asyncio.sleep(Intervals.REALTIME_COALESCE_SECONDS)

    async def _rebuild(self, changed: tuple[tuple[str, str | None], ...], *, broadcast: bool, resource_types: tuple[str, ...] = ()) -> None:
        async with self._build_lock:
            if not broadcast and self._snapshot is not None:
                return
            if self._factory is None:
                raise RuntimeError("Real-time snapshot factory has not been configured.")

            sections = await self._factory(changed)
            previous = self._snapshot
            self._revision += 1
            metadata = {"revision": self._revision, "changed": [{"kind": kind, "entity_id": entity_id} for kind, entity_id in changed]}
            full = {**sections, **metadata}
            self._snapshot = full

            if not broadcast:
                return

            payload = {key: value for key, value in full.items() if key in METADATA_KEYS or previous is None or _comparable(key, previous.get(key)) != _comparable(key, value)}
            update = RealtimeUpdate(revision=self._revision, changed=changed, snapshot=payload, resource_types=resource_types)
            self._publish(update)
            if self._bus is not None:
                with contextlib.suppress(Exception):
                    await self._bus.publish_update(update)

    def _publish(self, update: RealtimeUpdate) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(update)


realtime_broker = RealtimeBroker()
