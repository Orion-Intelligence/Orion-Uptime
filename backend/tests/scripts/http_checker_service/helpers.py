from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from orion.management.jobs.monitoring_controller.checkers.http_checker import HTTPChecker
from orion.services.mongo_manager.shared_model.db_http_monitor_model import HTTPMonitorModel
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
PROFILE_ID = "64f000000000000000000002"


def _monitor(auth_profile_id: str | None = None) -> HTTPMonitorModel:
    return HTTPMonitorModel(id="64f000000000000000000001", name="Site", url="https://app.example.com/health", check_interval=60, timeout=10, expected_status_code=200, auth_profile_id=auth_profile_id, created_at=NOW, updated_at=NOW)


def _profile(login_url: str = "https://app.example.com/api/login") -> AuthProfileModel:
    return AuthProfileModel(id=PROFILE_ID, name="App login", login_url=login_url, credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _run(checker: HTTPChecker, monitor: HTTPMonitorModel):
    return asyncio.run(checker.check(monitor))
