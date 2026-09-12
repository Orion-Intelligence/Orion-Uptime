from __future__ import annotations

from orion.services.mongo_manager.mongo_controller import DatabaseManager


def _manager_with_engine(engine) -> DatabaseManager:
    manager = DatabaseManager()
    manager._engine = engine
    return manager
