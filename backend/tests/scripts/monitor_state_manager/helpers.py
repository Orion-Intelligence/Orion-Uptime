from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.constants.constant import Collections
from orion.management.jobs.monitoring_controller.monitor_state_manager.monitor_state_manager import MonitorStateManager
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorType
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.MONITOR_STATES: collection})
    return MonitorStateManager(engine), collection


def _process(manager, success):
    return asyncio.run(manager.process_result("monitor-1", MonitorType.HTTP, success=success, status_code=200 if success else 503, response_time_ms=42, checked_at=NOW))
