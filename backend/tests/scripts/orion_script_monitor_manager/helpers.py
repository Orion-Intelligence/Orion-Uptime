from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.orion_script_monitor_manager.orion_script_monitor_manager import OrionScriptMonitorManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _profile(profile_id, login_url):
    return AuthProfileModel(id=profile_id, name=profile_id, login_url=login_url, created_at=NOW, updated_at=NOW)


def _auth_profile_service(profiles):
    async def get_profile_model(profile_id):
        return next((profile for profile in profiles if profile.id == profile_id), None)

    async def list_profile_models():
        return profiles

    return SimpleNamespace(get_profile_model=get_profile_model, list_profile_models=list_profile_models)


def _manager(*, collection=None, auth_profile_service=None):
    collection = collection if collection is not None else FakeCollection()
    engine = SimpleNamespace(database={Collections.ORION_SCRIPT_MONITORS: collection})
    manager = OrionScriptMonitorManager(engine, auth_profile_service)
    return manager, collection


def _create(manager, *, name="Site", url="http://example.com", check_interval=60, timeout=10, expected_response_time_ms=None, created_by=None, auth_profile_id=None):
    return asyncio.run(manager.create_monitor(name, url, check_interval, timeout, expected_response_time_ms, created_by, auth_profile_id))
