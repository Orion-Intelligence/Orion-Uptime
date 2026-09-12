from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_ping_monitor_model import PingMonitorModel


def _ping_monitor(expected_response_time_ms=None):
    now = datetime.now(UTC)
    return PingMonitorModel(name="Gateway", host="example.com", check_interval=60, timeout=5, expected_response_time_ms=expected_response_time_ms, created_at=now, updated_at=now)
