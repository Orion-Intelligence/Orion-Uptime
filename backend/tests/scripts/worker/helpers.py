from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

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


def _record(calls):
    async def _call(item):
        calls.append(item)

    return _call
