from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.errors import PyMongoError

from orion.constants.constant import Collections
from orion.services.realtime_manager.realtime import RealtimeUpdate, realtime_broker

logger = logging.getLogger(__name__)

BUS_MEMORY = "memory"
BUS_MONGO = "mongo"
CHANNEL_SIZE_BYTES = 8 * 1024 * 1024
LEASE_SECONDS = 15.0
HEARTBEAT_SECONDS = 5.0
IDLE_POLL_SECONDS = 0.5

MESSAGE_CHANGE = "change"
MESSAGE_UPDATE = "update"


def bus_mode() -> str:
    return os.environ.get("REALTIME_BUS", BUS_MEMORY).strip().lower() or BUS_MEMORY


def node_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class MongoRealtimeBus:
    def __init__(self, database: Any, identity: str | None = None) -> None:
        self.database = database
        self.identity = identity or node_id()
        self._channel = database[Collections.REALTIME_CHANNEL]
        self._leases = database[Collections.REALTIME_LEASES]
        self._listener: asyncio.Task[None] | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._is_leader = False
        self._stopped = False

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    async def start(self) -> None:
        await self._ensure_channel()
        self._is_leader = await self._acquire_lease()
        self._listener = asyncio.create_task(self._listen())
        self._heartbeat = asyncio.create_task(self._keep_lease())

    async def stop(self) -> None:
        self._stopped = True
        for task in (self._listener, self._heartbeat):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._listener = None
        self._heartbeat = None
        if self._is_leader:
            with contextlib.suppress(PyMongoError):
                await self._leases.delete_one({"_id": Collections.REALTIME_LEADER_KEY, "holder": self.identity})
        self._is_leader = False

    async def publish_change(self, kind: str, entity_id: str | None, catalog: bool) -> None:
        await self._publish({"type": MESSAGE_CHANGE, "kind": kind, "entity_id": entity_id, "catalog": catalog})

    async def publish_update(self, update: RealtimeUpdate) -> None:
        await self._publish({
            "type": MESSAGE_UPDATE,
            "revision": update.revision,
            "changed": [[kind, entity_id] for kind, entity_id in update.changed],
            "snapshot": update.snapshot,
            "resource_types": list(update.resource_types),
        })

    async def _publish(self, message: dict[str, Any]) -> None:
        document = {**message, "sender": self.identity, "created_at": datetime.now(UTC)}
        with contextlib.suppress(PyMongoError):
            await self._channel.insert_one(document)

    async def _ensure_channel(self) -> None:
        names = await self.database.list_collection_names()
        if Collections.REALTIME_CHANNEL not in names:
            with contextlib.suppress(PyMongoError):
                await self.database.create_collection(Collections.REALTIME_CHANNEL, capped=True, size=CHANNEL_SIZE_BYTES)
        with contextlib.suppress(PyMongoError):
            await self._channel.insert_one({"type": "bootstrap", "sender": self.identity, "created_at": datetime.now(UTC)})

    async def _acquire_lease(self) -> bool:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=LEASE_SECONDS)
        try:
            await self._leases.update_one(
                {"_id": Collections.REALTIME_LEADER_KEY, "$or": [{"holder": self.identity}, {"expires_at": {"$lte": now}}]},
                {"$set": {"holder": self.identity, "expires_at": expires_at}},
                upsert=True,
            )
        except PyMongoError:
            return False
        document = await self._leases.find_one({"_id": Collections.REALTIME_LEADER_KEY})
        return bool(document) and document.get("holder") == self.identity

    async def _keep_lease(self) -> None:
        while not self._stopped:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            leader = await self._acquire_lease()
            if leader != self._is_leader:
                self._is_leader = leader
                logger.info("Real-time leadership changed for %s: leader=%s", self.identity, leader)

    async def _listen(self) -> None:
        while not self._stopped:
            try:
                await self._tail()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("The real-time channel listener stopped unexpectedly; retrying.")
                await asyncio.sleep(IDLE_POLL_SECONDS)

    async def _tail(self) -> None:
        latest = await self._channel.find_one(sort=[("$natural", -1)])
        query: dict[str, Any] = {"_id": {"$gt": latest["_id"]}} if latest else {}
        cursor = self._channel.find(query, cursor_type=self._tailable_type(), no_cursor_timeout=False)
        cursor.max_await_time_ms(1000)
        async for message in cursor:
            if self._stopped:
                return
            if message.get("sender") == self.identity:
                continue
            await self._handle(message)

    @staticmethod
    def _tailable_type():
        from pymongo import CursorType

        return CursorType.TAILABLE_AWAIT

    async def _handle(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == MESSAGE_CHANGE and self._is_leader:
            realtime_broker.notify(str(message.get("kind")), message.get("entity_id"), catalog=bool(message.get("catalog", True)), local_only=True)
            return
        if kind == MESSAGE_UPDATE and not self._is_leader:
            changed = tuple((str(item[0]), item[1]) for item in message.get("changed", []) if isinstance(item, list) and len(item) == 2)
            realtime_broker.deliver(RealtimeUpdate(revision=int(message.get("revision", 0)), changed=changed, snapshot=dict(message.get("snapshot") or {}), resource_types=tuple(message.get("resource_types") or ())))
