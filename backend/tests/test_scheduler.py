import asyncio
from dataclasses import dataclass, field

import pytest

from app.modules.monitoring_controller.scheduler import MonitorScheduler
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorType

pytestmark = pytest.mark.anyio


@dataclass
class FakeMonitor:
    id: str
    monitor_type: MonitorType = MonitorType.HTTP
    check_interval: int = 3600
    is_active: bool = True
    last_heartbeat_at: object = None
    name: str = "fake"

    @property
    def persisted_id(self) -> str:
        return self.id


@dataclass
class FakeMonitorService:
    monitors: list[FakeMonitor] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    fail_listing: bool = False

    async def list_active_monitors(self):
        if self.fail_listing:
            raise RuntimeError("database unavailable")
        return [monitor for monitor in self.monitors if monitor.is_active]

    async def get_monitor(self, monitor_id, _monitor_type=None):
        return next((monitor for monitor in self.monitors if monitor.id == monitor_id), None)

    async def check_and_update(self, monitor):
        self.checks.append(monitor.id)


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


async def test_reconcile_starts_stops_and_restarts_workers():
    service = FakeMonitorService([FakeMonitor("a"), FakeMonitor("b")])
    clock = {"now": 1000.0}
    scheduler = MonitorScheduler(service, reconcile_interval=3600, clock=lambda: clock["now"])
    await scheduler.start()
    await settle()
    try:
        assert scheduler.status()["alive_workers"] == 2
        assert scheduler.is_healthy()
        assert sorted(service.checks) == ["a", "b"]

        task = scheduler._workers["a"]._task
        assert task is not None
        task.cancel()
        await settle()
        assert scheduler.status()["alive_workers"] == 1
        await scheduler.reconcile()
        await settle()
        assert scheduler.status()["alive_workers"] == 2

        service.monitors[1].is_active = False
        service.monitors.append(FakeMonitor("c"))
        await scheduler.reconcile()
        await settle()
        assert sorted(scheduler._workers) == ["a", "c"]
        assert all(worker.is_alive for worker in scheduler._workers.values())
    finally:
        await scheduler.stop()
    assert scheduler.status()["workers"] == 0
    assert not scheduler.is_healthy()


async def test_reconcile_failure_is_reported_and_recovers():
    service = FakeMonitorService([FakeMonitor("a")], fail_listing=True)
    clock = {"now": 0.0}
    scheduler = MonitorScheduler(service, reconcile_interval=3600, clock=lambda: clock["now"])
    await scheduler.start()
    try:
        assert not scheduler.is_healthy()
        assert "database unavailable" in scheduler.status()["last_reconcile_error"]
        service.fail_listing = False
        await scheduler.reconcile()
        assert scheduler.is_healthy()
        assert scheduler.status()["last_reconcile_error"] is None
        clock["now"] = 10_000.0
        assert not scheduler.is_healthy()
    finally:
        await scheduler.stop()


async def test_heartbeat_without_first_beat_gets_no_worker():
    service = FakeMonitorService([FakeMonitor("hb", monitor_type=MonitorType.HEARTBEAT)])
    scheduler = MonitorScheduler(service, reconcile_interval=3600)
    await scheduler.start()
    try:
        assert scheduler.status()["workers"] == 0
    finally:
        await scheduler.stop()
