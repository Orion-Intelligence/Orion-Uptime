from __future__ import annotations

import pytest
from jwt import PyJWTError

from configs.app_dependency import AppDependency, jwt_signing_key
from orion.services.mongo_manager.shared_model.db_user_account_model import TokenType, UserRole


@pytest.fixture
def jwt_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret-value-0123456789abcdef")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")


def test_access_token_roundtrip(jwt_env):
    dependency = AppDependency()
    token = dependency.create_access_token("user-1", "tester", UserRole.ADMIN)
    payload = dependency.verify_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["username"] == "tester"
    assert payload["role"] == UserRole.ADMIN.value
    assert payload["type"] == TokenType.ACCESS.value
    assert payload["jti"]


def test_refresh_token_roundtrip(jwt_env):
    dependency = AppDependency()
    token, expires_at = dependency.create_refresh_token("user-1", "tester", UserRole.VIEWER)
    payload = dependency.verify_refresh_token(token)
    assert payload["type"] == TokenType.REFRESH.value
    assert payload["role"] == UserRole.VIEWER.value
    assert expires_at.tzinfo is not None


def test_verify_access_token_rejects_a_refresh_token(jwt_env):
    dependency = AppDependency()
    refresh_token, _ = dependency.create_refresh_token("user-1", "tester", UserRole.ADMIN)
    with pytest.raises(PyJWTError):
        dependency.verify_access_token(refresh_token)


def test_verify_refresh_token_rejects_an_access_token(jwt_env):
    dependency = AppDependency()
    access_token = dependency.create_access_token("user-1", "tester", UserRole.ADMIN)
    with pytest.raises(PyJWTError):
        dependency.verify_refresh_token(access_token)


def test_decode_token_rejects_a_wrong_signing_key(jwt_env, monkeypatch):
    dependency = AppDependency()
    token = dependency.create_access_token("user-1", "tester", UserRole.ADMIN)
    monkeypatch.setenv("JWT_SECRET", "a-different-secret-0123456789abcdef")
    with pytest.raises(PyJWTError):
        dependency.decode_token(token)


def test_jwt_signing_key_reads_the_environment(jwt_env):
    assert jwt_signing_key() == "unit-test-secret-value-0123456789abcdef"
