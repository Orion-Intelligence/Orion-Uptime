from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.incident_manager.incident_manager import IncidentManager
from orion.constants.constant import Collections
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.INCIDENTS: collection})
    manager = IncidentManager(engine)
    return manager, collection
