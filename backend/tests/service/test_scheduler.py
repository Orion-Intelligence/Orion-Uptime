from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from orion.management.jobs.monitoring_controller.scheduler import MonitorScheduler
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType

NOW = datetime.now(UTC)


def _returns(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


async def _noop(*_args, **_kwargs):
    return None


def _monitor_service(active):
    holder = {"active": active}

    async def list_active_monitors():
        value = holder["active"]
        if isinstance(value, Exception):
            raise value
        return value

    service = SimpleNamespace(
        list_active_monitors=list_active_monitors,
        monitor_result_service=SimpleNamespace(seed_history=_noop),
        get_monitor=_returns(None),
        check_and_update=_noop,
    )
    return service, holder


def _monitor(monitor_id):
    return SimpleNamespace(persisted_id=monitor_id, monitor_type=MonitorType.HTTP)


def _scheduler(active=None, clock=None):
    service, holder = _monitor_service(active if active is not None else [])
    scheduler = MonitorScheduler(service, reconcile_interval=3600, clock=clock or (lambda: 0.0))
    return scheduler, holder


def test_status_and_health_before_start():
    scheduler, _ = _scheduler()
    assert scheduler.running is False
    assert scheduler.is_healthy() is False
    status = scheduler.status()
    assert status["running"] is False
    assert status["workers"] == 0
    assert status["seconds_since_reconcile"] is None


def test_start_reconciles_and_stop_clears_running():
    async def run():
        scheduler, _ = _scheduler(active=[])
        await scheduler.start()
        running = scheduler.running
        healthy = scheduler.is_healthy()
        await scheduler.stop()
        return running, healthy, scheduler.running

    running, healthy, after = asyncio.run(run())
    assert running is True
    assert healthy is True
    assert after is False


def test_reconcile_starts_and_stops_workers():
    async def run():
        scheduler, holder = _scheduler(active=[_monitor("a")])
        await scheduler.start()
        started = set(scheduler._workers)
        holder["active"] = []
        await scheduler.reconcile()
        remaining = set(scheduler._workers)
        await scheduler.stop()
        return started, remaining

    started, remaining = asyncio.run(run())
    assert started == {"a"}
    assert remaining == set()


def test_reconcile_skips_heartbeat_without_first_beat():
    async def run():
        heartbeat = HeartbeatMonitorModel(id="h1", name="hb", expected_heartbeat_interval=300, grace_period=60, heartbeat_token_hash="hash", created_at=NOW, updated_at=NOW, last_heartbeat_at=None)
        scheduler, _ = _scheduler(active=[heartbeat])
        await scheduler.start()
        workers = set(scheduler._workers)
        await scheduler.stop()
        return workers

    assert asyncio.run(run()) == set()


def test_stop_worker_missing_is_noop():
    asyncio.run(_scheduler()[0].stop_worker("ghost"))


def test_is_healthy_false_when_stalled():
    clock = {"t": 100.0}

    async def run():
        scheduler, _ = _scheduler(active=[], clock=lambda: clock["t"])
        await scheduler.start()
        healthy_now = scheduler.is_healthy(stall_seconds=30)
        clock["t"] += 1000
        stalled = scheduler.is_healthy(stall_seconds=30)
        await scheduler.stop()
        return healthy_now, stalled

    healthy_now, stalled = asyncio.run(run())
    assert healthy_now is True
    assert stalled is False


def test_reconcile_records_error_and_reraises():
    async def run():
        scheduler, _ = _scheduler(active=RuntimeError("db down"))
        with pytest.raises(RuntimeError):
            await scheduler.reconcile()
        return scheduler.last_reconcile_error

    error = asyncio.run(run())
    assert "RuntimeError" in error
