from __future__ import annotations

import pytest

from orion.api.interactive.status_page_manager.status_page_manager import StatusPageManager


@pytest.fixture(autouse=True)
def clear_caches():
    StatusPageManager._uptime_cache.clear()
    StatusPageManager._detail_history_cache.clear()
    yield
    StatusPageManager._uptime_cache.clear()
    StatusPageManager._detail_history_cache.clear()
