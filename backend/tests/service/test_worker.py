from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from orion.management.jobs.monitoring_controller.worker import MonitorWorker
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType

NOW = datetime.now(UTC)


def _http_monitor():
    return SimpleNamespace(id="m1", persisted_id="m1", monitor_type=MonitorType.HTTP, check_interval=30)


def _heartbeat_monitor(last_heartbeat_at=None):
    return HeartbeatMonitorModel(id="h1", name="Heartbeat", expected_heartbeat_interval=300, grace_period=60, heartbeat_token_hash="hash", created_at=NOW, updated_at=NOW, last_heartbeat_at=last_heartbeat_at)


def _returns(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def test_is_alive_reflects_task_lifecycle():
    async def run():
        worker = MonitorWorker(_http_monitor(), SimpleNamespace(get_monitor=_returns(None)))
        before = worker.is_alive
        await worker.start()
        during = worker.is_alive
        await worker.stop()
        return before, during, worker.is_alive

    before, during, after = asyncio.run(run())
    assert before is False
    assert during is True
    assert after is False


def test_run_stops_when_monitor_is_missing():
    calls = []

    async def run():
        service = SimpleNamespace(get_monitor=_returns(None), check_and_update=_record(calls))
        worker = MonitorWorker(_http_monitor(), service)
        await worker.start()
        await asyncio.wait_for(worker._task, timeout=1)

    asyncio.run(run())
    assert calls == []


def test_run_checks_monitor_then_stops():
    calls = []

    async def run():
        monitor = _http_monitor()
        checked = asyncio.Event()

        async def check_and_update(item):
            calls.append(item)
            checked.set()

        service = SimpleNamespace(get_monitor=_returns(monitor), check_and_update=check_and_update)
        worker = MonitorWorker(monitor, service)
        await worker.start()
        await asyncio.wait_for(checked.wait(), timeout=1)
        await worker.stop()

    asyncio.run(run())
    assert len(calls) >= 1


def test_run_logs_and_continues_when_check_raises():
    calls = []

    async def run():
        monitor = _http_monitor()
        checked = asyncio.Event()

        async def check_and_update(item):
            calls.append(item)
            checked.set()
            raise RuntimeError("check failed")

        service = SimpleNamespace(get_monitor=_returns(monitor), check_and_update=check_and_update)
        worker = MonitorWorker(monitor, service)
        await worker.start()
        await asyncio.wait_for(checked.wait(), timeout=1)
        await worker.stop()

    asyncio.run(run())
    assert len(calls) >= 1


def test_heartbeat_run_stops_when_last_heartbeat_missing():
    async def run():
        monitor = _heartbeat_monitor(last_heartbeat_at=None)
        service = SimpleNamespace(get_monitor=_returns(monitor), check_and_update=_returns(None))
        worker = MonitorWorker(monitor, service)
        await worker.start()
        await asyncio.wait_for(worker._task, timeout=1)

    asyncio.run(run())


def test_heartbeat_run_checks_when_deadline_passed():
    calls = []

    async def run():
        monitor = _heartbeat_monitor(last_heartbeat_at=NOW - timedelta(days=1))
        checked = asyncio.Event()

        async def check_and_update(item):
            calls.append(item)
            checked.set()

        service = SimpleNamespace(get_monitor=_returns(monitor), check_and_update=check_and_update)
        worker = MonitorWorker(monitor, service)
        await worker.start()
        await asyncio.wait_for(checked.wait(), timeout=1)
        await worker.stop()

    asyncio.run(run())
    assert len(calls) >= 1


def test_seconds_until_heartbeat_deadline():
    future_monitor = _heartbeat_monitor(last_heartbeat_at=datetime.now(UTC))
    assert MonitorWorker._seconds_until_heartbeat_deadline(future_monitor) > 0

    past_monitor = _heartbeat_monitor(last_heartbeat_at=datetime.now(UTC) - timedelta(days=1))
    assert MonitorWorker._seconds_until_heartbeat_deadline(past_monitor) == 0.0

    with pytest.raises(ValueError):
        MonitorWorker._seconds_until_heartbeat_deadline(_heartbeat_monitor(last_heartbeat_at=None))


def _record(calls):
    async def _call(item):
        calls.append(item)

    return _call


def test_start_is_idempotent_when_already_running():
    async def run():
        worker = MonitorWorker(_http_monitor(), SimpleNamespace(get_monitor=_returns(None)))
        await worker.start()
        first_task = worker._task
        await worker.start()
        same = worker._task is first_task
        await worker.stop()
        return same

    assert asyncio.run(run()) is True


def test_heartbeat_run_backs_off_on_error():
    async def run():
        monitor = _heartbeat_monitor(last_heartbeat_at=NOW - timedelta(days=1))
        errored = asyncio.Event()

        async def get_monitor(_mid, _mtype):
            errored.set()
            raise RuntimeError("boom")

        worker = MonitorWorker(monitor, SimpleNamespace(get_monitor=get_monitor, check_and_update=_returns(None)))
        await worker.start()
        await asyncio.wait_for(errored.wait(), timeout=1)
        await worker.stop()

    asyncio.run(run())
