from __future__ import annotations

import pytest

from orion.api.interactive.status_page_manager.status_page_manager import StatusPageManager


@pytest.fixture(autouse=True)
def clear_caches():
    _reset_status_page_caches()
    yield
    _reset_status_page_caches()


def _reset_status_page_caches():
    StatusPageManager._uptime_cache.clear()
    StatusPageManager._detail_history_cache.clear()
    StatusPageManager._public_response_cache.clear()
    StatusPageManager._uptime_locks.clear()
    StatusPageManager._detail_locks.clear()
    StatusPageManager._response_locks.clear()
