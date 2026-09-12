from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from orion.management.jobs.monitoring_controller.checkers.api_checker import ApiChecker
from orion.services.mongo_manager.shared_model.db_api_monitor_model import APIMonitorModel
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
PROFILE_ID = "64f000000000000000000002"


def _monitor(**overrides) -> APIMonitorModel:
    fields = {"id": "64f000000000000000000001", "name": "API", "url": "https://api.example.com/health", "method": "GET", "expected_status_code": 200, "check_interval": 60, "timeout": 10, "created_at": NOW, "updated_at": NOW}
    fields.update(overrides)
    return APIMonitorModel(**fields)


def _profile(login_url: str = "https://api.example.com/login") -> AuthProfileModel:
    return AuthProfileModel(id=PROFILE_ID, name="App login", login_url=login_url, credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _checker(handler) -> ApiChecker:
    return ApiChecker(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def _run(checker: ApiChecker, monitor: APIMonitorModel):
    return asyncio.run(checker.check(monitor))
