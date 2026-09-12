from __future__ import annotations

import os

os.environ.setdefault("APP_NAME", "Orion Uptime")
os.environ.setdefault("APP_VERSION", "1.0.0")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-value-0123456789abcdef")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "7")

import pytest
from fastapi.testclient import TestClient

from main import app as fastapi_app
from orion.services.auth import authorization
from orion.services.mongo_manager.mongo_controller import get_engine
from orion.services.mongo_manager.shared_model.db_user_account_model import CurrentUserResponse, UserRole
from tests.model.fakes import FakeEngine


@pytest.fixture
def app():
    async def _fake_engine():
        return FakeEngine()

    fastapi_app.dependency_overrides[get_engine] = _fake_engine
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def override(app):
    def _override(dependency, provider):
        app.dependency_overrides[dependency] = provider

    return _override


@pytest.fixture
def authenticate_as(app):
    def _authenticate_as(role):
        current_user = CurrentUserResponse(id="user-id", username="tester", role=role)

        async def _current_user():
            return current_user

        app.dependency_overrides[authorization.get_current_user] = _current_user
        return current_user

    return _authenticate_as


@pytest.fixture
def as_admin(authenticate_as):
    return authenticate_as(UserRole.ADMIN)


@pytest.fixture
def as_viewer(authenticate_as):
    return authenticate_as(UserRole.VIEWER)


@pytest.fixture
def stub_stream(monkeypatch):
    from starlette.requests import Request

    from orion.services.realtime_manager.realtime import realtime_broker

    async def _disconnected(_self):
        return True

    async def _snapshot(is_admin):
        return {"revision": 1, "overviews": []}

    monkeypatch.setattr(Request, "is_disconnected", _disconnected)
    monkeypatch.setattr(realtime_broker, "subscribe", lambda is_admin: object())
    monkeypatch.setattr(realtime_broker, "unsubscribe", lambda queue: None)
    monkeypatch.setattr(realtime_broker, "get_snapshot", _snapshot)
