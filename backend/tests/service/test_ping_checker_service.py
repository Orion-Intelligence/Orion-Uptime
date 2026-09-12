from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from orion.management.jobs.monitoring_controller.checkers import ping_checker as ping_module
from orion.management.jobs.monitoring_controller.checkers.ping_checker import PingChecker
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus
from orion.services.mongo_manager.shared_model.db_ping_monitor_model import PingMonitorModel
from tests.fake_model.fakes import FakePingProcess, FakePingSpawner


def test_ping_checker_reports_website_up_when_ping_succeeds(monkeypatch):
    calls = []
    process = FakePingProcess(returncode=0, stdout=b"64 bytes from 93.184.216.34: icmp_seq=1 ttl=56 time=12.4 ms")
    monkeypatch.setattr(ping_module.asyncio, "create_subprocess_exec", FakePingSpawner(process=process, calls=calls))
    now = datetime.now(UTC)
    monitor = PingMonitorModel(name="Example website", host="example.com", check_interval=60, timeout=5, created_at=now, updated_at=now)

    result = asyncio.run(PingChecker().check(monitor))

    assert calls == [["ping", "-c", "1", "-W", "5", "--", "example.com"]]
    assert result.url == "example.com"
    assert result.status == MonitorStatus.UP
    assert result.response_time_ms == 12
    assert result.success is True
    assert result.error is None


class _FakeWriter:
    def close(self):
        return None

    async def wait_closed(self):
        return None


class _TimeoutProcess:
    returncode = None

    async def communicate(self):
        raise TimeoutError


def _ping_monitor(expected_response_time_ms=None):
    now = datetime.now(UTC)
    return PingMonitorModel(name="Gateway", host="example.com", check_interval=60, timeout=5, expected_response_time_ms=expected_response_time_ms, created_at=now, updated_at=now)


def test_ping_marks_slow_when_over_expected(monkeypatch):
    process = FakePingProcess(returncode=0, stdout=b"64 bytes from host: time=250.0 ms")
    monkeypatch.setattr(ping_module.asyncio, "create_subprocess_exec", FakePingSpawner(process=process))

    result = asyncio.run(PingChecker().check(_ping_monitor(expected_response_time_ms=100)))

    assert result.status == MonitorStatus.UP
    assert result.is_slow is True


def test_ping_falls_back_to_tcp_when_icmp_fails(monkeypatch):
    process = FakePingProcess(returncode=1, stdout=b"", stderr=b"100% packet loss")
    monkeypatch.setattr(ping_module.asyncio, "create_subprocess_exec", FakePingSpawner(process=process))

    async def fake_open_connection(host, port):
        return object(), _FakeWriter()

    monkeypatch.setattr(ping_module.asyncio, "open_connection", fake_open_connection)

    result = asyncio.run(PingChecker().check(_ping_monitor()))

    assert result.status == MonitorStatus.UP
    assert result.success is True
    assert result.response_time_ms is not None


def test_ping_down_when_icmp_and_tcp_fail(monkeypatch):
    process = FakePingProcess(returncode=1, stdout=b"", stderr=b"Destination unreachable")
    monkeypatch.setattr(ping_module.asyncio, "create_subprocess_exec", FakePingSpawner(process=process))

    async def fake_open_connection(host, port):
        raise OSError("no route to host")

    monkeypatch.setattr(ping_module.asyncio, "open_connection", fake_open_connection)

    result = asyncio.run(PingChecker().check(_ping_monitor()))

    assert result.status == MonitorStatus.DOWN
    assert result.success is False
    assert "did not answer" in result.error


def test_ping_times_out(monkeypatch):
    async def spawn(*_args, **_kwargs):
        return _TimeoutProcess()

    monkeypatch.setattr(ping_module.asyncio, "create_subprocess_exec", spawn)

    result = asyncio.run(PingChecker().check(_ping_monitor()))

    assert result.timed_out is True
    assert result.response_time_ms == 5000
    assert result.success is False
