from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import orion.api.interactive.orion_login_manager.orion_token_manager as auth_token_state
from orion.api.interactive.orion_login_manager.orion_login_manager import AuthProfileManager
from orion.constants.constant import Collections
from orion.services.mongo_manager.shared_model.db_orion_login_model import CreateAuthProfileRequest
from tests.model.fakes import FakeCollection

NOW = datetime.now(UTC)
DEFAULT_CREDENTIALS = {"username": "admin", "password": "secret"}


def _fake_token_manager(*, token="token-1", status_code=200, error=None):
    calls = {"authenticate": [], "cache": [], "invalidate": []}

    async def authenticate_profile(profile):
        calls["authenticate"].append(profile)
        if error is not None:
            raise error
        return token, status_code

    def cache_token(profile_id, cached_token):
        calls["cache"].append((profile_id, cached_token))

    def invalidate(profile_id):
        calls["invalidate"].append(profile_id)

    manager = SimpleNamespace(authenticate_profile=authenticate_profile, cache_token=cache_token, invalidate=invalidate)
    return manager, calls


def _manager():
    collection = FakeCollection()
    engine = SimpleNamespace(database={Collections.AUTH_PROFILES: collection})
    return AuthProfileManager(engine), collection


def _create_request(name="Profile", login_url="https://example.com/login", credentials=None, headers=None):
    return CreateAuthProfileRequest(name=name, login_url=login_url, credentials=credentials or DEFAULT_CREDENTIALS, headers=headers or {})


def _seed_profile(manager, monkeypatch, *, name="Profile", login_url="https://example.com/login", credentials=None):
    fake_token_manager, _ = _fake_token_manager()
    monkeypatch.setattr(auth_token_state, "token_manager", fake_token_manager)
    return asyncio.run(manager.create_profile(_create_request(name=name, login_url=login_url, credentials=credentials)))
