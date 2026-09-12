from __future__ import annotations

from datetime import UTC, datetime

from orion.services.mongo_manager.shared_model.db_heartbeat_monitor_model import HeartbeatMonitorModel

NOW = datetime.now(UTC)


def _monitor(last_heartbeat_at):
    return HeartbeatMonitorModel(name="Cron", expected_heartbeat_interval=300, grace_period=60, heartbeat_token_hash="hash", created_at=NOW, updated_at=NOW, last_heartbeat_at=last_heartbeat_at)
