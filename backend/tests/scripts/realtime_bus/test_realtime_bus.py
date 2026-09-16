from __future__ import annotations

import asyncio

from orion.services.realtime_manager.realtime import RealtimeBroker, RealtimeUpdate
from orion.services.realtime_manager.realtime_bus import BUS_MEMORY, BUS_MONGO, bus_mode, node_id
from tests.scripts.realtime_broker.helpers import _factory
from tests.scripts.realtime_bus.helpers import FakeBus


def test_bus_mode_defaults_to_memory(monkeypatch):
    monkeypatch.delenv("REALTIME_BUS", raising=False)
    assert bus_mode() == BUS_MEMORY


def test_bus_mode_reads_environment(monkeypatch):
    monkeypatch.setenv("REALTIME_BUS", " Mongo ")
    assert bus_mode() == BUS_MONGO


def test_node_id_is_unique():
    assert node_id() != node_id()


def test_leader_publishes_updates_to_the_bus():
    async def run():
        bus = FakeBus(leader=True)
        broker = RealtimeBroker()
        broker.configure(_factory(), bus=bus)
        queue = broker.subscribe()
        broker.notify("monitor", "m1", catalog=False)
        await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return bus

    bus = asyncio.run(run())
    assert bus.changes == []
    assert len(bus.updates) == 1
    assert bus.updates[0].changed == (("monitor", "m1"),)


def test_follower_forwards_changes_instead_of_rebuilding():
    async def run():
        bus = FakeBus(leader=False)
        broker = RealtimeBroker()
        broker.configure(_factory(), bus=bus)
        broker.notify("user", "u1")
        await asyncio.sleep(0)
        return broker, bus

    broker, bus = asyncio.run(run())
    assert bus.changes == [("user", "u1", True)]
    assert bus.updates == []
    assert broker._pending_changes == set()


def test_follower_applies_leader_updates_locally():
    async def run():
        bus = FakeBus(leader=False)
        broker = RealtimeBroker()
        broker.configure(_factory(sections={"summary": {"total": 1}, "activity": []}), bus=bus)
        await broker.get_snapshot()
        queue = broker.subscribe()
        broker.deliver(RealtimeUpdate(revision=7, changed=(), snapshot={"activity": ["from-leader"]}, resource_types=("users",)))
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update, await broker.get_snapshot()

    update, snapshot = asyncio.run(run())
    assert update.resource_types == ("users",)
    assert snapshot["activity"] == ["from-leader"]
    assert snapshot["summary"] == {"total": 1}


def test_local_only_notify_is_handled_by_the_leader_node():
    async def run():
        bus = FakeBus(leader=True)
        broker = RealtimeBroker()
        broker.configure(_factory(), bus=bus)
        queue = broker.subscribe()
        broker.notify("status_page", "s1", local_only=True)
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update, bus

    update, bus = asyncio.run(run())
    assert bus.changes == []
    assert update.resource_types == ("status_pages",)


def test_is_leader_defaults_to_true_without_a_bus():
    broker = RealtimeBroker()
    broker.configure(_factory())
    assert broker.is_leader is True
