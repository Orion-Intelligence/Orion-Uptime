from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.modules.monitoring_controller.checkers import ping_checker as ping_module
from app.modules.monitoring_controller.checkers.ping_checker import PingChecker
from app.service.mongo_db.shared_models.db_monitoring_controller_model import MonitorStatus
from app.service.mongo_db.shared_models.db_ping_monitor_model import PingMonitorModel
from tests.fake_model.fakes import FakePingProcess, FakePingSpawner


def test_ping_checker_reports_website_up_when_ping_succeeds(monkeypatch):
    calls = []
    process = FakePingProcess(returncode=0, stdout=b"64 bytes from 93.184.216.34: icmp_seq=1 ttl=56 time=12.4 ms")
    monkeypatch.setattr(ping_module.asyncio, "create_subprocess_exec", FakePingSpawner(process=process, calls=calls))
    now = datetime.now(UTC)
    monitor = PingMonitorModel(
        name="Example website",
        host="example.com",
        check_interval=60,
        timeout=5,
        created_at=now,
        updated_at=now,
    )

    result = asyncio.run(PingChecker().check(monitor))

    assert calls == [["ping", "-c", "1", "-W", "5", "--", "example.com"]]
    assert result.url == "example.com"
    assert result.status == MonitorStatus.UP
    assert result.response_time_ms == 12
    assert result.success is True
    assert result.error is None
