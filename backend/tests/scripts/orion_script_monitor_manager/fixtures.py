from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _allow_private_targets(monkeypatch):
    monkeypatch.setenv("MONITOR_ALLOW_PRIVATE_TARGETS", "true")
