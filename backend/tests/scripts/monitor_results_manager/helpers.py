from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from bson import ObjectId

from orion.constants.constant import Collections
from orion.management.jobs.monitoring_controller.monitor_results_manager.monitor_results_manager import MonitorResultManager
from orion.services.mongo_manager.shared_model.db_monitoring_controller_model import MonitorStatus, MonitorType
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.MONITOR_RESULTS: collection})
    return MonitorResultManager(engine), collection


def _async_return(value):
    async def _call(*_args, **_kwargs):
        return value

    return _call


def _capture_insert_many(collection):
    captured = []

    async def insert_many(documents):
        captured.append(documents)
        return SimpleNamespace(inserted_ids=[ObjectId() for _ in documents])

    collection.insert_many = insert_many
    return captured


def _document(monitor_id, checked_at, **overrides):
    document = {"_id": ObjectId(), "monitor_id": monitor_id, "monitor_type": MonitorType.HTTP, "status": MonitorStatus.UP, "status_code": None, "response_time_ms": None, "success": True, "is_slow": False, "checked_at": checked_at}
    document.update(overrides)
    return document
