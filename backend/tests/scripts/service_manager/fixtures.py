from __future__ import annotations

import pytest

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
import orion.management.jobs.monitoring_controller.scheduler as scheduler_state
from orion.management.managers.service_manager import ServiceManager


@pytest.fixture(autouse=True)
def reset_service_manager():
    ServiceManager._ServiceManager__instance = None
    scheduler_state.scheduler = None
    auth_token_state.token_manager = None
    yield
    ServiceManager._ServiceManager__instance = None
    scheduler_state.scheduler = None
    auth_token_state.token_manager = None
