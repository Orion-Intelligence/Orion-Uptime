from __future__ import annotations

from orion.services.realtime_manager.realtime import RealtimeUpdate


class FakeBus:
    def __init__(self, leader: bool = True) -> None:
        self.is_leader = leader
        self.changes: list[tuple[str, str | None, bool]] = []
        self.updates: list[RealtimeUpdate] = []

    async def publish_change(self, kind: str, entity_id: str | None, catalog: bool) -> None:
        self.changes.append((kind, entity_id, catalog))

    async def publish_update(self, update: RealtimeUpdate) -> None:
        self.updates.append(update)
