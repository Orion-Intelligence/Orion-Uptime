from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from orion.management.jobs.monitoring_controller.checkers.heartbeat_checker import HeartbeatChecker
from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus

NOW = datetime.now(UTC)


def _monitor(last_heartbeat_at):
    return HeartbeatMonitorModel(name="Cron", expected_heartbeat_interval=300, grace_period=60, heartbeat_token_hash="hash", created_at=NOW, updated_at=NOW, last_heartbeat_at=last_heartbeat_at)


def test_unknown_before_first_heartbeat():
    result = asyncio.run(HeartbeatChecker().check(_monitor(last_heartbeat_at=None)))
    assert result.status == MonitorStatus.UNKNOWN
    assert result.success is False


def test_up_when_within_interval_and_grace():
    result = asyncio.run(HeartbeatChecker().check(_monitor(last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=120))))
    assert result.status == MonitorStatus.UP
    assert result.success is True


def test_down_when_deadline_exceeded():
    result = asyncio.run(HeartbeatChecker().check(_monitor(last_heartbeat_at=datetime.now(UTC) - timedelta(seconds=1000))))
    assert result.status == MonitorStatus.DOWN
    assert result.success is False
