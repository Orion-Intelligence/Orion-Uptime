from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import httpx

from orion.management.jobs.monitoring_controller.checkers.orion_script_checker import OrionScriptChecker
from orion.services.mongo_manager.shared_model.db_orion_login_model import AuthProfileModel
from orion.services.mongo_manager.shared_model.db_orion_script_monitor_model import OrionScriptMonitorModel

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _raise(exc):
    async def action(state):
        state.start = time.perf_counter()
        raise exc

    return action


def _monitor() -> OrionScriptMonitorModel:
    return OrionScriptMonitorModel(id="64f000000000000000000001", name="Orion", url="https://orion.example.com", check_interval=300, timeout=10, created_at=NOW, updated_at=NOW)


def _profile() -> AuthProfileModel:
    return AuthProfileModel(id="64f000000000000000000002", name="Orion login", login_url="https://orion.example.com/api/login", credentials={"username": "u", "password": "p"}, created_at=NOW, updated_at=NOW)


def _catalog_payload() -> dict:
    return {"rules": [{"key": "leak", "rule_type": "unique", "path": "leak_collector/leak"}, {"key": "news", "rule_type": "unique", "path": "news_collector"}, {"key": "twitter", "rule_type": "shared", "path": "social/platform"}, {"key": "generic", "rule_type": "generic", "path": None}]}


def _route(scripts_response, catalog_response=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/catalog"):
            return catalog_response(request) if callable(catalog_response) else httpx.Response(200, json=_catalog_payload())
        return scripts_response(request) if callable(scripts_response) else scripts_response
    return handler


def _scripts_payload() -> dict:
    return {
        "scripts": [
            {"id": "s1", "rule_key": "leak", "entry_kind": "script", "enabled": True, "file_name": "_leak_parser.py", "last_success_date": "2026-09-04T10:00:00Z", "last_failure_date": "2026-09-03T10:00:00Z", "last_success_message": "ok", "values": []},
            {"id": "s4", "rule_key": "twitter", "entry_kind": "script", "enabled": True, "file_name": "_twitter.py", "values": [{"url": "https://twitter.com/orion", "status": "success", "last_checked_at": "2026-09-04T09:30:00Z"}]},
            {"id": "s2", "rule_key": "news", "entry_kind": "script", "enabled": False, "file_name": "_news_parser.py", "last_success_date": "2026-09-01T10:00:00+00:00", "last_failure_date": "2026-09-02T10:00:00+00:00", "last_failure_message": "boom"},
            {"id": "v1", "rule_key": "generic", "entry_kind": "values", "enabled": True, "file_name": "_generic__values", "values": [{"url": "https://a.example.com", "status": "failure", "last_checked_at": "2026-09-04T09:00:00Z", "last_error": "timeout"}, {"url": "https://b.example.com", "status": "pending"}]},
            {"id": "s3", "entry_kind": "script", "file_name": "_fresh.py"},
        ],
        "has_more": False,
    }


def _run(checker: OrionScriptChecker, monitor: OrionScriptMonitorModel):
    return asyncio.run(checker.check(monitor))
