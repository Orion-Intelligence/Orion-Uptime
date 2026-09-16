from __future__ import annotations

import asyncio

import pytest

from orion.services.realtime_manager.realtime import RealtimeBroker, RealtimeUpdate
from tests.scripts.realtime_broker.helpers import _changing_factory, _factory


def test_get_snapshot_builds_sections_and_metadata():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        return await broker.get_snapshot()

    snapshot = asyncio.run(run())
    assert snapshot["scope"] == "common"
    assert snapshot["revision"] >= 1
    assert snapshot["changed"] == []


def test_get_snapshot_without_factory_raises():
    async def run():
        await RealtimeBroker().get_snapshot()

    with pytest.raises(RuntimeError):
        asyncio.run(run())


def test_notify_without_factory_is_a_noop():
    broker = RealtimeBroker()
    broker.notify("monitor", "monitor-1")
    assert broker._pending_changes == set()


def test_notify_without_subscribers_serves_fresh_snapshot_on_next_read():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        first = await broker.get_snapshot()
        broker.notify("monitor", "monitor-1", catalog=False)
        served = await broker.get_snapshot()
        unchanged = await broker.get_snapshot()
        return first, served, unchanged

    first, served, unchanged = asyncio.run(run())
    assert served["revision"] > first["revision"]
    assert unchanged["revision"] == served["revision"]


def test_notify_broadcasts_update_to_subscribers():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        queue = broker.subscribe()
        broker.notify("monitor", "monitor-1")
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert isinstance(update, RealtimeUpdate)
    assert ("monitor", "monitor-1") in update.changed
    assert update.snapshot["scope"] == "common"
    assert update.resource_types == ("API", "HTTP", "heartbeat", "orion_script", "ping")


def test_notify_without_catalog_changes_reports_no_resource_types():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        queue = broker.subscribe()
        broker.notify("monitor", "monitor-1", catalog=False)
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert update.resource_types == ()


def test_broadcast_omits_sections_that_did_not_change():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_changing_factory([
            {"summary": {"total": 1}, "activity": ["a"]},
            {"summary": {"total": 1}, "activity": ["b"]},
        ]))
        await broker.get_snapshot()
        queue = broker.subscribe()
        broker.notify("monitor", "monitor-1", catalog=False)
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert "summary" not in update.snapshot
    assert update.snapshot["activity"] == ["b"]
    assert update.snapshot["revision"] >= 2


def test_broadcast_ignores_volatile_overview_timestamps():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_changing_factory([
            {"overviews": [{"id": "m1", "status": "up", "snapshot_at": "t1"}]},
            {"overviews": [{"id": "m1", "status": "up", "snapshot_at": "t2"}]},
        ]))
        await broker.get_snapshot()
        queue = broker.subscribe()
        broker.notify("monitor", "monitor-1", catalog=False)
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert "overviews" not in update.snapshot


def test_notify_replaces_stale_update_when_queue_is_full():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        queue = broker.subscribe()
        queue.put_nowait(RealtimeUpdate(revision=0, changed=(), snapshot={}, resource_types=()))
        broker.notify("monitor", "monitor-1")
        await asyncio.sleep(2.15)
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert update.revision >= 1
    assert ("monitor", "monitor-1") in update.changed


def test_deliver_merges_partial_snapshot_for_followers():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory(sections={"summary": {"total": 1}, "activity": []}))
        await broker.get_snapshot()
        queue = broker.subscribe()
        broker.deliver(RealtimeUpdate(revision=9, changed=(("monitor", "m1"),), snapshot={"activity": ["fresh"]}, resource_types=("HTTP",)))
        update = await asyncio.wait_for(queue.get(), timeout=3)
        broker.unsubscribe(queue)
        return update, await broker.get_snapshot()

    update, snapshot = asyncio.run(run())
    assert update.resource_types == ("HTTP",)
    assert snapshot["activity"] == ["fresh"]
    assert snapshot["summary"] == {"total": 1}


def test_shutdown_clears_state():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        broker.subscribe()
        broker.notify("monitor", "monitor-1")
        await broker.shutdown()
        return broker

    broker = asyncio.run(run())
    assert broker._factory is None
    assert broker._subscribers == set()
