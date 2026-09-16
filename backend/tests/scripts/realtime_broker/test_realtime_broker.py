from __future__ import annotations

import asyncio

import pytest

from orion.services.realtime_manager.realtime import RealtimeBroker, RealtimeUpdate
from tests.scripts.realtime_broker.helpers import _factory


def test_get_snapshot_builds_common_and_admin_views():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        common = await broker.get_snapshot(is_admin=False)
        admin = await broker.get_snapshot(is_admin=True)
        return common, admin

    common, admin = asyncio.run(run())
    assert common["scope"] == "common"
    assert common["revision"] >= 1
    assert admin["scope"] == "admin"


def test_get_snapshot_without_factory_raises():
    async def run():
        await RealtimeBroker().get_snapshot(is_admin=False)

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
        first = await broker.get_snapshot(is_admin=False)
        broker.notify("monitor", "monitor-1")
        served = await broker.get_snapshot(is_admin=False)
        unchanged = await broker.get_snapshot(is_admin=False)
        return first, served, unchanged

    first, served, unchanged = asyncio.run(run())
    assert served["revision"] > first["revision"]
    assert unchanged["revision"] == served["revision"]


def test_notify_broadcasts_update_to_subscribers():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        queue = broker.subscribe(is_admin=True)
        broker.notify("monitor", "monitor-1")
        update = await asyncio.wait_for(queue.get(), timeout=1)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert isinstance(update, RealtimeUpdate)
    assert ("monitor", "monitor-1") in update.changed
    assert update.admin_snapshot["scope"] == "admin"


def test_notify_replaces_stale_update_when_queue_is_full():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        queue = broker.subscribe(is_admin=False)
        stale = RealtimeUpdate(revision=0, changed=(), common_snapshot={}, admin_snapshot={})
        queue.put_nowait(stale)
        broker.notify("monitor", "monitor-1")
        await asyncio.sleep(0.15)
        update = await asyncio.wait_for(queue.get(), timeout=1)
        broker.unsubscribe(queue)
        return update

    update = asyncio.run(run())
    assert update.revision >= 1
    assert ("monitor", "monitor-1") in update.changed


def test_failed_rebuild_requeues_change_and_recovers():
    async def run():
        broker = RealtimeBroker()
        attempts = {"count": 0}

        async def flaky_factory(changed, include_admin):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("transient rebuild failure")
            return {"scope": "common"}, ({"scope": "admin"} if include_admin else {})

        broker.configure(flaky_factory)
        queue = broker.subscribe(is_admin=False)
        broker.notify("monitor", "monitor-1")
        update = await asyncio.wait_for(queue.get(), timeout=2)
        broker.unsubscribe(queue)
        return update, attempts["count"]

    update, attempts = asyncio.run(run())
    assert attempts >= 2
    assert ("monitor", "monitor-1") in update.changed


def test_shutdown_clears_state():
    async def run():
        broker = RealtimeBroker()
        broker.configure(_factory())
        broker.subscribe(is_admin=False)
        broker.notify("monitor", "monitor-1")
        await broker.shutdown()
        return broker

    broker = asyncio.run(run())
    assert broker._factory is None
    assert broker._subscribers == {}
