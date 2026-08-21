import asyncio
from dataclasses import dataclass

import pytest

from app.modules.monitoring_controller.monitoring_controller import MonitorManager
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus, MonitorType

pytestmark = pytest.mark.anyio


@dataclass
class FakeMonitor:
    id: str = "m1"
    name: str = "slow"
    url: str = "https://example.com/health"
    timeout: int = 1
    monitor_type: MonitorType = MonitorType.HTTP


class HangingChecker:
    async def check(self, _monitor):
        await asyncio.sleep(3600)


class QuickChecker:
    async def check(self, _monitor):
        return "ok"


async def test_deadline_scales_with_timeout():
    assert MonitorManager.check_deadline_seconds(FakeMonitor(timeout=5)) == 25
    assert MonitorManager.check_deadline_seconds(FakeMonitor(timeout=0)) == 10


async def test_hanging_check_is_abandoned(monkeypatch):
    monkeypatch.setattr(MonitorManager, "check_deadline_seconds", staticmethod(lambda monitor: 0.05))
    result = await MonitorManager.run_check_with_deadline(HangingChecker(), FakeMonitor())
    assert result.success is False
    assert result.timed_out is True
    assert result.status == MonitorStatus.DOWN
    assert "abandoned" in result.error


async def test_quick_check_passes_through():
    assert await MonitorManager.run_check_with_deadline(QuickChecker(), FakeMonitor()) == "ok"
