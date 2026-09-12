from __future__ import annotations

import pytest

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state


@pytest.fixture(autouse=True)
def _reset_token_manager(monkeypatch):
    monkeypatch.setattr(auth_token_state, "token_manager", None)
    yield
