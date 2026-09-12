from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from orion.api.interactive.api_monitor_manager.api_monitor_manager import ApiMonitorManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_api_monitor_model import CreateApiMonitorRequest
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)


def _auth_profile_service(valid_ids=None):
    valid_ids = valid_ids or []

    async def get_profile_model(profile_id):
        return SimpleNamespace(id=profile_id) if profile_id in valid_ids else None

    return SimpleNamespace(get_profile_model=get_profile_model)


def _manager(*, collection=None, auth_profile_service=None):
    collection = collection if collection is not None else FakeCollection()
    engine = SimpleNamespace(database={Collections.API_MONITORS: collection})
    manager = ApiMonitorManager(engine, auth_profile_service)
    return manager, collection


def _request(*, name="API", url="http://example.com/health", expected_status_code=200, check_interval=60, timeout=10, method="GET", headers=None, request_body=None, expected_response_time_ms=None, expected_json=None, expected_headers=None, expected_content_type=None, auth_profile_id=None):
    return CreateApiMonitorRequest(
        name=name,
        url=url,
        expected_status_code=expected_status_code,
        check_interval=check_interval,
        timeout=timeout,
        method=method,
        headers=headers or {},
        request_body=request_body,
        expected_response_time_ms=expected_response_time_ms,
        expected_json=expected_json,
        expected_headers=expected_headers,
        expected_content_type=expected_content_type,
        auth_profile_id=auth_profile_id,
    )


def _create(manager, *, created_by=None, **kwargs):
    return asyncio.run(manager.create_monitor(_request(**kwargs), created_by))
